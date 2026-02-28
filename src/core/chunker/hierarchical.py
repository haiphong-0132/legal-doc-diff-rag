from __future__ import annotations

from typing import List

from src.core.chunker.base import ChunkingStrategy
from src.schemas import ChunkDocument, ChunkMetadata, LegalDocument, Section


class HierarchicalChunker(ChunkingStrategy):
    """Chunk following document hierarchy in the legal JSON schema."""

    def __init__(self) -> None:
        pass

    def chunk(self, document: LegalDocument) -> List[ChunkDocument]:
        chunks: List[ChunkDocument] = []
        doc_id = self._derive_doc_id(document)

        metadata_text = self._build_metadata_text(document)
        if metadata_text:
            chunks.extend(self._emit_text_chunks(metadata_text, f"{doc_id}_metadata"))

        for idx, item in enumerate(document.dinh_nghia, start=1):
            text = f"DINH_NGHIA: {item.tu_khoa} = {item.y_nghia}"
            section_id = f"{doc_id}_dinh_nghia_{idx}"
            chunks.extend(self._emit_text_chunks(text, section_id))

        for section in document.noi_dung_chinh:
            chunks.extend(self._walk_section(section=section, doc_id=doc_id))

        for idx, appendix in enumerate(document.phu_luc, start=1):
            parts = [f"PHU_LUC {idx}"]
            if appendix.tieu_de:
                parts.append(appendix.tieu_de)
            if appendix.noi_dung:
                parts.append(appendix.noi_dung)
            text = "\n".join(parts).strip()
            if text:
                chunks.extend(self._emit_text_chunks(text, f"{doc_id}_phu_luc_{idx}"))

        for idx, item in enumerate(document.khac, start=1):
            if item.noi_dung:
                chunks.extend(
                    self._emit_text_chunks(item.noi_dung, f"{doc_id}_khac_{idx}")
                )

        return chunks

    def _walk_section(self, section: Section, doc_id: str) -> List[ChunkDocument]:
        chunks: List[ChunkDocument] = []
        title = section.tieu_de or ""
        body = section.noi_dung or ""

        parts: List[str] = []
        if title:
            parts.append(f"Tieu_de: {title}")
        if body:
            parts.append(body)

        section_text = "\n".join(parts).strip()
        if section_text:
            chunks.extend(self._emit_text_chunks(section_text, f"{doc_id}_{section.id}"))

        for child in section.con:
            chunks.extend(self._walk_section(section=child, doc_id=doc_id))

        return chunks

    def _build_metadata_text(self, document: LegalDocument) -> str:
        lines: List[str] = []
        meta = document.metadata

        for label, value in (
            ("Quoc_hieu", meta.quoc_hieu),
            ("Tieu_ngu", meta.tieu_ngu),
            ("Ten_van_ban", meta.ten_van_ban),
            ("So_hieu", meta.so_hieu),
            ("Ngay_ky", meta.ngay_ky),
        ):
            if value:
                lines.append(f"{label}: {value}")

        for idx, signer in enumerate(meta.thong_tin_ky_ket, start=1):
            signer_lines = [f"Thong_tin_ky_ket_{idx}"]
            if signer.vai_tro:
                signer_lines.append(f"Vai_tro: {signer.vai_tro}")
            if signer.ghi_chu:
                signer_lines.append(f"Ghi_chu: {signer.ghi_chu}")
            if signer.noi_dung:
                signer_lines.append(signer.noi_dung)
            lines.append("\n".join(signer_lines))

        return "\n".join(lines).strip()

    def _emit_text_chunks(self, text: str, section_id: str) -> List[ChunkDocument]:
        if not text.strip():
            return []
        return [ChunkDocument(text=text, metadata=ChunkMetadata(section_id=section_id))]

    def _derive_doc_id(self, document: LegalDocument) -> str:
        return "HD"
