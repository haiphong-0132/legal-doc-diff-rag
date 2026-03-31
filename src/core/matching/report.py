from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.schemas import ChunkDocumentForHierarchical

from .types import MatchResult
from .utils import chunk_text_for_display


def write_pair_match_report(
    *,
    results: List[MatchResult],
    vb1_map: Dict[str, ChunkDocumentForHierarchical],
    vb2_map: Dict[str, ChunkDocumentForHierarchical],
    vb1_path: str,
    vb2_path: str,
    distance_threshold: float,
    rerank_threshold: float,
    output_dir: str = "results/pair_match",
) -> Path:
    output_path = Path(output_dir) / f"pair_match_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results_sorted = sorted(results, key=lambda x: x.vb2_chunk_id)
    stats = {
        "raw_exact": sum(1 for r in results_sorted if r.method == "raw_exact"),
        "threshold": sum(1 for r in results_sorted if r.method == "threshold"),
        "llm": sum(1 for r in results_sorted if r.method == "llm"),
        "unmatched": sum(1 for r in results_sorted if r.method == "unmatched"),
    }

    lines: List[str] = [
        "# Pair Matching Pipeline Report\n",
        f"- Generated at: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- VB1: `{vb1_path}`",
        f"- VB2: `{vb2_path}`",
        f"- Threshold: distance < `{distance_threshold}` and rerank_score >= `{rerank_threshold}`\n",
        "## Summary\n",
        f"- Total VB2 chunks: `{len(results_sorted)}`",
        f"- Raw exact matches: `{stats['raw_exact']}`",
        f"- Threshold matches: `{stats['threshold']}`",
        f"- LLM matches: `{stats['llm']}`",
        f"- Unmatched: `{stats['unmatched']}`\n",
        "## Details\n",
    ]

    for idx, row in enumerate(results_sorted, start=1):
        vb2_text = chunk_text_for_display(vb2_map.get(row.vb2_chunk_id))
        vb1_text = chunk_text_for_display(vb1_map.get(row.vb1_chunk_id)) if row.vb1_chunk_id else ""

        lines.extend(
            [
                f"### {idx}. VB2 `{row.vb2_chunk_id}` -> VB1 `{row.vb1_chunk_id or 'NONE'}`",
                f"- Method: `{row.method}`",
                f"- Distance: `{row.distance}`" if row.distance is not None else "",
                f"- Rerank score: `{row.rerank_score}`" if row.rerank_score is not None else "",
                f"- Confidence: `{row.confidence}`" if row.confidence is not None else "",
                f"- Reason: {row.reason}\n",
                "VB2 chunk text:\n```text\n" + vb2_text + "\n```\n",
                "VB1 chunk text:\n```text\n" + vb1_text + "\n```\n",
            ]
        )

    lines = [line for line in lines if line]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path

