from __future__ import annotations

from typing import Iterable, List, Optional, Union

try:
    import docx  # type: ignore
except ImportError as exc:  # pragma: no cover - phụ thuộc ngoài
    docx = None
    _import_error = exc
else:
    _import_error = None


def extract_docx_text(path: str, encoding_fallback: Optional[str] = None) -> str:
    """
    Trích xuất toàn bộ văn bản từ file .docx thành một chuỗi,
    bao gồm cả nội dung bảng được chuyển sang dạng văn bản có cấu trúc.

    Mặc định sử dụng thư viện `python-docx`.
    """
    if docx is None:
        raise ImportError(
            "Không tìm thấy thư viện `python-docx`. "
            "Hãy cài đặt bằng: pip install python-docx"
        ) from _import_error

    document = docx.Document(path)

    # Duyệt lần lượt các block trong thân tài liệu (đoạn/bảng)
    # để giữ nguyên thứ tự xuất hiện.
    body = document.element.body

    def iter_block_items() -> Iterable[Union["docx.text.paragraph.Paragraph", "docx.table.Table"]]:
        for child in body.iterchildren():
            if child.tag.endswith("}p"):
                yield docx.text.paragraph.Paragraph(child, document)
            elif child.tag.endswith("}tbl"):
                yield docx.table.Table(child, document)

    lines: List[str] = []

    for block in iter_block_items():
        # Đoạn văn thường
        if isinstance(block, docx.text.paragraph.Paragraph):
            text = (block.text or "").strip()
            if text:
                lines.append(text)
            continue

        # Bảng -> "tên cột: giá trị; ..."
        if isinstance(block, docx.table.Table):
            rows = list(block.rows)
            if not rows:
                continue

            raw_headers = [c.text.strip() for c in rows[0].cells]
            headers: List[str] = []
            for idx, h in enumerate(raw_headers):
                if h:
                    headers.append(h)
                else:
                    headers.append(f"Cột {idx + 1}")

            for row in rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                if not any(cells):
                    continue

                parts: List[str] = []
                for col_idx, value in enumerate(cells):
                    if not value:
                        continue
                    header = headers[col_idx] if col_idx < len(headers) else f"Cột {col_idx + 1}"
                    parts.append(f"{header}: {value}")

                if parts:
                    lines.append("; ".join(parts))

    text = "\n".join(lines)

    # encoding_fallback được giữ cho tương thích chữ ký, không dùng cho docx
    return text


__all__ = ["extract_docx_text"]

