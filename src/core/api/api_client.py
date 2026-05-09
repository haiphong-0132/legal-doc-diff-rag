"""HTTP client for calling remote FastAPI endpoints."""

import json
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class APIClient:
    """
    HTTP client wrapper for calling remote NLP API endpoints.
    Includes retry logic and timeout handling.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL of the API server (e.g., 'http://127.0.0.1:8000')
            timeout: Request timeout in seconds
            max_retries: Number of retries on failure
            backoff_factor: Backoff factor for exponential delay between retries
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _post(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send POST request to API endpoint.

        Args:
            endpoint: API endpoint path (e.g., '/embed')
            payload: Request payload dict
            timeout: Optional override for request timeout

        Returns:
            Response JSON as dict

        Raises:
            requests.RequestException: On network/connection errors
            ValueError: On non-200 response status
        """
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.timeout

        try:
            response = self.session.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise requests.RequestException(
                f"API request to {url} failed: {str(e)}"
            ) from e

    def embed(self, texts: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Call /embed endpoint to get embeddings.

        Args:
            texts: List of texts to embed
            timeout: Optional request timeout

        Returns:
            Response dict with 'embeddings', 'dimension', 'device' keys
        """
        return self._post("/embed", {"texts": texts}, timeout)

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 3,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Call /rerank endpoint to rerank documents.

        Args:
            query: Query text
            documents: List of documents to rerank
            top_k: Number of top results to return
            timeout: Optional request timeout

        Returns:
            Response dict with 'results' key containing ranked documents
        """
        return self._post(
            "/rerank",
            {"query": query, "documents": documents, "top_k": top_k},
            timeout,
        )

    def health_check(self, timeout: Optional[int] = None) -> bool:
        """
        Check if API server is healthy.

        Args:
            timeout: Optional request timeout

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.base_url}/",
                timeout=timeout or self.timeout,
            )
            return response.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        """Close the session and release resources."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
