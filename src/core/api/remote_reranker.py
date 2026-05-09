"""Remote reranker wrapper that calls FastAPI endpoints."""

from typing import List, Tuple

from src.schemas import ChromaQueryResult
from .api_client import APIClient


class RemoteReranker:
    """
    Reranker wrapper that calls a remote FastAPI server.
    Compatible with local FlagReranker interface.
    """

    def __init__(
        self,
        api_base_url: str,
        timeout: int = 120,
    ):
        """
        Initialize remote reranker.

        Args:
            api_base_url: Base URL of the API server (e.g., 'http://127.0.0.1:8000')
            timeout: Request timeout in seconds
        """
        self.api_client = APIClient(api_base_url, timeout=timeout)
        self.timeout = timeout

        # Test connection
        if not self.api_client.health_check():
            raise RuntimeError(f"Cannot connect to API server at {api_base_url}")

    def compute_score(
        self,
        pairs: List[List[str]],
        normalize: bool = True,
    ) -> List[float]:
        """
        Compute rerank scores for query-document pairs.

        Args:
            pairs: List of [query, document] pairs
            normalize: Whether scores are normalized (affects interpretation only)

        Returns:
            List of scores (one per pair)

        Note:
            The normalize parameter matches FlagReranker interface but is handled
            server-side. Scores returned are already normalized if configured server-side.
        """
        if not pairs:
            return []

        # Extract unique queries and documents
        # For now, assume first element is query for all pairs (common use case)
        if pairs and len(pairs[0]) == 2:
            query = pairs[0][0]
            documents = [pair[1] for pair in pairs]

            try:
                response = self.api_client.rerank(
                    query=query,
                    documents=documents,
                    top_k=len(documents),
                    timeout=self.timeout,
                )

                # Extract scores from results
                # Results are sorted by score descending, map back to original order
                results = response.get("results", [])

                # Create mapping from document to score
                doc_to_score = {r["document"]: r["score"] for r in results}

                # Return scores in original order
                scores = [doc_to_score.get(doc, 0.0) for doc in documents]
                return scores

            except Exception as e:
                raise RuntimeError(
                    f"Reranking failed: {str(e)}"
                ) from e

        raise ValueError("Expected list of [query, document] pairs")

    def rerank_with_scores(
        self,
        query: str,
        documents: List[str],
    ) -> List[Tuple[str, float]]:
        """
        Rerank documents and return with scores.

        Args:
            query: Query text
            documents: List of documents to rerank

        Returns:
            List of (document, score) tuples sorted by score descending
        """
        pairs = [[query, doc] for doc in documents]
        scores = self.compute_score(pairs, normalize=True)

        ranked = sorted(
            zip(documents, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return list(ranked)

    def rerank(
        self,
        query: str,
        documents: List[str],
    ) -> List[str]:
        """
        Rerank documents and return only documents.

        Args:
            query: Query text
            documents: List of documents to rerank

        Returns:
            List of documents sorted by relevance (descending)
        """
        return [doc for doc, _ in self.rerank_with_scores(query, documents)]

    def close(self) -> None:
        """Close the API client and release resources."""
        self.api_client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
