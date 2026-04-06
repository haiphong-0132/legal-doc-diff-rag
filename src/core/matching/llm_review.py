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


def llm_review_pair(vb1_chunk: ChunkDocumentForHierarchical, vb2_chunk: ChunkDocumentForHierarchical, method: str) -> ChangeItem:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy so sánh 1 cặp chunk đã được ghép.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "kind": "sua_doi|khong_thay_doi|khong_du_can_cu",
  "summary": "tom tat ngan",
  "impact": "anh huong ngan hoac Chua ro",
  "vb1_excerpt": "trich doan ngan",
  "vb2_excerpt": "trich doan ngan",
  "important_points": ["y 1", "y 2"],
  "reason": "giai thich ngan"
}}

Method ghep cap: {method}

VB1:
{format_chunk(vb1_chunk, True)}

VB2:
{format_chunk(vb2_chunk, True)}
"""
    try:
        data = parse_json_response(call_ollama(prompt))
    except Exception as exc:
        logger.warning(
            "LLM pair review failed for VB1=%s VB2=%s: %s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
            exc,
        )
        return ChangeItem(
            kind="khong_du_can_cu",
            vb1_chunk_id=vb1_chunk.metadata.section_id,
            vb2_chunk_id=vb2_chunk.metadata.section_id,
            vb1_excerpt=vb1_chunk.noi_dung or vb1_chunk.tieu_de or "",
            vb2_excerpt=vb2_chunk.noi_dung or vb2_chunk.tieu_de or "",
            summary="LLM khong tra ve ket qua hop le.",
            impact="Chua ro",
            reason=str(exc),
            method=method,
        )

    return ChangeItem(
        kind=str(data.get("kind", "khong_du_can_cu")).strip().lower(),
        vb1_chunk_id=vb1_chunk.metadata.section_id,
        vb2_chunk_id=vb2_chunk.metadata.section_id,
        vb1_excerpt=str(data.get("vb1_excerpt", "")).strip(),
        vb2_excerpt=str(data.get("vb2_excerpt", "")).strip(),
        summary=str(data.get("summary", "")).strip(),
        impact=str(data.get("impact", "Chua ro")).strip() or "Chua ro",
        reason=str(data.get("reason", "")).strip(),
        method=method,
        important_points=[str(point).strip() for point in data.get("important_points", []) if str(point).strip()],
    )


def llm_review_single(chunk: ChunkDocumentForHierarchical, kind: str) -> ChangeItem:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy phân tích 1 chunk đơn lẻ đã được xác định sơ bộ là `{kind}`.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "kind": "{kind}|khong_du_can_cu",
  "summary": "tom tat ngan",
  "impact": "anh huong ngan hoac Chua ro",
  "excerpt": "trich doan ngan",
  "important_points": ["y 1", "y 2"],
  "reason": "giai thich ngan"
}}

Chunk:
{format_chunk(chunk, True)}
"""
    try:
        data = parse_json_response(call_ollama(prompt))
    except Exception as exc:
        logger.warning("LLM single review failed for %s=%s: %s", kind, chunk.metadata.section_id, exc)
        data = {
            "kind": "khong_du_can_cu",
            "summary": "LLM khong tra ve ket qua hop le.",
            "impact": "Chua ro",
            "excerpt": chunk.noi_dung or chunk.tieu_de or "",
            "important_points": [],
            "reason": str(exc),
        }

    excerpt = str(data.get("excerpt", "")).strip()
    return ChangeItem(
        kind=str(data.get("kind", "khong_du_can_cu")).strip().lower(),
        vb1_chunk_id=chunk.metadata.section_id if kind == "xoa_bo" else None,
        vb2_chunk_id=chunk.metadata.section_id if kind == "them_moi" else None,
        vb1_excerpt=excerpt if kind == "xoa_bo" else "",
        vb2_excerpt=excerpt if kind == "them_moi" else "",
        summary=str(data.get("summary", "")).strip(),
        impact=str(data.get("impact", "Chua ro")).strip() or "Chua ro",
        reason=str(data.get("reason", "")).strip(),
        method=kind,
        important_points=[str(point).strip() for point in data.get("important_points", []) if str(point).strip()],
    )
