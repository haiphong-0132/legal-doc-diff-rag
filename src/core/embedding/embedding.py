from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel
from src.schemas import ChunkDocument, ChunkDocumentForHierarchical, EmbeddingRequest, EmbeddingResult
from src.core.embedding import decode_section_id

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[ChunkDocument] | List[ChunkDocumentForHierarchical]

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        if not self.chunk_documents:
            return []
        if isinstance(self.chunk_documents[0], ChunkDocument):
            return [
                EmbeddingRequest(
                    chunk_id=chunk.metadata.section_id,
                    text=f'Nội dung: {self._enrich_text(chunk)}'
                ) for chunk in self.chunk_documents
            ]
        elif isinstance(self.chunk_documents[0], ChunkDocumentForHierarchical):
            requests = []
            for chunk in self.chunk_documents:
                section_id = chunk.metadata.section_id
                
                # Nếu chunk.noi_dung đã đầy đủ ngữ cảnh, ta dùng trực tiếp chunk.noi_dung.
                # Nếu chunk.noi_dung trống (như header chunk), ta dùng chunk.tieu_de làm nội dung.
                main_text = chunk.noi_dung or chunk.tieu_de or ""
                
                texts = [main_text] if main_text else []
                # if chunk.ref:
                #     texts.append('Các viện dẫn: ' + ', '.join(decode_section_id(ref) for ref in chunk.ref))

                requests.append(
                    EmbeddingRequest(
                        chunk_id=section_id,
                        text='\n'.join(texts)
                    )
                )           
            return requests
        else:
            raise ValueError(f"chunk_documents phải là List[ChunkDocument] hoặc List[ChunkDocumentForHierarchical], nhưng nhận {type(self.chunk_documents[0])}")

    def _enrich_text(self, chunk: ChunkDocument) -> str:
        return chunk.text

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)