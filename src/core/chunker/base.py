from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Union

from src.schemas import ChunkDocument, LegalDocument

ChunkingInput = Union[LegalDocument, str]


class ChunkingStrategy(ABC):
    """Common interface for all chunking strategies."""

    @abstractmethod
    def chunk(self, data: ChunkingInput) -> List[ChunkDocument]:
        """Split input into chunks."""


# Backward-compatible function signature alias.
ChunkingFunction = Callable[[ChunkingInput], List[ChunkDocument]]
