from __future__ import annotations

from pathlib import Path
from typing import Optional

from docx_loader import extract_docx_text
from pdf_loader import extract_pdf_text
from text_cleaner import clean_text

'''
import hàm ingest_file và truyền vào path và trả về string
'''
def ingest_file(path: str | Path) -> str:
    """
    Ingestion tài liệu pháp lý: đọc file Word/PDF và (tuỳ chọn) làm sạch text.

    - Nếu là .pdf  -> dùng `extract_pdf_text`
    - Nếu là .docx -> dùng `extract_docx_text`
    - Nếu `clean=True` -> chạy thêm `clean_text`
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        raw = extract_pdf_text(str(file_path), password=password)
    elif ext == ".docx":
        raw = extract_docx_text(str(file_path))
    else:
        raise ValueError(f"Định dạng file không được hỗ trợ: {ext} (chỉ hỗ trợ .pdf, .docx)")

    return clean_text(raw)


__all__ = [
    "extract_docx_text",
    "extract_pdf_text",
    "clean_text",
    "ingest_file",
]

