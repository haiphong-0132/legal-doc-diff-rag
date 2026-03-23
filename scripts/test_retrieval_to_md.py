from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from src.core.retrieval.retrieval import (
    RetrievalService,
    create_embedding_model,
    create_reranker,
    create_vector_store,
)
from src.schemas import ChromaQueryResult


def _section_id_or_chunk_id(r: ChromaQueryResult) -> str:
    # Thực tế metadata của project đang có key `section_id`.
    md = r.metadata or {}
    section_id = md.get("section_id")
    return str(section_id) if section_id is not None else r.chunk_id


def _format_metadata(md: Dict[str, Any]) -> str:
    if not md:
        return ""
    lines: List[str] = []
    for k, v in md.items():
        # Giữ format giống file mẫu: - `key`: `value`
        lines.append(f"- `{k}`: `{v}`")
    return "\n".join(lines)


def _format_item(index: int, r: ChromaQueryResult, distance: float, rerank_score: float) -> str:
    section_id = _section_id_or_chunk_id(r)
    metadata_md = _format_metadata(r.metadata or {})
    text = (r.text or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    return (
        f"#### {index}. `{section_id}`\n\n"
        f"- **distance**: `{distance}`\n"
        f"- **rerank_score**: `{rerank_score}`\n"
        f"- **metadata**:\n"
        f"{metadata_md}\n"
        f"**text**:\n\n"
        "```\n"
        f"{text}\n"
        "```"
    )


def _render_md(
    query_text: str,
    top_k: int,
    retrieved: List[ChromaQueryResult],
    retrieved_scores: List[float],
    reranked: List[ChromaQueryResult],
    reranked_scores: List[float],
    timestamp: datetime,
) -> str:
    retrieved_blocks: List[str] = []
    for i, (r, s) in enumerate(zip(retrieved, retrieved_scores), start=1):
        retrieved_blocks.append(_format_item(i, r, distance=float(r.distance), rerank_score=float(s)))

    reranked_blocks: List[str] = []
    for i, (r, s) in enumerate(zip(reranked, reranked_scores), start=1):
        reranked_blocks.append(_format_item(i, r, distance=float(r.distance), rerank_score=float(s)))

    ts_display = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return (
        "# Retrieval test output\n"
        "\n"
        f"- **timestamp**: `{ts_display}`\n"
        f"- **query**: `{query_text}`\n"
        f"- **top_k**: `{top_k}`\n"
        "\n"
        "## Retrieved\n"
        "\n"
        + "\n\n".join(retrieved_blocks)
        + "\n"
        "\n"
        "## Reranked\n"
        "\n"
        + "\n\n".join(reranked_blocks)
        + "\n"
    )


def run_retrieval_to_md(query_text: str, top_k: int, output_md_path: Path) -> Path:
    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    embedding_model = create_embedding_model()
    vector_store = create_vector_store()
    reranker = create_reranker()
    service = RetrievalService(embedding_model=embedding_model, vector_store=vector_store, reranker=reranker)

    retrieved = service.retrieve(query_text=query_text, top_k=top_k)

    # Compute rerank scores for the retrieved set (and reuse them to sort).
    pairs: List[List[str]] = [[query_text, r.text] for r in retrieved]
    retrieved_scores = list(reranker.compute_score(pairs, normalize=True))
    scored = sorted(zip(retrieved, retrieved_scores), key=lambda x: x[1], reverse=True)
    reranked = [r for r, _ in scored]
    reranked_scores = [float(s) for _, s in scored]

    now = datetime.now()
    md = _render_md(
        query_text=query_text,
        top_k=top_k,
        retrieved=retrieved,
        retrieved_scores=[float(s) for s in retrieved_scores],
        reranked=reranked,
        reranked_scores=reranked_scores,
        timestamp=now,
    )

    output_md_path.write_text(md, encoding="utf-8")
    return output_md_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--query",
        type=str,
        default="Không yêu cầu Bên B cung cấp báo cáo về các vấn đề phát sinh trong quá trình kinh doanh, cũng như không bắt buộc thực hiện nhập liệu trên các phần mềm như phần mềm quản lý bán hàng, hệ thống tính tiền,… nên Bên A không có cơ sở để theo dõi và giám sát hoạt động kinh doanh của Bên B.",
        help="Query text để truy vấn rerank.",
    )
    parser.add_argument("--top_k", type=int, default=10, help="Số kết quả lấy từ vector search.")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Đường dẫn file md output. Nếu trống thì tự tạo ở outputs/retrieval_YYYYMMDD_HHMMSS.md",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    outputs_dir = project_root / "outputs"

    if args.output.strip():
        output_md_path = Path(args.output.strip())
        if not output_md_path.is_absolute():
            output_md_path = project_root / output_md_path
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_md_path = outputs_dir / f"retrieval_{ts}.md"

    run_retrieval_to_md(query_text=args.query, top_k=args.top_k, output_md_path=output_md_path)
    print(f"Wrote: {output_md_path}")


if __name__ == "__main__":
    main()

