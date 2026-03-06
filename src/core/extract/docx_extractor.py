from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Union

from docling.datamodel.document import DocumentStream
from docling.document_converter import DocumentConverter
from lxml import etree

PathLike = Union[str, Path]

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
MENDELEY_CITATION_XPATH = (
    "//w:sdt[w:sdtPr/w:tag[contains(@w:val,'MENDELEY_CITATION')]]"
)

def _flatten_mendeley_citations(tree: etree._Element) -> None:
    """
    - Đọc cây XML của `document.xml` trong file .docx.
    - Tìm các node SDT mang tag Mendeley, chuyển toàn bộ run con
      ra ngoài node cha, rồi xóa node SDT.
    - Không còn wrapper đặc thù của Mendeley,
      giúp Docling trích xuất nội dung ổn định hơn.
    """
    for sdt in tree.xpath(MENDELEY_CITATION_XPATH, namespaces=WORD_NS):
        parent = sdt.getparent()
        insert_at = parent.index(sdt)
        for run in sdt.xpath(".//w:sdtContent//w:r", namespaces=WORD_NS):
            parent.insert(insert_at, run)
            insert_at += 1
        parent.remove(sdt)


def _build_normalized_docx(docx_path: Path, debug: bool = False) -> BytesIO:
    """
    Đọc .docx, flatten Mendeley citation SDTs ở `document.xml` và trả về
    archive đã chỉnh sửa dạng BytesIO (tức là thành .docx mới đã được làm sạch).
    """
    with zipfile.ZipFile(docx_path, "r") as zf:
        raw_xml = zf.read("word/document.xml")

    tree = etree.fromstring(raw_xml)
    _flatten_mendeley_citations(tree)
    processed_xml = etree.tostring(
        tree,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )

    if debug:
        debug_path = docx_path.with_name(f"{docx_path.stem}_debug.xml")
        debug_path.write_bytes(processed_xml)

    buffer = BytesIO()
    with zipfile.ZipFile(docx_path, "r") as zf_in:
        with zipfile.ZipFile(buffer, "w") as zf_out:
            for entry in zf_in.infolist():
                data = (
                    processed_xml
                    if entry.filename == "word/document.xml"
                    else zf_in.read(entry.filename)
                )
                zf_out.writestr(entry, data)
    buffer.seek(0)
    return buffer


def extract_docx_text(file_path: PathLike) -> str:
    """
    Trích xuất Markdown từ file .docx bằng Docling,
    với bước normalize Mendeley giống nhánh DOCX trong `convert_to_markdown`.
    """
    file_path = Path(file_path)

    normalized_buffer = _build_normalized_docx(file_path)
    stream = DocumentStream(name=file_path.name, stream=normalized_buffer)

    converter = DocumentConverter()
    result = converter.convert(stream)
    return result.document.export_to_markdown()