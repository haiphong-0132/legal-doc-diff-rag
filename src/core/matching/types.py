from dataclasses import dataclass, field
from typing import List, Optional

from src.schemas import ChunkDocumentForHierarchical


@dataclass
class MatchResult:
    vb2_chunk_id: str
    vb1_chunk_id: Optional[str]
    method: str
    distance: Optional[float] = None
    rerank_score: Optional[float] = None
    hybrid_score: Optional[float] = None


@dataclass
class ChunkRecord:
    chunk: ChunkDocumentForHierarchical
    query_text: str = ""
    vector: Optional[List[float]] = None


@dataclass
class ChangeItem:
    kind: str
    vb1_chunk_id: Optional[str] = None
    vb2_chunk_id: Optional[str] = None
    vb1_excerpt: str = ""
    vb2_excerpt: str = ""
    summary: str = ""
    impact: str = ""
    reason: str = ""
    method: str = ""
    important_points: List[str] = field(default_factory=list)
