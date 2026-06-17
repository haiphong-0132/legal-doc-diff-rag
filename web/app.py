import threading
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import logger
from src.schemas import PipelineResult

app = FastAPI(title="Legal Doc Diff API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://ben-overall-arlington-establishment.trycloudflare.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.config import WEB_MAX_FILE_SIZE, WEB_ALLOWED_EXTENSIONS
MAX_FILE_SIZE = WEB_MAX_FILE_SIZE
ALLOWED_EXT = WEB_ALLOWED_EXTENSIONS


@dataclass
class Job:
    job_id: str
    status: str = "pending"
    phase: str = ""
    message: str = ""
    error: str = ""
    vb1_path: str = ""
    vb2_path: str = ""
    vb1_pdf_path: str = ""
    vb2_pdf_path: str = ""
    result: Optional[PipelineResult] = None


jobs: Dict[str, Job] = {}


def _run_pipeline_thread(job: Job):
    from src.pipeline.runner import run_pipeline

    try:
        job.status = "running"

        def on_phase(phase: str, msg: str):
            job.phase = phase
            job.message = msg

        result = run_pipeline(
            vb1_path=job.vb1_path,
            vb2_path=job.vb2_path,
            on_phase=on_phase,
        )
        job.result = result
        job.status = "done"
        job.phase = "done"
        job.message = "Hoàn thành!"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)


def _save_upload(upload: UploadFile, dest: Path):
    content = upload.file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File quá lớn (tối đa {MAX_FILE_SIZE // 1024 // 1024}MB)")
    dest.write_bytes(content)


@app.post("/api/compare")
async def compare(vb1: UploadFile = File(...), vb2: UploadFile = File(...)):
    for f in [vb1, vb2]:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Định dạng không hỗ trợ: {ext}. Chỉ chấp nhận {', '.join(ALLOWED_EXT)}")

    job_id = uuid.uuid4().hex[:12]
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"legaldiff_{job_id}_"))

    vb1_path = tmp_dir / f"vb1{Path(vb1.filename).suffix}"
    vb2_path = tmp_dir / f"vb2{Path(vb2.filename).suffix}"
    _save_upload(vb1, vb1_path)
    _save_upload(vb2, vb2_path)

    job = Job(job_id=job_id, vb1_path=str(vb1_path), vb2_path=str(vb2_path))
    jobs[job_id] = job

    thread = threading.Thread(target=_run_pipeline_thread, args=(job,), daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/status")
async def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "phase": job.phase,
        "message": job.message,
        "error": job.error,
    }


def _chunk_to_dict(chunk) -> dict:
    return {
        "section_id": chunk.metadata.section_id,
        "tieu_de": chunk.tieu_de,
        "noi_dung": chunk.noi_dung,
        "ref": chunk.ref,
        "tables": getattr(chunk, "tables", []) or [],
    }


def _change_item_to_dict(item) -> dict:
    return {
        "kind": item.kind,
        "vb1_chunk_id": item.vb1_chunk_id,
        "vb2_chunk_id": item.vb2_chunk_id,
        "vb1_excerpt": item.vb1_excerpt,
        "vb2_excerpt": item.vb2_excerpt,
        "summary": item.summary,
        "changes": item.changes,
        "method": item.method,
    }


def _match_result_to_dict(m) -> dict:
    return {
        "vb2_chunk_id": m.vb2_chunk_id,
        "vb1_chunk_id": m.vb1_chunk_id,
        "method": m.method,
        "distance": m.distance,
        "rerank_score": m.rerank_score,
        "hybrid_score": m.hybrid_score,
    }


def _semantic_match_to_dict(m, vb1_map: Dict[str, Any], vb2_map: Dict[str, Any]) -> dict:
    item = {
        "kind": "giong_nhau_ngu_nghia",
        "vb2_chunk_id": m.vb2_chunk_id,
        "vb1_chunk_id": m.vb1_chunk_id,
        "method": m.method,
        "distance": m.distance,
        "rerank_score": m.rerank_score,
        "hybrid_score": m.hybrid_score,
        "summary": "Cặp chunk giống nhau về ngữ nghĩa",
        "changes": [],
    }
    if m.vb1_chunk_id and m.vb1_chunk_id in vb1_map:
        vb1 = vb1_map[m.vb1_chunk_id]
        item["vb1"] = _chunk_to_dict(vb1)
        item["vb1_excerpt"] = vb1.noi_dung or vb1.tieu_de or ""
    else:
        item["vb1_excerpt"] = ""
    if m.vb2_chunk_id in vb2_map:
        vb2 = vb2_map[m.vb2_chunk_id]
        item["vb2"] = _chunk_to_dict(vb2)
        item["vb2_excerpt"] = vb2.noi_dung or vb2.tieu_de or ""
    else:
        item["vb2_excerpt"] = ""
    return item


