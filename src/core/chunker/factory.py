from src.core.chunker.base import ChunkingStrategy
from src.core.chunker.fixed_size import FixedSizeChunker
from src.core.chunker.hierarchical import HierarchicalChunker


def create_chunker(strategy: str, **kwargs) -> ChunkingStrategy:
    key = strategy.strip().lower()

    if key == "fixed_size":
        return FixedSizeChunker(**kwargs)
    if key == "hierarchical":
        return HierarchicalChunker(**kwargs)

    raise ValueError(
        "Unsupported chunking strategy. Use 'fixed_size' or 'hierarchical'."
    )
