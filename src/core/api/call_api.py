from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from src.config import EMBED_API_URL, RERANK_API_URL, LLM_API_URL

DEFAULT_BASE_URL = LLM_API_URL
DEFAULT_TIMEOUT = 180


def _post_json(
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API {endpoint} failed with status {response.status_code}: {detail}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Cannot call API {endpoint} at {url}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"API {endpoint} returned invalid JSON") from exc


def call_embed_api(
    texts: List[str],
    base_url: str = EMBED_API_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Goi API /embed.

    Tra ve JSON dang:
    {
        "embeddings": List[List[float]],
        "dimension": int,
        "device": str,
    }
    """
    if not texts:
        raise ValueError("texts must not be empty")

    return _post_json(
        base_url=base_url,
        endpoint="/embed",
        payload={"texts": texts},
        timeout=timeout,
    )


def call_generate_api(
    prompt: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    max_length: int = 200,
    temperature: float = 0.7,
    base_url: str = LLM_API_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Goi API /generate bang prompt hoac messages.

    Tra ve JSON dang:
    {
        "prompt": str,
        "messages": List[dict],
        "answer": str,
        "device": str,
    }
    """
    if prompt is None and messages is None:
        raise ValueError("Either prompt or messages must be provided")
    if prompt is not None and messages is not None:
        raise ValueError("Only one of prompt or messages can be provided")

    payload: Dict[str, Any] = {
        "max_length": max_length,
        "temperature": temperature,
    }
    if messages is not None:
        payload["messages"] = messages
    if prompt is not None:
        payload["prompt"] = prompt

    return _post_json(
        base_url=base_url,
        endpoint="/generate",
        payload=payload,
        timeout=timeout,
    )


def call_rerank_api(
    query: str,
    documents: List[str],
    top_k: int = 5,
    base_url: str = RERANK_API_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Goi API /rerank.

    Tra ve JSON dang:
    {
        "query": str,
        "results": [
            {"rank": int, "index": int, "document": str, "score": float}
        ],
        "device": str,
    }
    """
    if not query:
        raise ValueError("query must not be empty")
    if not documents:
        raise ValueError("documents must not be empty")

    return _post_json(
        base_url=base_url,
        endpoint="/rerank",
        payload={
            "query": query,
            "documents": documents,
            "top_k": top_k,
        },
        timeout=timeout,
    )
