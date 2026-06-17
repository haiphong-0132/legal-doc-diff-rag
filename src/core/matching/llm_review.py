import os
import json
import re

from src.config import (
    LLM_MODE,
    LLM_API_KEY,
    LLM_MODEL_NAME,
    LLM_API_URL,
    LLM_TEMPERATURE,
    LLM_TOP_P,
    LLM_MAX_TOKENS,
    LLM_REMOTE_TEMPERATURE,
    LLM_REMOTE_MAX_LENGTH,
    LLM_REMOTE_TIMEOUT,
    logger
)
from src.core.api.call_api import call_generate_api
from src.core.matching.chunk_formatter import format_chunk
from src.core.matching.llm_prompts import (
    PAIR_REVIEW_SYSTEM_PROMPT,
    PAIR_REVIEW_USER_PROMPT,
    SINGLE_REVIEW_SYSTEM_PROMPT,
    SINGLE_REVIEW_USER_PROMPT,
    KHOAN_WITH_DIEM_SYSTEM_PROMPT,
    KHOAN_WITH_DIEM_USER_PROMPT,
    FLAT_DIEU_SYSTEM_PROMPT,
    FLAT_DIEU_USER_PROMPT,
)
from src.schemas import ChangeItem, ChunkDocumentForHierarchical



def call_local_llm(messages: list[dict], max_length: int = 2000) -> str:
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
    
    if LLM_MODE == "nvidia":
        logger.info("Calling NVIDIA API model=%s messages=%d prompt_chars=%d", LLM_MODEL_NAME, len(messages), prompt_chars)
        try:
            from openai import OpenAI
            
            # Khởi tạo client OpenAI kết nối tới NVIDIA Endpoint
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=LLM_API_KEY or os.getenv("NVIDIA_API_KEY", "")
            )
            
            # Gọi API
            completion = client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=messages,
                temperature=LLM_TEMPERATURE,
                top_p=LLM_TOP_P,
                max_tokens=LLM_MAX_TOKENS,
                stream=True
            )
            
            # Thu thập stream kết quả một cách an toàn
            answer_parts = []
            for chunk in completion:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        answer_parts.append(delta.content)
            
            answer = "".join(answer_parts).strip()
            logger.info("NVIDIA API response received: %d chars", len(answer))
            return answer
            
        except Exception as exc:
            logger.error("Failed to call NVIDIA API: %s", exc)
            raise
            
    else:
        # Mặc định: LLM_MODE == "remote"
        logger.info("Calling remote generate API messages=%d prompt_chars=%d", len(messages), prompt_chars)
        try:
            response = call_generate_api(
                messages=messages,
                max_length=max_length if max_length != 2000 else LLM_REMOTE_MAX_LENGTH,
                temperature=LLM_REMOTE_TEMPERATURE,
                timeout=LLM_REMOTE_TIMEOUT,
                base_url=LLM_API_URL,
            )
            answer = str(response.get("answer", "")).strip()
            logger.info("Remote generate API response received: %d chars", len(answer))
            return answer
        except Exception as exc:
            logger.error("Failed to call remote generate API: %s", exc)
            raise



def parse_json_response(raw_text: str):
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Xử lý nếu model sinh ra markdown code block (VD: ```json ... ```)
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
                
        # Tìm đoạn JSON đầu tiên bằng cách đếm ngoặc {} (Hỗ trợ ngoặc lồng nhau)
        start = raw_text.find('{')
        if start != -1:
            count = 0
            for i in range(start, len(raw_text)):
                if raw_text[i] == '{':
                    count += 1
                elif raw_text[i] == '}':
                    count -= 1
                    
                if count == 0:
                    json_str = raw_text[start:i+1]
                    try:
                        return json.loads(json_str)
                    except:
                        break
        raise


