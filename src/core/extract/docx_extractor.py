import pypandoc
import sys
from pathlib import Path


def extract_docx_text(input_file):
    input_path = Path(input_file)
    # PROJECT_ROOT = Path(__file__).resolve().parents[3]
    # OUTPUT_FILE = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"

    # convert: dùng gfm để ép pipe table (| a | b |), tránh grid table (+---+)
    # vì grid table không render đúng trên GitHub/VS Code
    text = pypandoc.convert_file(
        str(input_path),
        "gfm",
        extra_args=["--wrap=none"],
    )
    # OUTPUT_FILE.write_text(text, encoding="utf-8")
    return text