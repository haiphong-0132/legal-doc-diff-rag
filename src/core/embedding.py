from typing import List, Callable
from pydantic import BaseModel
from src.schemas import ChunkDocument, EmbeddingRequest, EmbeddingResult

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module"""
    chunk_documents: List[ChunkDocument]

    def to_embedding_requests(self) -> List[EmbeddingRequest]:
        return [
            EmbeddingRequest(
                chunk_id=chunk.metadata.section_id,
                text=chunk.text
            ) for chunk in self.chunk_documents
        ]

# Nhận danh sách EmbeddingRequest và trả về danh sách EmbeddingResult
EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]