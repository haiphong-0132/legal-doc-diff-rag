from typing import List, Callable
from pydantic import BaseModel
from src.schemas import ChunkDocument, EmbeddingRequest, EmbeddingResult

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[ChunkDocument]

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        return [
            EmbeddingRequest(
                chunk_id=chunk.metadata.section_id,
                text=self._enrich_text(chunk)
            ) for chunk in self.chunk_documents
        ]

    def _enrich_text(self, chunk: ChunkDocument) -> str:
        # Giả sử ta thêm section_id vào đầu text để embedding có thể học được mối liên hệ giữa section_id và nội dung
        return f"{chunk.metadata.section_id}\n\n{chunk.text}"

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)