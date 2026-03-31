from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.matching import PairMatchPipeline, PipelineConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pair matching VB2 -> VB1 using embeddings + rerank + Ollama fallback.")
    parser.add_argument("--vb1", required=True, help="Path to VB1 file (.docx/.pdf).")
    parser.add_argument("--vb2", required=True, help="Path to VB2 file (.docx/.pdf).")

    parser.add_argument("--embedding_model_dir", default="./models/Vietnamese_Embedding_v2")
    parser.add_argument("--reranker_model_dir", default="./models/bge-reranker-v2-m3")

    parser.add_argument("--ollama_url", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--ollama_model", default="qwen3:8b")

    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--distance_threshold", type=float, default=0.185)
    parser.add_argument("--rerank_threshold", type=float, default=0.985)

    parser.add_argument("--chroma_persist", action="store_true", help="Persist Chroma index to disk.")
    parser.add_argument("--chroma_dir", default="./chroma_db", help="Persist directory if --chroma_persist.")
    parser.add_argument("--chroma_collection", default="", help="Collection name (optional).")
    parser.add_argument("--distance_metric", default="ip", choices=["ip", "cosine", "l2"])

    parser.add_argument("--log_level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = PipelineConfig(
        vb1_path=str(Path(args.vb1)),
        vb2_path=str(Path(args.vb2)),
        embedding_model_dir=args.embedding_model_dir,
        reranker_model_dir=args.reranker_model_dir,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        top_k=args.top_k,
        distance_threshold=args.distance_threshold,
        rerank_threshold=args.rerank_threshold,
        chroma_is_persist=bool(args.chroma_persist),
        chroma_persist_directory=args.chroma_dir,
        chroma_distance_metric=args.distance_metric,
        chroma_collection_name=args.chroma_collection.strip() or None,
    )

    out_path = PairMatchPipeline(config).run()
    print(f"Done. Report saved to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

