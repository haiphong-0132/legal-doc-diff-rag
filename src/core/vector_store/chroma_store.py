import chromadb
from typing import List
from src.schemas import ChromaConfig, ChromaUpsertRequest, ChromaQueryRequest, ChromaQueryResult

class ChromaStore:
    def __init__(self, config: ChromaConfig):
        self.config = config
        
        if self.config.persist:
            self.client = chromadb.PersistentClient(path=self.config.persist_directory)
        else:
            self.client = chromadb.EphemeralClient()
        
        self.collection = self.client.get_or_create_collection(
            name=self.config.collection_name,
            metadata={"hnsw:space": self.config.distance_metric}
        )

    def upsert(self, requests: List[ChromaUpsertRequest]) -> None:
        self.collection.upsert(
            ids = [r.chunk_id for r in requests],
            embeddings = [r.vector for r in requests],
            documents = [r.text for r in requests],
            metadatas = [r.metadata for r in requests]
        )

    def query(self, request: ChromaQueryRequest) -> List[ChromaQueryResult]:
        raw = self.collection.query(
            query_embeddings = [request.query_vector],
            n_results = request.top_k,
            include=['documents', 'metadatas', 'distances'],
            **({'where': request.filter} if request.filter else {})
        )
    
        return [
            ChromaQueryResult(
                chunk_id=raw['ids'][0][i],
                text=raw['documents'][0][i],
                metadata=raw['metadatas'][0][i],
                distance=raw['distances'][0][i]
            ) for i in range(len(raw['ids'][0]))
        ]