"""Remote embedding model wrapper that calls FastAPI endpoints."""

from typing import List

import numpy as np
from tqdm import tqdm

from src.schemas import EmbeddingRequest, EmbeddingResult
from .api_client import APIClient


class RemoteEmbeddingModel:
    """
    Embedding model wrapper that calls a remote FastAPI server.
    Compatible with local OnnxEmbeddingModel interface.
    """

    def __init__(
        self,
        api_base_url: str,
        timeout: int = 120,
    ):
        """
        Initialize remote embedding model.

        Args:
            api_base_url: Base URL of the API server (e.g., 'http://127.0.0.1:8000')
            timeout: Request timeout in seconds
        """
        self.api_client = APIClient(api_base_url, timeout=timeout)
        self.model_dir = api_base_url  # Store for logging/debugging
        self.timeout = timeout

        # Test connection
        if not self.api_client.health_check():
            raise RuntimeError(f"Cannot connect to API server at {api_base_url}")

    def embed(
        self,
        requests_list: List[EmbeddingRequest],
        batch_size: int = 32,
    ) -> List[EmbeddingResult]:
        """
        Embed texts by calling remote API.

        Args:
            requests_list: List of EmbeddingRequest objects
            batch_size: Batch size for API calls

        Returns:
            List of EmbeddingResult objects
        """
        if not requests_list:
            return []

        texts = [r.text for r in requests_list]
        results: List[EmbeddingResult] = []

        with tqdm(
            total=(len(texts) + batch_size - 1) // batch_size,
            desc="Embedding batches via API",
            unit="batch",
        ) as pbar:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_requests = requests_list[i : i + batch_size]

                try:
                    response = self.api_client.embed(batch, timeout=self.timeout)
                    embeddings = response.get("embeddings", [])

                    for j, vec in enumerate(embeddings):
                        results.append(
                            EmbeddingResult(
                                chunk_id=batch_requests[j].chunk_id,
                                text=batch_requests[j].text,
                                vector=vec if isinstance(vec, list) else vec.tolist(),
                                token_count=0,
                            )
                        )
                except Exception as e:
                    raise RuntimeError(
                        f"Embedding failed for batch {i}-{i + len(batch)}: {str(e)}"
                    ) from e

                pbar.update(1)

        return results

    def close(self) -> None:
        """Close the API client and release resources."""
        self.api_client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
