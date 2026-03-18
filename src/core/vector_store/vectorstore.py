from typing import List, Callable
from pydantic import BaseModel
from src.schemas import ChunkDocument, EmbeddingResult, ChromaUpsertRequest
from src.core.vector_store.chroma_store import ChromaStore

class VectorStorePipeline(BaseModel):
    """Pipeline để lưu trữ vector vào ChromaDB"""
    embeddings: List[EmbeddingResult]

    def _to_upsert_requests(self) -> List[ChromaUpsertRequest]:
        """Kết nối với EmbeddingResult để tạo dữ liệu upsert cho ChromaDB"""
        requests: List[ChromaUpsertRequest] = []
        for embedding in self.embeddings:
            if not embedding.chunk_id:
                raise ValueError(f"EmbeddingResult thiếu chunk_id: {embedding}")
            requests.append(
                ChromaUpsertRequest(
                    chunk_id=embedding.chunk_id,
                    text=embedding.text,
                    vector=embedding.vector,
                    metadata={"section_id": embedding.chunk_id} # Có thể thêm thông tin khác nếu cần
                )
            )
        return requests
    
    def run(self, store: ChromaStore, batch_size: int = None) -> None:
        """Upsert toàn bộ chunks vào ChromaStore"""
        requests = self._to_upsert_requests()
        if batch_size:
            store.upsert_batch(requests, batch_size=batch_size)
        else:
            store.upsert(requests)