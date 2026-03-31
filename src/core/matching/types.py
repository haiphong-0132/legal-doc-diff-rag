from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.schemas import ChunkDocumentForHierarchical


@dataclass
class Candidate:
    chunk_id: str
    distance: float
    rerank_score: float


@dataclass
class MatchResult:
    vb2_chunk_id: str
    vb1_chunk_id: Optional[str]
    method: str  # "raw_exact" | "threshold" | "llm" | "unmatched"
    distance: Optional[float]
    rerank_score: Optional[float]
    confidence: Optional[float]
    reason: str


@dataclass
class ChunkRecord:
    source: str  # "VB1" | "VB2"
    chunk: ChunkDocumentForHierarchical
    query_text: str
    vector: List[float]
    matched: bool = False
    matched_to: Optional[str] = None
    match_method: Optional[str] = None

    @property
    def section_id(self) -> str:
        return self.chunk.metadata.section_id

    def set_match(self, target_id: Optional[str], method: str) -> None:
        self.matched = True
        self.matched_to = target_id
        self.match_method = method


UnresolvedItem = Dict[str, Any]

