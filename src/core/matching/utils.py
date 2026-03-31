from __future__ import annotations

import re
from typing import List, Optional

from src.core.chunker.hierarchical import HierarchicalChunker
from src.core.chunker.legal_parser import build_json_tree
from src.core.ingestion.extractor import extract_file
from src.schemas import ChunkDocumentForHierarchical


def chunk_text_for_display(chunk: Optional[ChunkDocumentForHierarchical]) -> str:
    if not chunk:
        return ""
    parts: List[str] = []
    if chunk.tieu_de:
        parts.append(f"Tieu de: {chunk.tieu_de}")
    if chunk.noi_dung:
        parts.append(f"Noi dung: {chunk.noi_dung}")
    if chunk.ref:
        parts.append(f"Ref: {', '.join(chunk.ref)}")
    return "\n".join(parts).strip()


def chunk_raw_key(chunk: ChunkDocumentForHierarchical) -> str:
    raw = chunk_text_for_display(chunk)
    return re.sub(r"\s+", " ", raw).strip()


def load_hierarchical_chunks(file_path: str) -> List[ChunkDocumentForHierarchical]:
    raw_text = extract_file(file_path)
    payload = build_json_tree(raw_text)
    return HierarchicalChunker().chunk({"payload": payload})

