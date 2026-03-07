"""
- Sửa giá trị `INPUT_PATH`.
- Chạy: `python extractor.py`.
Luồng dữ liệu:
- `extract_file(INPUT_PATH)`:
    - Nếu là .pdf  -> `extract_pdf_text` 
    - Nếu là .docx -> `extract_docx_text`
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Union


PathLike = Union[str, "PathLike"]  # giữ tương thích type-hint os.PathLike


def extract_file(path: PathLike):
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        from pdf_extractor import extract_pdf_text
        extract_pdf_text(str(file_path))
    elif ext == ".docx":
        from docx_extractor import extract_docx_text
        extract_docx_text(str(file_path))
    else:
        raise ValueError(
            f"Định dạng file không được hỗ trợ: {ext} (chỉ hỗ trợ .pdf, .docx)"
        )
    
def main() -> int:
    INPUT_PATH = Path(r"D:\Downloads\hop-dong-kinh-te.pdf")
    extract_file(INPUT_PATH)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

