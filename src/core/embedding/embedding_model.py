import os
from typing import Dict, List

import torch
from tqdm import tqdm

from src.schemas import EmbeddingRequest, EmbeddingResult

os.environ["TOKENIZERS_PARALLELISM"] = "true"

_MODEL_CACHE: Dict[str, object] = {}


class EmbeddingModel:
    """
    Embedding model wrapper dùng SentenceTransformer (CPU / GPU tự động).
    Giữ nguyên interface để tương thích với toàn bộ pipeline.
    """

    def __init__(
        self,
        model_dir: str,
        max_length: int = 2048,
        normalize: bool = True,
        **kwargs,  # bỏ qua pooling, onnx_path nếu còn truyền vào
    ):
        self.model_dir = model_dir
        self.max_length = max_length
        self.normalize = normalize

        if model_dir not in _MODEL_CACHE:
            from sentence_transformers import SentenceTransformer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = SentenceTransformer(model_dir, device=device)
            model.max_seq_length = max_length
            _MODEL_CACHE[model_dir] = model
            print(f"Loaded SentenceTransformer from {model_dir} on {device}")

        self._model = _MODEL_CACHE[model_dir]

    def embed(self, requests: List[EmbeddingRequest], batch_size: int = 32) -> List[EmbeddingResult]:
        texts = [r.text for r in requests]
        results: List[EmbeddingResult] = []

        with tqdm(total=(len(texts) + batch_size - 1) // batch_size, desc="Embedding batches", unit="batch") as pbar:
            for i in range(0, len(texts), batch_size):
                batch = texts[i: i + batch_size]
                embeddings = self._model.encode(
                    batch,
                    normalize_embeddings=self.normalize,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                for j, vec in enumerate(embeddings):
                    results.append(
                        EmbeddingResult(
                            chunk_id=requests[i + j].chunk_id,
                            text=requests[i + j].text,
                            vector=vec.astype(float).tolist(),
                            token_count=0,
                        )
                    )
                pbar.update(1)

        return results


OnnxEmbeddingModel = EmbeddingModel
