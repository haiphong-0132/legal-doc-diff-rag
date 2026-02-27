from typing import List, Callable
from pydantic import BaseModel
from schemas import ChunkDocument, EmbeddingResult, ChromaUpsertRequest


class VectorStorePipeline(BaseModel):
    """Pipeline để lưu trữ vector vào ChromaDB"""
    chunks: List[ChunkDocument]
    embeddings: List[EmbeddingResult]

    def to_upsert_requests(self) -> List[ChromaUpsertRequest]:
        """Kết nối giữa ChunkDocument và EmbeddingResult để tạo dữ liệu upsert cho ChromaDB"""

        embedding_map = {}
        for e in self.embeddings:
            if e.chunk_id in embedding_map:
             raise ValueError(f"Duplicate chunk_id detected in embeddings: {e.chunk_id}")
            embedding_map[e.chunk_id] = e

        requests = []

        for chunk in self.chunks:
            cid = chunk.metadata.section_id
            if cid not in embedding_map:
                continue
                
            requests.append(
                ChromaUpsertRequest(
                    chunk_id=cid,
                    vector=embedding_map[cid].vector,
                    text=chunk.text,
                    metadata={"section_id": cid}  # Có thể thêm thông tin khác nếu cần
                )
            )
        
        return requests 

# Định nghĩa kiểu cho hàm lưu trữ vector vào ChromaDB
VectorStoreFunction = Callable[[VectorStorePipeline], None]