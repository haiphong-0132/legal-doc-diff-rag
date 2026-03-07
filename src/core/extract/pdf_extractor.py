from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Union

from text_cleaner import clean_text

PathLike = Union[str, Path]


def extract_pdf_text(file_path: PathLike):
    """
    Dùng any2md để chuyển PDF -> Markdown,
    sau đó clean text và ghi ra ile output.
    """
    
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    OUTPUT_FILE = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"
    file_path = Path(file_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["any2md", str(file_path), "-o", tmpdir, "-f"],
            check=True,
        )

        md_file = next(Path(tmpdir).glob("*.md"))
        raw_text = md_file.read_text(encoding="utf-8")

    cleaned_text = clean_text(raw_text)

    OUTPUT_FILE.write_text(cleaned_text, encoding="utf-8")