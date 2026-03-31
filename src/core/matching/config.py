from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineConfig:
    vb1_path: str = "vb1.docx"
    vb2_path: str = "vb2.docx"
    embedding_model_dir: str = "./models/Vietnamese_Embedding_v2"
    reranker_model_dir: str = "./models/bge-reranker-v2-m3"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://127.0.0.1:11434/api/generate"

    top_k: int = 5
    distance_threshold: float = 0.185
    rerank_threshold: float = 0.985

    # Vector store options (for real-data runs)
    chroma_is_persist: bool = False
    chroma_persist_directory: str = "./chroma_db"
    chroma_distance_metric: str = "ip"
    chroma_collection_name: str | None = None

    def validate(self) -> None:
        if self.vb1_path == "PASTE_VB1_PATH" or self.vb2_path == "PASTE_VB2_PATH":
            raise ValueError("Please provide valid VB1_PATH and VB2_PATH.")
        if not Path(self.vb1_path).exists():
            raise FileNotFoundError(f"VB1 not found: {self.vb1_path}")
        if not Path(self.vb2_path).exists():
            raise FileNotFoundError(f"VB2 not found: {self.vb2_path}")

