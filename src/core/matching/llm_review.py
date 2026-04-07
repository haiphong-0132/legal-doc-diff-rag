import json
import re
import urllib.request

from src.config import OLLAMA_MODEL, OLLAMA_URL, logger
from src.core.matching.chunk_formatter import format_chunk
from src.schemas import ChangeItem, ChunkDocumentForHierarchical


def call_ollama(prompt: str) -> str:
    logger.info("Calling Ollama model=%s url=%s prompt_chars=%d", OLLAMA_MODEL, OLLAMA_URL, len(prompt))
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        response = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    logger.info("Ollama response received: %d chars", len(response))
    return response


def parse_json_response(raw_text: str):
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _excerpt_from_chunk(chunk: ChunkDocumentForHierarchical) -> str:
    return chunk.noi_dung or chunk.tieu_de or ""


LlmReviewResult = tuple[ChangeItem, str]


def llm_review_pair(vb1_chunk: ChunkDocumentForHierarchical, vb2_chunk: ChunkDocumentForHierarchical, method: str) -> LlmReviewResult:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy so sánh 1 cặp chunk đã được ghép.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "changes": [{{"old_content": "noi dung cu", "new_content": "noi dung moi"}}],
  "summary": "tom tat ngan cac diem thay doi quan trong"
}}

Method ghép cặp: {method}

VB1:
{format_chunk(vb1_chunk, True)}

VB2:
{format_chunk(vb2_chunk, True)}
"""
    vb1_excerpt = _excerpt_from_chunk(vb1_chunk)
    vb2_excerpt = _excerpt_from_chunk(vb2_chunk)

    try:
        raw_text = call_ollama(prompt)
        data = parse_json_response(raw_text)
    except Exception as exc:
        logger.warning(
            "LLM pair review failed for VB1=%s VB2=%s: %s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
            exc,
        )
        return ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=vb1_chunk.metadata.section_id,
            vb2_chunk_id=vb2_chunk.metadata.section_id,
            vb1_excerpt=vb1_excerpt,
            vb2_excerpt=vb2_excerpt,
            summary="LLM khong tra ve ket qua hop le.",
            impact="Chua ro",
            method=method,
        ), f"ERROR: {exc}"

    return ChangeItem(
        kind="sua_doi",
        vb1_chunk_id=vb1_chunk.metadata.section_id,
        vb2_chunk_id=vb2_chunk.metadata.section_id,
        vb1_excerpt=vb1_excerpt,
        vb2_excerpt=vb2_excerpt,
        summary=str(data.get("summary", "")).strip(),
        impact="",
        method=method,
        changes=[
            f"Cũ: {c.get('old_content', '').strip()} → Mới: {c.get('new_content', '').strip()}"
            if isinstance(c, dict)
            else str(c).strip()
            for c in data.get("changes", [])
            if c and str(c).strip()
        ],
    ), raw_text


def llm_review_single(chunk: ChunkDocumentForHierarchical, kind: str) -> LlmReviewResult:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy phân tích 1 chunk đơn lẻ đã được xác định là `{kind}`.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "changes": ["mo ta noi dung cu the 1", "mo ta noi dung cu the 2"],
  "summary": "tom tat ngan ly do them moi hoac xoa bo"
}}

Chunk:
{format_chunk(chunk, True)}
"""
    excerpt = _excerpt_from_chunk(chunk)
    raw_text = ""

    try:
        raw_text = call_ollama(prompt)
        data = parse_json_response(raw_text)
    except Exception as exc:
        logger.warning("LLM single review failed for %s=%s: %s", kind, chunk.metadata.section_id, exc)
        raw_text = raw_text or f"ERROR: {exc}"
        data = {
            "kind": "khong_du_can_cu",
            "summary": "LLM khong tra ve ket qua hop le.",
            "changes": [],
        }

    return ChangeItem(
        kind=kind,
        vb1_chunk_id=chunk.metadata.section_id if kind == "xoa_bo" else None,
        vb2_chunk_id=chunk.metadata.section_id if kind == "them_moi" else None,
        vb1_excerpt=excerpt if kind == "xoa_bo" else "",
        vb2_excerpt=excerpt if kind == "them_moi" else "",
        summary=str(data.get("summary", "")).strip(),
        impact="",
        method=kind,
        changes=[str(c).strip() for c in data.get("changes", []) if str(c).strip()],
    ), raw_text
