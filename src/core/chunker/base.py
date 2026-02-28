from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List

from src.schemas import ChunkDocument, LegalDocument


class ChunkingStrategy(ABC):
    """Common interface for all chunking strategies."""

    @abstractmethod
    def chunk(self, document: LegalDocument) -> List[ChunkDocument]:
        """Split a parsed legal document into chunks."""


# Backward-compatible function signature alias.
ChunkingFunction = Callable[[LegalDocument], List[ChunkDocument]]