def _parse_id_to_key(id_str: Optional[str]) -> tuple:
    if not id_str:
        return (999, ())
    
    segments = id_str.strip().split('.')
    key_parts = []
    
    for seg in segments:
        if not seg:
            continue
        parts = seg.split('_')
        prefix = parts[0].lower()
        
        # Phân tích phần số và chữ sau prefix để sắp xếp chính xác tự nhiên (ví dụ: 1, 2, 10...)
        sub_keys = []
        for p in parts[1:]:
            if p.isdigit():
                sub_keys.append((0, int(p)))
            else:
                sub_keys.append((1, p.lower()))
        
        # Thiết lập thứ tự ưu tiên cho từng cấp bậc của văn bản pháp luật Việt Nam
        prefix_order = 99
        if prefix in ("modau", "mo_dau"):
            prefix_order = 0
        elif prefix == "phan":
            prefix_order = 1
        elif prefix == "chuong":
            prefix_order = 2
        elif prefix == "muc":
            prefix_order = 3
        elif prefix == "dieu":
            prefix_order = 4
        elif prefix == "khoan":
            prefix_order = 5
        elif prefix == "diem":
            prefix_order = 6
        elif prefix == "chinh":
            prefix_order = 7
            
        key_parts.append((prefix_order, tuple(sub_keys)))
        
    return (0, tuple(key_parts))


def _sort_matched_pair(pair: dict) -> tuple:
    chunk_id = pair.get("vb2_chunk_id") or pair.get("vb1_chunk_id")
    return _parse_id_to_key(chunk_id)


def _sort_change_item(item: dict) -> tuple:
    chunk_id = item.get("vb2_chunk_id") or item.get("vb1_chunk_id")
    return _parse_id_to_key(chunk_id)


@app.get("/api/jobs/{job_id}/results")
async def get_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    if job.status != "done":
        raise HTTPException(409, f"Job chưa hoàn thành (status={job.status})")

    r = job.result
    vb1_map = {c.metadata.section_id: c for c in r.vb1_chunks}
    vb2_map = {c.metadata.section_id: c for c in r.vb2_chunks}

    matched_pairs = []
    for m in r.match_results:
        pair: Dict[str, Any] = _match_result_to_dict(m)
        if m.vb1_chunk_id and m.vb1_chunk_id in vb1_map:
            pair["vb1"] = _chunk_to_dict(vb1_map[m.vb1_chunk_id])
        if m.vb2_chunk_id in vb2_map:
            pair["vb2"] = _chunk_to_dict(vb2_map[m.vb2_chunk_id])
        matched_pairs.append(pair)

    semantic_methods = {"llm_semantic_identical"}
    semantic_matches = [
        _semantic_match_to_dict(m, vb1_map, vb2_map)
        for m in r.match_results
        if m.method in semantic_methods and m.vb1_chunk_id
    ]

    grouped_changes: Dict[str, list] = {"sua_doi": [], "them_moi": [], "xoa_bo": [], "giong_nhau_ngu_nghia": semantic_matches}
    for item in r.change_items:
        d = _change_item_to_dict(item)
        if item.vb1_chunk_id:
            vb1_lookup = item.vb1_chunk_id.split('.')[0]
            if vb1_lookup in vb1_map:
                d["vb1"] = _chunk_to_dict(vb1_map[vb1_lookup])
        if item.vb2_chunk_id:
            vb2_lookup = item.vb2_chunk_id.split('.')[0]
            if vb2_lookup in vb2_map:
                d["vb2"] = _chunk_to_dict(vb2_map[vb2_lookup])
        grouped_changes.setdefault(item.kind, []).append(d)

    # Sắp xếp lại tất cả kết quả theo thứ tự tự nhiên của Điều Khoản Điểm
    matched_pairs = sorted(matched_pairs, key=_sort_matched_pair)
    semantic_matches = sorted(semantic_matches, key=_sort_change_item)
    for kind in list(grouped_changes.keys()):
        grouped_changes[kind] = sorted(grouped_changes[kind], key=_sort_change_item)

    return {
        "stats": r.stats,
        "matched_pairs": matched_pairs,
        "semantic_matches": semantic_matches,
        "changes": grouped_changes,
        "report_text": r.report_text,
        "vb1_path": job.vb1_path,
        "vb2_path": job.vb2_path,
    }


