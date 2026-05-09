import difflib
import re
from typing import Optional

import numpy as np

from src.schemas import ChunkRecord


def extract_keywords(text: str) -> set:
    if not text:
        return set()

    numbers = set(re.findall(r"\b\d+\b", text))
    dates = set(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text))
    names = set(re.findall(r"\b[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯ][a-zàáâãèéêìíòóôõùúýăđĩũơư]+\b", text))
    return numbers.union(dates).union(names)


def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return intersection / union if union > 0 else 0.0


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def get_title_sim(title_a: Optional[str], title_b: Optional[str]) -> Optional[float]:
    title_a = _clean_text(title_a)
    title_b = _clean_text(title_b)
    if not title_a or not title_b:
        return None

    try:
        from thefuzz import fuzz

        return fuzz.token_sort_ratio(title_a, title_b) / 100.0
    except ImportError:
        return difflib.SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()


def calculate_hybrid_score(record_a: ChunkRecord, record_b: ChunkRecord, pos_a: int, pos_b: int, n_a: int, n_b: int) -> float:
    v1, v2 = record_a.vector, record_b.vector
    if v1 and v2:
        v1_arr, v2_arr = np.array(v1), np.array(v2)
        norm_v1, norm_v2 = np.linalg.norm(v1_arr), np.linalg.norm(v2_arr)
        if norm_v1 > 0 and norm_v2 > 0:
            s_embed = float(np.dot(v1_arr, v2_arr) / (norm_v1 * norm_v2))
        else:
            s_embed = 0.0
    else:
        s_embed = 0.0

    s_title = get_title_sim(record_a.chunk.tieu_de, record_b.chunk.tieu_de)
    s_pos = 1.0 - abs(pos_a / n_a - pos_b / n_b) if n_a > 0 and n_b > 0 else 0.0
    s_lex = jaccard(extract_keywords(record_a.query_text), extract_keywords(record_b.query_text))

    if s_title is None:
        return 0.50 * s_embed + 0.20 * s_pos + 0.30 * s_lex

    return 0.35 * s_embed + 0.15 * s_title + 0.20 * s_pos + 0.30 * s_lex
