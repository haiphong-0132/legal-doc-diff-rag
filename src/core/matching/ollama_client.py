from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Dict

from .config import PipelineConfig


def parse_llm_json(raw: str) -> Dict[str, Any]:
    """
    Ollama đôi khi trả thêm text ngoài JSON; ưu tiên bóc JSON object đầu tiên.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return json.loads(raw)


class OllamaClient:
    def __init__(self, config: PipelineConfig):
        self.url = config.ollama_url
        self.model = config.ollama_model

    def generate(self, prompt: str, timeout: int = 180) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("response", "")).strip()

