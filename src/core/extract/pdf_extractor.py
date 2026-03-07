from __future__ import annotations

from pathlib import Path
from typing import Union

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from text_cleaner import clean_text

PathLike = Union[str, Path]

def extract_pdf_text(file_path: PathLike) -> str:
    """
    Trích xuất nội dung từ file .pdf bằng Docling
    """
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    file_path = Path(file_path)
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
    result = converter.convert(file_path)
    text = result.document.export_to_markdown()
    cleaned_text = clean_text(text)
    output_file = PROJECT_ROOT / "src" / "core" / "extract" / "output.md"
    output_file.write_text(cleaned_text, encoding="utf-8")
