import pypandoc
import sys
from pathlib import Path

from src.core.ingestion.text_cleaner import extract_text_from_html


def extract_docx_text(input_file):
    """Convert DOCX to plain text for chunking/embedding.
    
    Process: DOCX -> Pandoc HTML -> extract text -> output
    
    Args:
        input_file: Path to DOCX file
        
    Returns:
        Plain text string (HTML tags removed, ready for LLM)
    """
    input_path = Path(input_file)
    html = pypandoc.convert_file(
        str(input_path),
        "html",
        extra_args=["--wrap=none"],
    )
    # Extract plain text from HTML for chunking/embedding
    text = extract_text_from_html(html)
    return text