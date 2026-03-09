"""
- Sửa giá trị `INPUT_PATH`.
- Chạy: `python extractor.py`.
Luồng dữ liệu:
- `extract_file(INPUT_PATH)`:
    - Nếu là .pdf  -> `extract_pdf_text` 
    - Nếu là .docx -> `extract_docx_text`
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

def extract_file(path):
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        from src.core.ingestion.pdf_extractor import extract_pdf_text
        return extract_pdf_text(str(file_path))
    elif ext == ".docx":
        from src.core.ingestion.docx_extractor import extract_docx_text
        return extract_docx_text(str(file_path))
    else:
        raise ValueError(
            f"Định dạng file không được hỗ trợ (chỉ hỗ trợ .pdf, .docx)"
        )
    
def main():
    INPUT_PATH = Path(r"D:\PTIT\BTL\TTCS\.temp\tongquan.pdf")
    extract_file(INPUT_PATH)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

