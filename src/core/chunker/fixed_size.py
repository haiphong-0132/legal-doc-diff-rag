from __future__ import annotations

from typing import List
from tqdm import tqdm
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.schemas import ChunkDocument, ChunkMetadata


class FixedSizeChunker:
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

    def _validate_text_input(self, data: str) -> str:
        if not isinstance(data, str):
            raise TypeError("FixedSizeChunker.chunk expects str input")
        return data

    def chunk(self, data: str) -> List[ChunkDocument]:
        raw_text = self._validate_text_input(data)
        pieces = self.splitter.split_text(raw_text)
        result = []
        for idx, piece in enumerate(tqdm(pieces, desc="Splitting text", total=len(pieces))):
            if piece.strip():
                result.append(ChunkDocument(
                    text=piece,
                    metadata=ChunkMetadata(section_id=f'chunk_{idx}')
                ))
        return result
