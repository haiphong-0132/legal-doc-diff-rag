import re

from src.core.embedding import decode_section_id
from src.schemas import ChunkDocumentForHierarchical


def format_chunk(chunk: ChunkDocumentForHierarchical, for_llm: bool = False) -> str:
    if not for_llm:
        raw = f"Tieu de: {chunk.tieu_de or ''}\nNoi dung: {chunk.noi_dung or ''}\nRef: {', '.join(chunk.ref or [])}"
        return re.sub(r"\s+", " ", raw).strip()

    ma_doan = chunk.metadata.section_id
    try:
        ma_doan = decode_section_id(ma_doan)
    except ValueError:
        pass

    # Nếu dùng cho LLM, lấy tieu_de (chứa nội dung gốc chưa gộp) thay vì noi_dung gộp để giảm kích thước prompt và tránh trùng lặp
    noi_dung = chunk.tieu_de or chunk.noi_dung or "(trống)"
    vien_dan = ", ".join([decode_section_id(r) if r else r for r in (chunk.ref or [])]) or "Không có"
    return f"Mã đoạn: {ma_doan}\nNội dung: {noi_dung}\nCác viện dẫn: {vien_dan}"
