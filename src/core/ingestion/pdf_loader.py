from __future__ import annotations

from typing import Optional

try:
    from PyPDF2 import PdfReader  # type: ignore
except ImportError as exc:  # pragma: no cover - phụ thuộc ngoài
    PdfReader = None
    _import_error = exc
else:
    _import_error = None


def extract_pdf_text(path: str, password: Optional[str] = None) -> str:
    """
    Trích xuất toàn bộ văn bản từ file PDF thành một chuỗi.

    Mặc định sử dụng `PyPDF2`. Hỗ trợ PDF có mật khẩu (nếu cung cấp).
    """
    if PdfReader is None:
        raise ImportError(
            "Không tìm thấy thư viện `PyPDF2`. "
            "Hãy cài đặt bằng: pip install PyPDF2"
        ) from _import_error

    reader = PdfReader(path)
    if password:
        reader.decrypt(password)  # type: ignore[call-arg]

    texts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        texts.append(page_text)

    return "\n".join(texts)


__all__ = ["extract_pdf_text"]

