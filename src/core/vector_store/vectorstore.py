from typing import List, Callable
from pydantic import BaseModel
from src.schemas import ChunkDocument, EmbeddingResult, ChromaUpsertRequest
from src.core.vector_store.chroma_store import ChromaStore

class VectorStorePipeline(BaseModel):
    """Pipeline để lưu trữ vector vào ChromaDB"""
    chunks: List[ChunkDocument]
    embeddings: List[EmbeddingResult]

    def _to_upsert_requests(self) -> List[ChromaUpsertRequest]:
        """Kết nối giữa ChunkDocument và EmbeddingResult để tạo dữ liệu upsert cho ChromaDB"""

        embedding_map = {}
        for e in self.embeddings:
            if e.chunk_id in embedding_map:
             raise ValueError(f"Duplicate chunk_id detected in embeddings: {e.chunk_id}")
            embedding_map[e.chunk_id] = e

        requests = []
        missing_chunk_ids = []

        for chunk in self.chunks:
            cid = chunk.metadata.section_id
            if cid not in embedding_map:
                missing_chunk_ids.append(cid)
                continue
                
            requests.append(
                ChromaUpsertRequest(
                    chunk_id=cid,
                    vector=embedding_map[cid].vector,
                    text=chunk.text,
                    metadata={"section_id": cid}  # Có thể thêm thông tin khác nếu cần
                )
            )
        
        if missing_chunk_ids:
            raise ValueError(f"Missing embeddings for chunk IDs: {missing_chunk_ids}")

        return requests
    
    def run(self, store: ChromaStore) -> None:
        """Upsert toàn bộ chunks vào ChromaStore"""
        requests = self._to_upsert_requests()
        store.upsert(requests)