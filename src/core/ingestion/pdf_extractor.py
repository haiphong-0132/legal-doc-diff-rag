import subprocess
import tempfile
import sys
import pypandoc
from pathlib import Path


_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.core.ingestion.text_cleaner import extract_text_from_html

def extract_pdf_text(file_path):
    """Convert PDF to plain text for chunking/embedding.
    
    Process: PDF -> any2md -> Markdown -> Pandoc HTML -> extract text -> output
    
    Args:
        file_path: Path to PDF file
        
    Returns:
        Plain text string (HTML tags removed, ready for LLM)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Convert PDF to Markdown using any2md
        subprocess.run(
            ["any2md", str(file_path), "-o", str(tmpdir_path), "-f"],
            check=True,
        )

        # Get generated markdown file
        md_file = next(tmpdir_path.glob("*.md"))
        raw_text = md_file.read_text(encoding="utf-8")

        # Convert Markdown to HTML using Pandoc
        html = pypandoc.convert_text(
            raw_text,
            to="html",
            format="markdown-fancy_lists",
            extra_args=["--wrap=none", "--strip-comments"],
        )

    # Extract plain text from HTML for chunking/embedding
    text = extract_text_from_html(html)
    return text