def llm_review_pair(
    vb1_chunk: ChunkDocumentForHierarchical,
    vb2_chunk: ChunkDocumentForHierarchical,
    method: str,
) -> tuple[ChangeItem | None, str, str | None]:
    # Chỉ bỏ qua LLM khi text trùng khớp chính xác (chuẩn hóa khoảng trắng + hoa/thường).
    # Mọi khác biệt còn lại — kể cả chỉ khác cách đánh số — đều giao cho LLM tự quyết định
    # qua trường "identical" (PAIR_REVIEW_SYSTEM_PROMPT đã hướng dẫn: khác số thứ tự = giống nhau).
    vb1_text = re.sub(r"\s+", " ", vb1_chunk.noi_dung or "").strip().lower()
    vb2_text = re.sub(r"\s+", " ", vb2_chunk.noi_dung or "").strip().lower()

    if vb1_text and vb1_text == vb2_text:
        logger.info(
            "Content identical, skipping LLM: VB1=%s VB2=%s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
        )
        return None, "SKIPPED: content identical", "exact"

    user_prompt = PAIR_REVIEW_USER_PROMPT.format(
        method=method,
        vb1_text=format_chunk(vb1_chunk, True),
        vb2_text=format_chunk(vb2_chunk, True),
    )

    messages = [
        {"role": "system", "content": PAIR_REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
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
        ), f"ERROR: {exc}", None

    # LLM xác định nội dung giống nhau (kể cả chỉ khác đánh số / diễn đạt lại) → bỏ qua, không tạo thay đổi
    if data.get("identical", False):
        logger.info(
            "LLM determined identical content: VB1=%s VB2=%s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
        )
        return None, raw_text, None

    # Xử lý lọc và chuẩn hóa danh sách thay đổi từ LLM, bỏ các phần cũ mới giống hệt nhau (hallucination)
    filtered_changes = []
    for c in data.get("changes", []):
        if isinstance(c, dict):
            old = str(c.get("old_content", "")).strip()
            new = str(c.get("new_content", "")).strip()
            if old == new:
                continue  # Loại bỏ hoàn toàn nếu cũ mới giống nhau
            if old and new:
                filtered_changes.append(f"Cũ: {old}\nMới: {new}")
            elif old:
                filtered_changes.append(f"Xóa bỏ: {old}")
            elif new:
                filtered_changes.append(f"Thêm mới: {new}")
        else:
            if str(c).strip():
                filtered_changes.append(str(c).strip())

    summary_text = str(data.get("summary", "")).strip()

    return ChangeItem(
        kind="sua_doi",
        vb1_chunk_id=vb1_chunk.metadata.section_id,
        vb2_chunk_id=vb2_chunk.metadata.section_id,
        vb1_excerpt=vb1_excerpt,
        vb2_excerpt=vb2_excerpt,
        summary=summary_text,
        method=method,
        changes=filtered_changes,
    ), raw_text, None


def llm_review_dieu_flat(
    vb1_chunk: ChunkDocumentForHierarchical,
    vb2_chunk: ChunkDocumentForHierarchical,
    method: str,
) -> tuple[list[ChangeItem], str]:
    """Review một Điều PHẲNG (không có Khoản/Điểm). Trả về DANH SÁCH ChangeItem,
    mỗi thay đổi (sửa/thêm/xóa) là một item riêng — đặc biệt để không bỏ sót các
    đoạn bị XÓA bên trong một Điều bị sửa. Chỉ dùng cho nhánh Điều phẳng ở runner,
    không ảnh hưởng luồng Khoản/Điểm.
    """
    dieu_id = vb1_chunk.metadata.section_id or vb2_chunk.metadata.section_id

    # Bỏ qua LLM nếu text trùng khớp chính xác.
    vb1_text = re.sub(r"\s+", " ", vb1_chunk.noi_dung or "").strip().lower()
    vb2_text = re.sub(r"\s+", " ", vb2_chunk.noi_dung or "").strip().lower()
    if vb1_text and vb1_text == vb2_text:
        return [], "SKIPPED: content identical"

    user_prompt = FLAT_DIEU_USER_PROMPT.format(
        vb1_text=format_chunk(vb1_chunk, True),
        vb2_text=format_chunk(vb2_chunk, True),
    )
    messages = [
        {"role": "system", "content": FLAT_DIEU_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw_text = call_local_llm(messages)
        data = parse_json_response(raw_text)
    except Exception as exc:
        logger.warning("LLM flat-dieu review failed for %s: %s", dieu_id, exc)
        # Fallback an toàn: coi như một sửa đổi tổng thể để không nuốt thay đổi
        return [ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=dieu_id,
            vb2_chunk_id=dieu_id,
            vb1_excerpt=vb1_chunk.noi_dung or "",
            vb2_excerpt=vb2_chunk.noi_dung or "",
            summary="LLM khong tra ve ket qua hop le.",
            method=method,
        )], f"ERROR: {exc}"

    if data.get("identical", False):
        return [], raw_text

    # Chiến lược: GỘP mọi thay đổi "sua_doi" trong cùng Điều thành MỘT item
    # (tránh phân mảnh từng dòng bảng/giá), nhưng TÁCH riêng từng đoạn bị XÓA và
    # từng đoạn THÊM MỚI thành item độc lập (đây mới là phần trước đây hay bị nuốt).
    items: list[ChangeItem] = []
    sua_changes: list[str] = []
    sua_summaries: list[str] = []
    sua_old, sua_new = "", ""
    kind_counts = {"them_moi": 0, "xoa_bo": 0}

    for c in data.get("changes", []):
        if not isinstance(c, dict):
            continue
        old = str(c.get("old_content", "")).strip()
        new = str(c.get("new_content", "")).strip()
        if old and new and old == new:
            continue

        kind = str(c.get("kind", "")).strip().lower()
        if kind not in ("them_moi", "xoa_bo", "sua_doi"):
            kind = "xoa_bo" if old and not new else "them_moi" if new and not old else "sua_doi"
        summary = str(c.get("summary", "")).strip()

        if kind == "sua_doi":
            sua_changes.append(f"Cũ: {old}\nMới: {new}" if old and new else (f"Xóa bỏ: {old}" if old else f"Thêm mới: {new}"))
            if summary:
                sua_summaries.append(summary)
            if old and not sua_old:
                sua_old = old
            if new and not sua_new:
                sua_new = new
            continue

        # xoa_bo / them_moi: mỗi đoạn là một item riêng (gán hậu tố id để khỏi bị merge)
        idx = kind_counts[kind]
        kind_counts[kind] += 1
        suffix = "" if idx == 0 else f".{kind[:3]}_{idx}"
        items.append(ChangeItem(
            kind=kind,
            vb1_chunk_id=(dieu_id + suffix) if kind == "xoa_bo" else None,
            vb2_chunk_id=(dieu_id + suffix) if kind == "them_moi" else None,
            vb1_excerpt=old if kind == "xoa_bo" else "",
            vb2_excerpt=new if kind == "them_moi" else "",
            summary=summary,
            method=method,
            changes=[f"Xóa bỏ: {old}" if kind == "xoa_bo" else f"Thêm mới: {new}"],
        ))

    if sua_changes:
        items.append(ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=dieu_id,
            vb2_chunk_id=dieu_id,
            vb1_excerpt=sua_old or (vb1_chunk.noi_dung or ""),
            vb2_excerpt=sua_new or (vb2_chunk.noi_dung or ""),
            summary=" ".join(sua_summaries),
            method=method,
            changes=sua_changes,
        ))

    return items, raw_text


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
    node_khoan_1: dict,
    node_khoan_2: dict,
    matched_diem: list,
    unmatched_diem_1: list,
    unmatched_diem_2: list,
    registry_vb1: dict,
    registry_vb2: dict,
    method: str
) -> tuple[ChangeItem | None, str]:
    # Tìm xem Điểm nào thực tế có sự thay đổi để đặt ID đại diện chính xác hơn cấp Khoản
    changed_diem_1_id = None
    changed_diem_2_id = None
    
    changed_diems_list = []
    for d1_id, d2_id, _ in matched_diem:
        d1 = registry_vb1.get(d1_id, {})
        d2 = registry_vb2.get(d2_id, {})
        s1 = re.sub(r"\s+", " ", str(d1.get('cached_merged_text') or d1.get('noi_dung') or "")).strip().lower()
        s2 = re.sub(r"\s+", " ", str(d2.get('cached_merged_text') or d2.get('noi_dung') or "")).strip().lower()
        if s1 != s2:
            changed_diems_list.append((d1_id, d2_id))
            
    if changed_diems_list:
        changed_diem_1_id, changed_diem_2_id = changed_diems_list[0]
    elif unmatched_diem_2:
        changed_diem_2_id = unmatched_diem_2[0].get("id")
    elif unmatched_diem_1:
        changed_diem_1_id = unmatched_diem_1[0].get("id")

    final_vb1_id = changed_diem_1_id if changed_diem_1_id else node_khoan_1.get("id")
    final_vb2_id = changed_diem_2_id if changed_diem_2_id else node_khoan_2.get("id")

    # 1. Dựng cấu trúc diff trực quan gửi cho LLM
    diff_lines = []
    diff_lines.append(f"KHOẢN GỐC (VB1): {node_khoan_1.get('cached_merged_text') or node_khoan_1.get('noi_dung')}")
    diff_lines.append(f"KHOẢN MỚI (VB2): {node_khoan_2.get('cached_merged_text') or node_khoan_2.get('noi_dung')}")
    
    if matched_diem or unmatched_diem_1 or unmatched_diem_2:
        diff_lines.append("\n=== CHI TIẾT CÁC ĐIỂM TRỰC THUỘC ===")
        for d1_id, d2_id, _ in matched_diem:
            d1 = registry_vb1.get(d1_id, {})
            d2 = registry_vb2.get(d2_id, {})
            # So sánh chuẩn hóa nghiêm ngặt
            s1 = re.sub(r"\s+", " ", str(d1.get('cached_merged_text') or d1.get('noi_dung') or "")).strip().lower()
            s2 = re.sub(r"\s+", " ", str(d2.get('cached_merged_text') or d2.get('noi_dung') or "")).strip().lower()
            if s1 and s1 == s2:
                continue # Giống nhau tuyệt đối, bỏ qua không gửi LLM để tiết kiệm context
                
            diff_lines.append(f"- Điểm {d1_id} -> {d2_id}:")
            diff_lines.append(f"  + Cũ: {d1.get('cached_merged_text') or d1.get('noi_dung')}")
            diff_lines.append(f"  + Mới: {d2.get('cached_merged_text') or d2.get('noi_dung')}")
            
        for d1 in unmatched_diem_1:
            diff_lines.append(f"- Điểm {d1.get('id')} bị XÓA BỎ: {d1.get('cached_merged_text') or d1.get('noi_dung')}")
            
        for d2 in unmatched_diem_2:
            diff_lines.append(f"- Điểm {d2.get('id')} được THÊM MỚI: {d2.get('cached_merged_text') or d2.get('noi_dung')}")

    # 2. Truyền chuỗi cấu trúc này vào Prompt để LLM tập trung tóm tắt và đánh giá tác động
    prompt = KHOAN_WITH_DIEM_USER_PROMPT.format(diff_block=chr(10).join(diff_lines))
    messages = [
        {"role": "system", "content": KHOAN_WITH_DIEM_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    
    try:
        raw_text = call_local_llm(messages)
        data = parse_json_response(raw_text)
    except Exception as exc:
        logger.warning("LLM khoan_with_diem review failed: %s", exc)
        return ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=final_vb1_id,
            vb2_chunk_id=final_vb2_id,
            vb1_excerpt=node_khoan_1.get("cached_merged_text") or node_khoan_1.get("noi_dung", ""),
            vb2_excerpt=node_khoan_2.get("cached_merged_text") or node_khoan_2.get("noi_dung", ""),
            summary="LLM khong tra ve ket qua hop le.",
            method=method,
        ), f"ERROR: {exc}"

    if data.get("identical", False):
        return None, raw_text

    return ChangeItem(
        kind="sua_doi",
        vb1_chunk_id=final_vb1_id,
        vb2_chunk_id=final_vb2_id,
        vb1_excerpt=node_khoan_1.get("cached_merged_text") or node_khoan_1.get("noi_dung", ""),
        vb2_excerpt=node_khoan_2.get("cached_merged_text") or node_khoan_2.get("noi_dung", ""),
        summary=str(data.get("summary", "")).strip(),
        method=method,
        changes=[str(c).strip() for c in data.get("changes", []) if str(c).strip()],
    ), raw_text
