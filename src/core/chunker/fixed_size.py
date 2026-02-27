from __future__ import annotations

from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.chunker.base import ChunkingStrategy
from src.schemas import ChunkDocument, LegalDocument


class FixedSizeChunker(ChunkingStrategy):
    """Chunk by fixed text length with overlap using LangChain splitter."""

    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        separators: List[str] | None = None,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        )

    def chunk(self, document: LegalDocument) -> List[ChunkDocument]:
        if hasattr(document, "model_dump_json"):
            raw_text = document.model_dump_json(
                exclude_none=True,
                by_alias=True,
                indent=2,
            )
        else:
            raw_text = document.json(
                ensure_ascii=False,
                exclude_none=True,
                by_alias=True,
                indent=2,
            )
        pieces = self.splitter.split_text(raw_text)
        return [ChunkDocument(text=piece) for piece in pieces if piece.strip()]
