from __future__ import annotations

from pathlib import Path
from typing import Union

import fitz  # PyMuPDF
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.exceptions import ConversionError

PathLike = Union[str, Path]


def _fallback_extract_pdf_text_pymupdf(file_path: Path) -> str:
    """
    Fallback khi Docling không đọc được PDF: dùng PyMuPDF để lấy text thuần.
    """
    texts: list[str] = []
    with fitz.open(file_path) as doc:
        for page in doc:
            texts.append(page.get_text("text"))
    return "\n\n".join(texts)


def extract_pdf_text(file_path: PathLike) -> str:
    """
    Trích xuất nội dung từ file .pdf, ưu tiên Docling và fallback sang PyMuPDF nếu cần.
    """
    file_path = Path(file_path)
    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        result = converter.convert(file_path)
        return result.document.export_to_markdown()
    except ConversionError:
        return _fallback_extract_pdf_text_pymupdf(file_path)
    except Exception:
        return _fallback_extract_pdf_text_pymupdf(file_path)