from fastapi.responses import FileResponse, HTMLResponse, Response


@app.get("/api/jobs/{job_id}/pdf/{doc}")
async def get_pdf(job_id: str, doc: str):
    """Trả về tài liệu gốc dưới dạng PDF hoặc HTML (nếu là DOCX) để hiển thị trong iframe."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    if doc not in ("vb1", "vb2"):
        raise HTTPException(400, "doc phải là vb1 hoặc vb2")
    
    path_str = job.vb1_path if doc == "vb1" else job.vb2_path
    if not path_str or not Path(path_str).exists():
        raise HTTPException(404, "File không tồn tại")
        
    p = Path(path_str)
    if p.suffix.lower() == ".pdf":
        return FileResponse(str(p), media_type="application/pdf")
        
    # Nếu là DOCX, chuyển đổi trực tiếp sang HTML dùng pypandoc (cực kỳ nhanh, không cần WeasyPrint/GObject)
    try:
        import pypandoc
        html = pypandoc.convert_file(
            str(p), "html5",
            extra_args=["--standalone", "--metadata", "title=Document"],
        )
        css = (
            "<style>\n"
            "body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width:820px; margin:24px auto;\n"
            "       font-size:14px; line-height:1.7; padding:0 20px; color:#1a1a1a; background-color:#fff; }\n"
            "h1, h2, h3, h4 { font-weight:700; margin-top:1.4em; color:#111827; }\n"
            "p { margin:.5em 0; }\n"
            "table { border-collapse:collapse; width:100%; margin:1em 0; }\n"
            "td, th { border:1px solid #e5e7eb; padding:8px 12px; text-align:left; }\n"
            "th { background-color:#f9fafb; font-weight:600; }\n"
            "</style>"
        )
        html = html.replace("</head>", css + "</head>", 1)
        return HTMLResponse(content=html, status_code=200)
    except Exception as exc:
        raise HTTPException(500, f"Không thể chuyển đổi DOCX sang HTML: {exc}")


@app.get("/api/jobs/{job_id}/file/{doc}")
async def get_file(job_id: str, doc: str):
    """Trả về file gốc để FE hiển thị (doc = 'vb1' hoặc 'vb2')."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    path = job.vb1_path if doc == "vb1" else job.vb2_path if doc == "vb2" else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(path, filename=Path(path).name)


@app.get("/api/jobs/{job_id}/view/{doc}", response_class=HTMLResponse)
async def view_document(job_id: str, doc: str):
    """Chuyển đổi file sang HTML để hiển thị trong iframe."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    path = job.vb1_path if doc == "vb1" else job.vb2_path if doc == "vb2" else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "File không tồn tại")

    p = Path(path)
    if p.suffix.lower() == ".pdf":
        file_url = f"/api/jobs/{job_id}/file/{doc}"
        return HTMLResponse(
            f'<html><body style="margin:0;padding:0;height:100vh">'
            f'<embed src="{file_url}" type="application/pdf" width="100%" height="100%">'
            f'</body></html>'
        )
    elif p.suffix.lower() == ".docx":
        import pypandoc
        try:
            html = pypandoc.convert_file(
                str(p), "html5",
                extra_args=["--standalone", "--metadata", "title=Document"],
            )
            # Inject minimal CSS for readability
            css = (
                '<style>'
                'body{font-family:serif;max-width:820px;margin:24px auto;'
                'font-size:14px;line-height:1.7;padding:0 20px;color:#1a1a1a}'
                'h1,h2,h3,h4{font-weight:700;margin-top:1.4em}'
                'p{margin:.5em 0}'
                'table{border-collapse:collapse;width:100%}'
                'td,th{border:1px solid #ccc;padding:4px 8px}'
                '</style>'
            )
            html = html.replace('</head>', css + '</head>', 1)
        except Exception as exc:
            raise HTTPException(500, f"Không thể chuyển đổi file: {exc}")
        return HTMLResponse(html)
    else:
        raise HTTPException(400, "Định dạng không hỗ trợ")


class ChatRequest(BaseModel):
    question: str


@app.post("/api/jobs/{job_id}/chat")
async def chat(job_id: str, body: ChatRequest):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    if job.status != "done":
        raise HTTPException(409, "Job chưa hoàn thành")

    from web.chat import chat_about_report

    try:
        answer = chat_about_report(job.result.report_text, body.question)
    except Exception as exc:
        raise HTTPException(502, f"LLM không phản hồi: {exc}")
    return {"answer": answer}
