from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel
from src.schemas import ChunkDocument, ChunkDocumentForHierarchical, EmbeddingRequest, EmbeddingResult
from src.core.embedding import decode_section_id, get_payload_context

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[ChunkDocument] | List[ChunkDocumentForHierarchical]
    
    fully_payload: Optional[Dict[str, Any]] = None

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        print(len(self.chunk_documents))
        if isinstance(self.chunk_documents[0], ChunkDocument):
            return [
                EmbeddingRequest(
                    id=chunk.metadata.section_id,
                    text=f'Nội dung: {self._enrich_text(chunk)}'
                ) for chunk in self.chunk_documents
            ]
        elif isinstance(self.chunk_documents[0], ChunkDocumentForHierarchical):
            requests = []
            for chunk in self.chunk_documents:
                section_id = chunk.metadata.section_id
                texts = []

                if self.full_payload:
                    # Duyet cay JSON tao ra context cho chunk hien tai dua vao section_id:
                    # Text:
                    # Tiêu đề: .....
                    # Tiêu đề Đoạn: ........
                    # Khoản:...
                    #.............
                    pass

                texts.append(f'Mã đoạn: {decode_section_id(section_id)}')
                if chunk.tieu_de:
                    texts.append(f'Tiêu đề: {chunk.tieu_de}')
                if chunk.noi_dung:
                    texts.append(f'Nội dung: {chunk.noi_dung}')
                if chunk.ref:
                    texts.append(f'Các viện dẫn: {
                        ','.join(decode_section_id(ref) for ref in chunk.ref)
                    }')

                requests.append(
                    EmbeddingRequest(
                        chunk_id=section_id,
                        text='\n'.join(texts)
                    )
                )           

            return requests

    def _enrich_text(self, chunk: ChunkDocument) -> str:
        return chunk.text

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)