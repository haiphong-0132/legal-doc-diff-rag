from __future__ import annotations

import argparse
from pathlib import Path

from src.core.chunker.factory import create_chunker
from src.schemas import LegalDocument


def _load_legal_document(input_path: Path) -> LegalDocument:
    raw = input_path.read_text(encoding="utf-8-sig")
    if hasattr(LegalDocument, "model_validate_json"):
        return LegalDocument.model_validate_json(raw)
    return LegalDocument.parse_raw(raw)


def _preview_chunks(name: str, chunks: list, preview_count: int = 3) -> None:
    print(f"\n=== {name} ===")
    print(f"Tong so chunks: {len(chunks)}")

    for idx, chunk in enumerate(chunks[:preview_count], start=1):
        section_id = None
        if getattr(chunk, "metadata", None):
            section_id = chunk.metadata.section_id
        head = chunk.text.replace("\n", " ")[:140]
        print(f"[{idx}] section_id={section_id} | {head}...")


def _print_all_hierarchical_chunks(chunks: list) -> None:
    print("\n=== Hierarchical chunking (full) ===")
    print(f"Tong so chunks: {len(chunks)}")
    for idx, chunk in enumerate(chunks, start=1):
        section_id = None
        if getattr(chunk, "metadata", None):
            section_id = chunk.metadata.section_id
        print(f"\n[{idx}] section_id={section_id}")
        print(chunk.text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test 2 phuong phap chunking (hierarchical + fixed_size) cho LegalDocument JSON"
    )
    parser.add_argument("input_path", help="Duong dan den file JSON dau vao")
    parser.add_argument("--fixed-size", type=int, default=1200, help="chunk_size cho fixed_size")
    parser.add_argument("--fixed-overlap", type=int, default=200, help="chunk_overlap cho fixed_size")
    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Khong tim thay file: {input_path}")

    document = _load_legal_document(input_path)

    hierarchical_chunker = create_chunker("hierarchical")
    fixed_size_chunker = create_chunker(
        "fixed_size",
        chunk_size=args.fixed_size,
        chunk_overlap=args.fixed_overlap,
    )

    hierarchical_chunks = hierarchical_chunker.chunk(document)
    fixed_chunks = fixed_size_chunker.chunk(document)

    _print_all_hierarchical_chunks(hierarchical_chunks)
    _preview_chunks("Fixed-size chunking", fixed_chunks)


if __name__ == "__main__":
    main()
