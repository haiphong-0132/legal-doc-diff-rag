import json
import re

from src.config import logger
from src.core.api.call_api import call_generate_api
from src.core.matching.chunk_formatter import format_chunk
from src.core.matching.llm_prompts import (
    PAIR_REVIEW_SYSTEM_PROMPT,
    PAIR_REVIEW_USER_PROMPT,
    SINGLE_REVIEW_SYSTEM_PROMPT,
    SINGLE_REVIEW_USER_PROMPT,
)
from src.schemas import ChangeItem, ChunkDocumentForHierarchical


def call_local_llm(messages: list[dict], max_length: int = 512) -> str:
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
    logger.info("Calling local generate API messages=%d prompt_chars=%d", len(messages), prompt_chars)

    response = call_generate_api(
        messages=messages,
        max_length=max_length,
        temperature=0,
        timeout=180,
    )
    answer = str(response.get("answer", "")).strip()
    logger.info("Local generate API response received: %d chars", len(answer))
    return answer


def parse_json_response(raw_text: str):
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def llm_review_pair(
    vb1_chunk: ChunkDocumentForHierarchical,
    vb2_chunk: ChunkDocumentForHierarchical,
    method: str,
) -> tuple[ChangeItem | None, str]:
    section_num_re = re.compile(
        r"^[\s]*(?:điều|khoản|mục|chương|phần|article|section|clause)?\s*"
        r"[\d]+(?:[.\-][\d]+)*[.\s:)]*",
        re.IGNORECASE,
    )
    vb1_normalized = re.sub(
        r"\s+",
        " ",
        section_num_re.sub("", vb1_chunk.noi_dung or ""),
    ).strip().lower()
    vb2_normalized = re.sub(
        r"\s+",
        " ",
        section_num_re.sub("", vb2_chunk.noi_dung or ""),
    ).strip().lower()

    if vb1_normalized == vb2_normalized and len(vb1_normalized) > 0:
        logger.info(
            "Content identical (numbering-only diff), skipping LLM: VB1=%s VB2=%s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
        )
        return None, "SKIPPED: content identical"

    messages = [
        {"role": "system", "content": PAIR_REVIEW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": PAIR_REVIEW_USER_PROMPT.format(
                method=method,
                vb1_text=format_chunk(vb1_chunk, True),
                vb2_text=format_chunk(vb2_chunk, True),
            ),
        },
    ]
    vb1_excerpt = vb1_chunk.noi_dung or vb1_chunk.tieu_de or ""
    vb2_excerpt = vb2_chunk.noi_dung or vb2_chunk.tieu_de or ""

    try:
        raw_text = call_local_llm(messages)
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
            method=method,
        ), f"ERROR: {exc}"

    # LLM xác định nội dung giống nhau → bỏ qua
    if data.get("identical", False):
        logger.info(
            "LLM determined identical content: VB1=%s VB2=%s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
        )
        return None, raw_text

    return ChangeItem(
        kind="sua_doi",
        vb1_chunk_id=vb1_chunk.metadata.section_id,
        vb2_chunk_id=vb2_chunk.metadata.section_id,
        vb1_excerpt=vb1_excerpt,
        vb2_excerpt=vb2_excerpt,
        summary=str(data.get("summary", "")).strip(),
        method=method,
        changes=[
            f"Cũ: {c.get('old_content', '').strip()}\nMới: {c.get('new_content', '').strip()}"
            if isinstance(c, dict)
            else str(c).strip()
            for c in data.get("changes", [])
            if c and str(c).strip()
        ],
    ), raw_text


def llm_review_single(chunk: ChunkDocumentForHierarchical, kind: str) -> tuple[ChangeItem | None, str]:
    messages = [
        {"role": "system", "content": SINGLE_REVIEW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": SINGLE_REVIEW_USER_PROMPT.format(
                kind=kind,
                chunk_text=format_chunk(chunk, True),
            ),
        },
    ]
    excerpt = chunk.noi_dung or chunk.tieu_de or ""
    raw_text = ""

    try:
        raw_text = call_local_llm(messages, max_length=256)
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
        method=kind,
        changes=[str(c).strip() for c in data.get("changes", []) if str(c).strip()],
    ), raw_text
