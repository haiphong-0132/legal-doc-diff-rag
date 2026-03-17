from pathlib import Path
from typing import List, Tuple

from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
from src.core.vector_store.chroma_store import ChromaStore
from src.schemas import ChromaConfig, ChromaQueryRequest, ChromaQueryResult, EmbeddingRequest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
EMBEDDING_MODEL_DIR = MODELS_DIR / "Vietnamese_Embedding_v2"
RERANKER_DIR = MODELS_DIR / "bge-reranker-v2-m3"


def create_embedding_model():
    return OnnxEmbeddingModel(model_dir=str(EMBEDDING_MODEL_DIR))


def create_vector_store():
    return ChromaStore(
        ChromaConfig(
            collection_name="test_collection",
            is_persist=True,
            persist_directory="./chroma_db",
            distance_metric="ip",
        )
    )


def create_reranker():
    from FlagEmbedding import FlagReranker
    return FlagReranker(str(RERANKER_DIR), use_fp16=True)

class RetrievalService:
    def __init__(self, embedding_model, vector_store, reranker):
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.reranker = reranker

    def retrieve(self, query_text: str, top_k: int) -> List[ChromaQueryResult]:
        query_vector = self._embed(query_text)

        return self.vector_store.query(
            ChromaQueryRequest(
                query_vector=query_vector,
                top_k=top_k
            )
        )

    def rerank(
        self,
        query_text: str,
        results: List[ChromaQueryResult]
    ) -> List[ChromaQueryResult]:

        if not results:
            return results

        pairs = [[query_text, r.text] for r in results]
        scores = self.reranker.compute_score(pairs, normalize=True)

        scored = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
        return [r for r, _ in scored]

    def retrieve_and_rerank(
        self,
        query_text: str,
        top_k: int
    ) -> Tuple[List[ChromaQueryResult], List[ChromaQueryResult]]:
        retrieved = self.retrieve(query_text, top_k)
        reranked = self.rerank(query_text, retrieved)
        return retrieved, reranked

    def _embed(self, text: str):
        result = self.embedding_model.embed(
            [EmbeddingRequest(chunk_id=None, text=text)]
        )

        if not result:
            raise ValueError("Embedding failed")

        return result[0].vector