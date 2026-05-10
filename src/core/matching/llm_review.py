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


def get_critical_tokens(text: str) -> set[str]:
    """Trích xuất chữ số, ngày tháng và các từ khóa pháp lý phủ định/bắt buộc."""
    if not text:
        return set()
        
    # Trích xuất số và ngày tháng
    numbers_and_dates = set(re.findall(r"\b\d+(?:[.,-/]\d+)*\b", text))
    
    # Trích xuất các từ khóa pháp lý cốt lõi
    critical_words = {
        "không", "không được", "chưa", "ngoại trừ", "trừ trường hợp", "nghiêm cấm",
        "được", "phải", "có quyền", "có nghĩa vụ", "bắt buộc", "cấm"
    }
    found_critical = {w for w in critical_words if w in text.lower()}
    
    return numbers_and_dates.union(found_critical)


def check_lexical_safeguard_jaccard(text1: str, text2: str) -> bool:
    """
    Sử dụng Jaccard để kiểm tra biến động tiểu tiết cốt lõi.
    Trả về True nếu Jaccard < 1.0 (có biến động nguy hiểm -> cần LLM).
    Trả về False nếu Jaccard == 1.0 (hoàn toàn trùng khớp tiểu tiết -> an toàn).
    """
    s1 = get_critical_tokens(text1)
    s2 = get_critical_tokens(text2)
    
    if not s1 and not s2:
        return False  # Cả hai đều không có số hay từ quan trọng -> An toàn
        
    intersection = len(s1.intersection(s2))
    union = len(s1.union(s2))
    jaccard_score = intersection / union if union > 0 else 0.0
    
    # Nếu Jaccard < 1.0 -> Có biến động tiểu tiết nguy hiểm -> Trả về True
    return jaccard_score < 1.0


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

    if method == "high_confidence_greedy":
        t1 = vb1_chunk.noi_dung or vb1_chunk.tieu_de or ""
        t2 = vb2_chunk.noi_dung or vb2_chunk.tieu_de or ""
        if not check_lexical_safeguard_jaccard(t1, t2):
            logger.info(
                "Lexical safeguard determined safe for high_confidence_greedy match, skipping LLM: VB1=%s VB2=%s",
                vb1_chunk.metadata.section_id,
                vb2_chunk.metadata.section_id,
            )
            return None, "SKIPPED: lexical safeguard safe"

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
        kind="sua_doi",  # Vì là cặp ghép khớp nên chắc chắn loại thay đổi là sửa đổi
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
    node_khoan_1: dict,
    node_khoan_2: dict,
    matched_diem: list,
    unmatched_diem_1: list,
    unmatched_diem_2: list,
    registry_vb1: dict,
    registry_vb2: dict,
    method: str
) -> tuple[ChangeItem | None, str]:
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
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp luật Việt Nam.
Hãy phân tích sự thay đổi của Khoản sau đây cùng với danh sách Điểm con của nó:

{chr(10).join(diff_lines)}

NGUYÊN TẮC:
- Chỉ báo cáo thay đổi làm khác ý nghĩa pháp lý, ví dụ: quyền, nghĩa vụ, điều kiện áp dụng, đối tượng áp dụng, thời hạn, mức phạt, số tiền, trình tự, thẩm quyền, ngoại lệ, phạm vi hiệu lực.
- Bỏ qua thay đổi không làm khác nội dung: số điều/khoản/mục, mã đoạn, thứ tự trình bày, xuống dòng, dấu câu, chính tả nhỏ, định dạng, cách diễn đạt tương đương.
- Nếu chỉ khác số thứ tự hoặc vị trí trong văn bản nhưng nội dung giữ nguyên, phải xem là giống nhau.
- Trả về JSON có cấu trúc:
{{
  "identical": false,
  "summary": "Tóm tắt nhận xét ngắn gọn thay đổi tổng thể của Khoản này",
  "changes": [
    "Thay đổi 1...",
    "Thay đổi 2..."
  ]
}}
"""
    messages = [
        {"role": "system", "content": "Bạn là hệ thống tự động phân tích so sánh văn bản pháp luật. Hãy luôn trả về JSON hợp lệ."},
        {"role": "user", "content": prompt}
    ]
    
    try:
        raw_text = call_local_llm(messages)
        data = parse_json_response(raw_text)
    except Exception as exc:
        logger.warning("LLM khoan_with_diem review failed: %s", exc)
        return ChangeItem(
            kind="sua_doi",
            vb1_chunk_id=node_khoan_1.get("id"),
            vb2_chunk_id=node_khoan_2.get("id"),
            vb1_excerpt=node_khoan_1.get("cached_merged_text") or node_khoan_1.get("noi_dung", ""),
            vb2_excerpt=node_khoan_2.get("cached_merged_text") or node_khoan_2.get("noi_dung", ""),
            summary="LLM khong tra ve ket qua hop le.",
            method=method,
        ), f"ERROR: {exc}"

    if data.get("identical", False):
        return None, raw_text

    return ChangeItem(
        kind="sua_doi",
        vb1_chunk_id=node_khoan_1.get("id"),
        vb2_chunk_id=node_khoan_2.get("id"),
        vb1_excerpt=node_khoan_1.get("cached_merged_text") or node_khoan_1.get("noi_dung", ""),
        vb2_excerpt=node_khoan_2.get("cached_merged_text") or node_khoan_2.get("noi_dung", ""),
        summary=str(data.get("summary", "")).strip(),
        method=method,
        changes=[str(c).strip() for c in data.get("changes", []) if str(c).strip()],
    ), raw_text
