import pypandoc
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

def extract_docx_text(input_file):
    input_path = Path(input_file)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_file}")
    
    output_file = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"

    # convert: dùng gfm để ép pipe table (| a | b |), tránh grid table (+---+)
    # vì grid table không render đúng trên GitHub/VS Code
    pypandoc.convert_file(
        str(input_path),
        "gfm",
        outputfile=str(output_file),
        extra_args=["--wrap=none"],
    )