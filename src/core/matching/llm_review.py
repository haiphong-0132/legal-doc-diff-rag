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


def call_local_llm(messages: list[dict], max_length: int = 2000) -> str:
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


def call_llm_api(prompt: str, max_length: int = 2000) -> str:
    return call_local_llm([{"role": "user", "content": prompt}], max_length=max_length)


def call_local_llm(messages: list[dict], max_length: int = 512) -> str:
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
    logger.info("Calling local generate API messages=%d prompt_chars=%d", len(messages), prompt_chars)
    try:
        response = call_generate_api(
            messages=messages,
            max_length=max_length,
            temperature=0,
            timeout=180,
        )
        answer = str(response.get("answer", "")).strip()
        logger.info("Local generate API response received: %d chars", len(answer))
        return answer
    except Exception as exc:
        logger.error("Failed to call local generate API: %s", exc)
        raise


# Giữ alias call_ollama để đảm bảo tương thích 100% với các phần khác (như web/chat.py)
call_ollama = call_llm_api
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


def llm_review_khoan_with_diem(
    vb1_parent_id: str,
    vb2_parent_id: str,
    matched_sub_pairs: list[tuple[str, str]],
    unmatched_sub_1: list[dict],
    unmatched_sub_2: list[dict],
    registry_vb1: dict,
    registry_vb2: dict,
) -> tuple[list[ChangeItem], str]:
    """
    Review toàn bộ thay đổi cấp con (Khoản, Điểm) của một Điều cha trong cùng một cuộc gọi LLM duy nhất.
    Giúp giữ trọn vẹn ngữ cảnh và tối ưu chi phí API.
    """
    comparison_text = []

    comparison_text.append("=== ĐIỀU CHA ===")
    p1 = registry_vb1.get(vb1_parent_id) or {}
    p2 = registry_vb2.get(vb2_parent_id) or {}
    comparison_text.append(f"VB1: {p1.get('tieu_de', '')} - {p1.get('noi_dung', '')}")
    comparison_text.append(f"VB2: {p2.get('tieu_de', '')} - {p2.get('noi_dung', '')}\n")

    comparison_text.append("=== CÁC PHẦN TỬ CON ĐÃ GHÉP CẶP ===")
    for idx, (id1, id2) in enumerate(matched_sub_pairs):
        n1 = registry_vb1.get(id1) or {}
        n2 = registry_vb2.get(id2) or {}
        comparison_text.append(f"Cặp #{idx+1}:")
        comparison_text.append(f"  - VB1 [ID: {id1}]: {n1.get('tieu_de', '')} {n1.get('noi_dung', '')}")
        comparison_text.append(f"  - VB2 [ID: {id2}]: {n2.get('tieu_de', '')} {n2.get('noi_dung', '')}")

    if unmatched_sub_1:
        comparison_text.append("\n=== CÁC PHẦN TỬ CON BỊ XÓA BỎ (CÓ TRONG VB1 NHƯNG KHÔNG CÓ TRONG VB2) ===")
        for n1 in unmatched_sub_1:
            comparison_text.append(f"  - VB1 [ID: {n1.get('id')}]: {n1.get('tieu_de', '')} {n1.get('noi_dung', '')}")

    if unmatched_sub_2:
        comparison_text.append("\n=== CÁC PHẦN TỬ CON THÊM MỚI (CÓ TRONG VB2 NHƯNG KHÔNG CÓ TRONG VB1) ===")
        for n2 in unmatched_sub_2:
            comparison_text.append(f"  - VB2 [ID: {n2.get('id')}]: {n2.get('tieu_de', '')} {n2.get('noi_dung', '')}")

    comparison_str = "\n".join(comparison_text)

    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp luật cấp cao.
Hãy so sánh sự thay đổi về nội dung thực tế giữa các phần tử con (Khoản, Điểm) trong cùng một Điều cha.

NGUYÊN TẮC REVIEW QUAN TRỌNG:
1. CHỈ báo cáo thay đổi về NỘI DUNG THỰC SỰ (quyền, nghĩa vụ, điều kiện, mức phạt, thời hạn, số tiền, phạm vi...).
2. KHÔNG báo cáo thay đổi về: số thứ tự điều khoản, mã đoạn con (ví dụ: a) -> b), Khoản 1 -> Khoản 2), lỗi định dạng, dấu câu.
3. Nếu nội dung của một cặp ghép hoàn toàn giống nhau (chỉ khác số thứ tự/mã đoạn hoặc phong cách hành văn đồng nghĩa) -> BỎ QUA không ghi nhận thay đổi cho cặp đó.
4. Với mỗi phần tử con THÊM MỚI hoặc XÓA BỎ, hãy tóm tắt nội dung pháp lý của phần tử đó.

Yêu cầu trả về duy nhất một chuỗi JSON hợp lệ theo định dạng danh sách (List of Objects) như sau:
[
  {{
    "kind": "sua_doi" | "them_moi" | "xoa_bo",
    "vb1_chunk_id": "ID của phần tử trong VB1 (để null nếu là thêm mới)",
    "vb2_chunk_id": "ID của phần tử trong VB2 (để null nếu là xóa bỏ)",
    "vb1_excerpt": "Nội dung cũ liên quan từ VB1",
    "vb2_excerpt": "Nội dung mới liên quan từ VB2",
    "summary": "Tóm tắt ngắn gọn sự thay đổi thực tế hoặc nội dung thêm/xóa",
    "changes": ["Chi tiết thay đổi 1", "Chi tiết thay đổi 2"]
  }}
]

Dữ liệu so sánh:
{comparison_str}
"""

    raw_text = ""
    change_items = []
    try:
        raw_text = call_ollama(prompt)
        parsed_data = parse_json_response(raw_text)
        if not isinstance(parsed_data, list):
            if isinstance(parsed_data, dict) and "changes" in parsed_data:
                parsed_data = parsed_data["changes"]
            else:
                parsed_data = [parsed_data]

        for item in parsed_data:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind") or "sua_doi"
            change_items.append(ChangeItem(
                kind=kind,
                vb1_chunk_id=item.get("vb1_chunk_id"),
                vb2_chunk_id=item.get("vb2_chunk_id"),
                vb1_excerpt=item.get("vb1_excerpt") or "",
                vb2_excerpt=item.get("vb2_excerpt") or "",
                summary=item.get("summary") or "",
                impact=item.get("impact") or "",
                method=f"zoomin_{kind}",
                changes=[str(c).strip() for c in item.get("changes", []) if str(c).strip()]
            ))
    except Exception as exc:
        logger.warning(
            "LLM hierarchical zoom-in review failed for VB1_parent=%s VB2_parent=%s: %s",
            vb1_parent_id,
            vb2_parent_id,
            exc,
        )
        change_items.append(ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=vb1_parent_id,
            vb2_chunk_id=vb2_parent_id,
            vb1_excerpt=f"Lỗi phân tích cấp con: {exc}",
            vb2_excerpt="",
            summary="LLM không trả về danh sách thay đổi hợp lệ.",
            impact="",
            method="zoomin_error",
            changes=[]
        ))

    return change_items, raw_text
