from pathlib import Path
from typing import List, Tuple

from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
from src.core.vector_store.chroma_store import ChromaStore
from src.schemas import ChromaConfig, ChromaQueryRequest, ChromaQueryResult, EmbeddingRequest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
EMBEDDING_MODEL_DIR = MODELS_DIR / "Vietnamese_Embedding_v2"
RERANKER_MODEL_ID = "AITeamVN/Vietnamese_Reranker"
RERANKER_DIR = MODELS_DIR / "Vietnamese_Reranker"


def create_embedding_model():
    return OnnxEmbeddingModel(model_dir=str(EMBEDDING_MODEL_DIR))


def create_vector_store():
    return ChromaStore(
        ChromaConfig(
            collection_name="test_collection",
            is_persist=True,
            persist_directory=str(PROJECT_ROOT / "chroma_db"),
            distance_metric="ip",
        )
    )


def create_reranker():
    from FlagEmbedding import FlagReranker
    # FlagReranker cần path model local.
    # Nếu đã có snapshot trong `models/Vietnamese_Reranker` thì dùng ngay (không cần `huggingface_hub`).
    if (RERANKER_DIR / "config.json").exists():
        return FlagReranker(str(RERANKER_DIR), use_fp16=True)

    # Nếu chưa có snapshot thì tải từ Hugging Face.
    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise RuntimeError(
            "Missing dependency `huggingface_hub`. Install it (pip install huggingface_hub) "
            "or download the reranker model manually into `models/Vietnamese_Reranker`."
        ) from e

    RERANKER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        model_path = snapshot_download(
            repo_id=RERANKER_MODEL_ID,
            local_dir=str(RERANKER_DIR),
            local_dir_use_symlinks=False,
            local_files_only=True,
        )
    except Exception:
        model_path = snapshot_download(
            repo_id=RERANKER_MODEL_ID,
            local_dir=str(RERANKER_DIR),
            local_dir_use_symlinks=False,
            local_files_only=False,
        )

    return FlagReranker(model_path, use_fp16=True)

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

    def rerank_with_scores(
        self,
        query_text: str,
        results: List[ChromaQueryResult],
    ) -> List[Tuple[ChromaQueryResult, float]]:
        if not results:
            return []

        pairs = [[query_text, r.text] for r in results]
        scores = self.reranker.compute_score(pairs, normalize=True)
        scored = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
        return [(r, float(s)) for r, s in scored]

    def rerank(
        self,
        query_text: str,
        results: List[ChromaQueryResult],
    ) -> List[ChromaQueryResult]:
        return [r for r, _ in self.rerank_with_scores(query_text, results)]

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