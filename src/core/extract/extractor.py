"""
Cách dùng:
    - Mở file `extractor.py`.
    - Sửa giá trị `INPUT_PATH` ở trên cho trỏ tới tài liệu bạn muốn trích xuất.
    - Chạy: `python extractor.py` (từ thư mục chứa file hoặc thông qua full path).
Luồng dữ liệu:
- `extract_file(INPUT_PATH)`:
    - Nếu là .pdf  -> `extract_pdf_text` 
    - Nếu là .docx -> `extract_docx_text`
    - Sau đó chạy `clean_markdown_text` để chuẩn hóa text.
- Đầu ra: ghi text đã làm sạch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from docx_extractor import extract_docx_text 
from pdf_extractor import extract_pdf_text
from text_cleaner import clean_markdown_text  

SUPPORTED_EXTS = {".pdf", ".docx"}

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# - Điền đường dẫn tuyệt đối hoặc tương đối tới file .pdf/.docx.
INPUT_PATH = Path(r"D:\Downloads\Hindi et al 2025 Retrieval-Augmented_Generation_RAG_in_Legal_Technology_A_Survey.pdf")

PathLike = Union[str, "PathLike"]  # giữ tương thích type-hint os.PathLike


def extract_file(path: PathLike) -> Any:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        text = extract_pdf_text(str(file_path))
    elif ext == ".docx":
        text = extract_docx_text(str(file_path))
    else:
        raise ValueError(
            f"Định dạng file không được hỗ trợ: {ext} (chỉ hỗ trợ .pdf, .docx)"
        )

    cleaned_text = clean_markdown_text(text)
    # output_md_path = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"
    # output_md_path.write_text(cleaned_text, encoding="utf-8")
    return cleaned_text


def main() -> int:
    text = extract_file(INPUT_PATH)
    output_md_path = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"
    output_md_path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

