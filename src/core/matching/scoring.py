import difflib
import re

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


def get_title_sim(title_a: str, title_b: str) -> float:
    try:
        from thefuzz import fuzz

        return fuzz.token_sort_ratio(title_a or "", title_b or "") / 100.0
    except ImportError:
        return difflib.SequenceMatcher(None, str(title_a or "").lower(), str(title_b or "").lower()).ratio()


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
    return 0.40 * s_embed + 0.25 * s_title + 0.15 * s_pos + 0.20 * s_lex
