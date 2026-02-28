from __future__ import annotations

from typing import Optional

try:
    import docx  # type: ignore
except ImportError as exc:  # pragma: no cover - phụ thuộc ngoài
    docx = None
    _import_error = exc
else:
    _import_error = None


def extract_docx_text(path: str, encoding_fallback: Optional[str] = None) -> str:
    """
    Trích xuất toàn bộ văn bản từ file .docx thành một chuỗi.

    Mặc định sử dụng thư viện `python-docx`.
    """
    if docx is None:
        raise ImportError(
            "Không tìm thấy thư viện `python-docx`. "
            "Hãy cài đặt bằng: pip install python-docx"
        ) from _import_error

    document = docx.Document(path)
    paragraphs = [p.text for p in document.paragraphs]
    text = "\n".join(paragraphs)

    # encoding_fallback được giữ cho tương thích chữ ký, không dùng cho docx
    return text


__all__ = ["extract_docx_text"]

