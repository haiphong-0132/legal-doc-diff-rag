from typing import List
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.config import DISTANCE_THRESHOLD, HYBRID_THRESHOLD, RERANK_THRESHOLD, TOP_K, logger
from src.core.matching.scoring import calculate_hybrid_score
from src.schemas import ChunkRecord, MatchResult
from src.core.retrieval.retrieval import RetrievalService
from src.core.vector_store.chroma_store import ChromaStore
from src.schemas import ChromaQueryRequest

_MATCHER_WORKERS = min(os.cpu_count() or 4, 8)


def _pass1_worker(
    vb2_record: ChunkRecord,
    vector_store: ChromaStore,
    retrieval_service: RetrievalService,
    reranker_lock: threading.Lock,
):
    """Query vector store + rerank for one vb2 chunk. Thread-safe."""
    if not vb2_record.vector:
        return vb2_record.chunk.metadata.section_id, []
    retrieved = vector_store.query(ChromaQueryRequest(query_vector=vb2_record.vector, top_k=TOP_K))
    if not retrieved:
        return vb2_record.chunk.metadata.section_id, []
    with reranker_lock:
        reranked = retrieval_service.rerank_with_scores(vb2_record.query_text, retrieved)
    return vb2_record.chunk.metadata.section_id, reranked


def _score_row(
    i: int,
    vb2_record: ChunkRecord,
    rem_vb1_records: List[ChunkRecord],
    vb2_index: dict,
    vb1_index: dict,
    n_a: int,
    n_b: int,
):
    """Compute one cost-matrix row. Thread-safe (numpy releases GIL)."""
    vb2_id = vb2_record.chunk.metadata.section_id
    pos_b = vb2_index[vb2_id]
    row = np.full(len(rem_vb1_records), 1e6, dtype=float)
    meta_row: dict = {}
    for j, vb1_record in enumerate(rem_vb1_records):
        vb1_id = vb1_record.chunk.metadata.section_id
        pos_a = vb1_index[vb1_id]
        hybrid_score = calculate_hybrid_score(vb1_record, vb2_record, pos_a, pos_b, n_a, n_b)
        row[j] = -hybrid_score
        meta_row[j] = {"hybrid_score": hybrid_score}
    return i, row, meta_row


def build_global_matches(
    vb1_records: List[ChunkRecord],
    vb2_records: List[ChunkRecord],
    vector_store: ChromaStore,
    retrieval_service: RetrievalService,
) -> List[MatchResult]:
    if not vb1_records or not vb2_records:
        return []

    matches: List[MatchResult] = []
    matched_vb1 = set()
    matched_vb2 = set()
    n_a = len(vb1_records)
    n_b = len(vb2_records)
    vb1_index = {record.chunk.metadata.section_id: idx for idx, record in enumerate(vb1_records)}
    vb2_index = {record.chunk.metadata.section_id: idx for idx, record in enumerate(vb2_records)}

    # ------------------------------------------------------------------
    # Pass 1: Greedy Match — parallel query+rerank, sequential selection
    # ------------------------------------------------------------------
    logger.info("Pass 1: Bắt đầu tìm kiếm ứng viên (Greedy Match) — %d workers", _MATCHER_WORKERS)
    reranker_lock = threading.Lock()
    rerank_results: dict = {}

    with ThreadPoolExecutor(max_workers=_MATCHER_WORKERS) as executor:
        future_to_id = {
            executor.submit(_pass1_worker, vb2_rec, vector_store, retrieval_service, reranker_lock): vb2_rec.chunk.metadata.section_id
            for vb2_rec in vb2_records
        }
        for future in as_completed(future_to_id):
            vb2_id, reranked = future.result()
            rerank_results[vb2_id] = reranked

    # Greedy selection in original order to preserve determinism
    for vb2_record in vb2_records:
        vb2_id = vb2_record.chunk.metadata.section_id
        reranked = rerank_results.get(vb2_id, [])
        if not reranked:
            continue
        top_item, rerank_score = reranked[0]
        distance = float(top_item.distance)
        rerank_score = float(rerank_score)
        if distance < DISTANCE_THRESHOLD and rerank_score >= RERANK_THRESHOLD and top_item.chunk_id not in matched_vb1:
            matches.append(
                MatchResult(
                    vb2_chunk_id=vb2_id,
                    vb1_chunk_id=top_item.chunk_id,
                    method="high_confidence_greedy",
                    distance=distance,
                    rerank_score=rerank_score,
                )
            )
            matched_vb1.add(top_item.chunk_id)
            matched_vb2.add(vb2_id)
            logger.info(
                "Pass 1 accepted: VB2=%s -> VB1=%s (Dist=%.3f, Rerank=%.3f)",
                vb2_id,
                top_item.chunk_id,
                distance,
                rerank_score,
            )

    rem_vb1_records = [r for r in vb1_records if r.chunk.metadata.section_id not in matched_vb1]
    rem_vb2_records = [r for r in vb2_records if r.chunk.metadata.section_id not in matched_vb2]
    if not rem_vb1_records or not rem_vb2_records:
        return matches

    # ------------------------------------------------------------------
    # Pass 2: Hungarian matching — parallel cost-matrix computation
    # ------------------------------------------------------------------
    logger.info(
        "Pass 2: Bắt đầu tính ma trận %d x %d cho các chunk còn lại — %d workers",
        len(rem_vb2_records), len(rem_vb1_records), _MATCHER_WORKERS,
    )
    cost_matrix = np.full((len(rem_vb2_records), len(rem_vb1_records)), 1e6, dtype=float)
    candidate_meta: dict = {}

    with ThreadPoolExecutor(max_workers=_MATCHER_WORKERS) as executor:
        row_futures = {
            executor.submit(
                _score_row, i, vb2_rec, rem_vb1_records, vb2_index, vb1_index, n_a, n_b
            ): i
            for i, vb2_rec in enumerate(rem_vb2_records)
        }
        for future in as_completed(row_futures):
            i, row, meta_row = future.result()
            cost_matrix[i] = row
            for j, meta in meta_row.items():
                candidate_meta[(i, j)] = meta

    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    for i, j in zip(row_ind.tolist(), col_ind.tolist()):
        meta = candidate_meta.get((i, j))
        if not meta:
            continue
        vb2_id = rem_vb2_records[i].chunk.metadata.section_id
        vb1_id = rem_vb1_records[j].chunk.metadata.section_id
        if meta["hybrid_score"] >= HYBRID_THRESHOLD:
            matches.append(
                MatchResult(
                    vb2_chunk_id=vb2_id,
                    vb1_chunk_id=vb1_id,
                    method="hungarian_hybrid",
                    hybrid_score=meta["hybrid_score"],
                )
            )
            logger.info("Pass 2 accepted: VB2=%s -> VB1=%s (Hybrid Score=%.3f)", vb2_id, vb1_id, meta["hybrid_score"])
        else:
            logger.info(
                "Pass 2 rejected by Hybrid Threshold: VB2=%s -> VB1=%s (Hybrid Score=%.3f)",
                vb2_id,
                vb1_id,
                meta["hybrid_score"],
            )
    return matches
