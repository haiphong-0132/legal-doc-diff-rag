from __future__ import annotations

from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.chunker.base import ChunkingInput, ChunkingStrategy
from src.schemas import ChunkDocument, FixedSizeChunkInput


class FixedSizeChunker(ChunkingStrategy):
    """Chunk by fixed text length with overlap using LangChain splitter."""

    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        separators: List[str] | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        )

    def chunk(self, data: ChunkingInput | FixedSizeChunkInput) -> List[ChunkDocument]:
        if isinstance(data, FixedSizeChunkInput):
            raw_text = data.text
        elif isinstance(data, str):
            raw_text = data
        else:
            raise TypeError("FixedSizeChunker.chunk expects text input (str)")

        pieces = self.splitter.split_text(raw_text)
        return [ChunkDocument(text=piece) for piece in pieces if piece.strip()]
