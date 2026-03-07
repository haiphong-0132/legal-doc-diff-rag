import subprocess
import tempfile
from pathlib import Path

import pypandoc

from text_cleaner import clean_text

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"


def extract_pdf_text(file_path):
    """
    PDF -> any2md -> pandoc normalize -> clean_text -> output.md
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        subprocess.run(
            ["any2md", str(file_path), "-o", str(tmpdir_path), "-f"],
            check=True,
        )

        md_file = next(tmpdir_path.glob("*.md"))
        raw_text = md_file.read_text(encoding="utf-8")

        formatted_text = pypandoc.convert_text(
            raw_text,
            to="gfm",
            format="md",
            extra_args=["--wrap=none", "--strip-comments"],
        )

    cleaned_text = clean_text(formatted_text)
    OUTPUT_FILE.write_text(cleaned_text, encoding="utf-8")