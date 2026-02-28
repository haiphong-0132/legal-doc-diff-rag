"""
Module ingestion: đọc tài liệu (PDF/DOCX) và chuẩn hoá text.

Public API:
- ingest_file(): ingest theo đường dẫn
- select_file_and_ingest(): pop-up chọn file rồi ingest
- main(): entrypoint (chạy trực tiếp module)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docx_loader import extract_docx_text
from interface import PathLike
from pdf_loader import extract_pdf_text
from text_cleaner import clean_text

SUPPORTED_EXTS = {".pdf", ".docx"}


def ingest_file(path: PathLike) -> str:
    """
    Ingestion tài liệu pháp lý: đọc file Word/PDF và làm sạch text.

    - Nếu là .pdf  -> dùng `extract_pdf_text`
    - Nếu là .docx -> dùng `extract_docx_text`
    - Luôn chạy thêm `clean_text`
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        raw = extract_pdf_text(str(file_path))
    elif ext == ".docx":
        raw = extract_docx_text(str(file_path))
    else:
        raise ValueError(f"Định dạng file không được hỗ trợ: {ext} (chỉ hỗ trợ .pdf, .docx)")

    return clean_text(raw)


def select_file_and_ingest() -> str:
    """
    Mở pop-up chọn file (.pdf/.docx), sau đó ingest và trả về text.
    """
    try:
        from tkinter import Tk, filedialog
    except Exception as exc:  # pragma: no cover
        raise ImportError("Không dùng được pop-up chọn file vì thiếu `tkinter`.") from exc

    root = Tk()
    root.withdraw()

    selected = filedialog.askopenfilename(
        title="Chọn tài liệu pháp lý",
        filetypes=[("PDF & Word", "*.pdf *.docx"), ("PDF", "*.pdf"), ("Word", "*.docx")],
    )

    root.destroy()

    if not selected:
        raise RuntimeError("Không có file nào được chọn.")

    return ingest_file(selected)


def main(argv: list[str] | None = None) -> int:
    """
    Entrypoint cho module ingestion.

    - Nếu có `--path` -> ingest file đó
    - Nếu không -> mở pop-up chọn file
    """
    parser = argparse.ArgumentParser(prog="core.ingestion")
    parser.add_argument("--path", type=str, default=None, help="Đường dẫn file .pdf/.docx")
    args = parser.parse_args(argv)

    if args.path:
        text = ingest_file(args.path)
    else:
        text = select_file_and_ingest()

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "extract_docx_text",
    "extract_pdf_text",
    "clean_text",
    "ingest_file",
    "select_file_and_ingest",
    "main",
]

