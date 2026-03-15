from __future__ import annotations

import json
from typing import Any, Dict, List
from pathlib import Path

from src.schemas import (
    ChunkDocumentForHierarchical,
    ChunkMetadata,
    HierarchicalChunkInput,
)
from src.core.chunker.legal_parser import build_json_tree
from src.core.ingestion.extractor import extract_file

class HierarchicalChunker:
    """Chunk raw hierarchical JSON while keeping title, content, refs, and section id."""

    def chunk(
        self,
        data: HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        document = self._validate_input(data)
        chunks: List[ChunkDocumentForHierarchical] = []

        for node in self._get_root_nodes(document):
            chunks.extend(self._walk_node(node=node))

        return chunks

    def _validate_input(
        self,
        data: HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> HierarchicalChunkInput:
        if isinstance(data, HierarchicalChunkInput):
            return data

        if isinstance(data, list):
            return HierarchicalChunkInput(payload=data)

        if isinstance(data, dict) and ("json" in data or "payload" in data):
            return HierarchicalChunkInput.model_validate(data)

        if isinstance(data, dict):
            return HierarchicalChunkInput(payload=data)

        raise TypeError("HierarchicalChunker.chunk expects HierarchicalChunkInput, dict, or list[dict]")

    def _get_root_nodes(self, document: HierarchicalChunkInput) -> List[Dict[str, Any]]:
        if isinstance(document.payload, list):
            return document.payload
        return [document.payload]

    def _walk_node(
        self,
        *,
        node: Dict[str, Any],
    ) -> List[ChunkDocumentForHierarchical]:
        chunks: List[ChunkDocumentForHierarchical] = []

        chunk = self._build_chunk(node=node)
        if chunk is not None:
            chunks.append(chunk)

        for child in self._get_children(node):
            chunks.extend(self._walk_node(node=child))

        return chunks

    def _build_chunk(
        self,
        *,
        node: Dict[str, Any],
    ) -> ChunkDocumentForHierarchical | None:
        node_id = str(node.get("id") or "").strip()
        title = self._as_clean_str(node.get("tieu_de"))
        content = self._as_clean_str(node.get("noi_dung"))
        refs = self._get_refs(node)

        if not any([title, content, refs]):
            return None
        if not node_id:
            raise ValueError("Each hierarchical node must contain a non-empty 'id'")

        metadata = ChunkMetadata(section_id=node_id)

        return ChunkDocumentForHierarchical(
            metadata=metadata,
            tieu_de=title,
            noi_dung=content,
            ref=refs,
        )

    def _get_children(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        children = node.get("con", [])
        if not isinstance(children, list):
            return []
        return [child for child in children if isinstance(child, dict)]

    def _get_refs(self, node: Dict[str, Any]) -> List[str]:
        refs = node.get("ref", [])
        if not isinstance(refs, list):
            return []
        return [str(ref).strip() for ref in refs if str(ref).strip()]

    def _as_clean_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def main() -> int:
    input_path = Path(r"C:\Users\ADMIN\Desktop\luu-ban-nhap-tu-dong-9.pdf")
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw_text = extract_file(str(input_path))
    print(raw_text)
    payload = build_json_tree(raw_text)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    chunks = HierarchicalChunker().chunk({"payload": payload})
    output_path = input_path.with_name(f"{input_path.stem}_chunks.json")
    output_path.write_text(
        json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(chunks)} chunks to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
