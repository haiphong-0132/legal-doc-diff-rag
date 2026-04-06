from typing import List

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.config import DISTANCE_THRESHOLD, HYBRID_THRESHOLD, RERANK_THRESHOLD, TOP_K, logger
from src.core.matching.scoring import calculate_hybrid_score
from src.schemas import ChunkRecord, MatchResult
from src.core.retrieval.retrieval import RetrievalService
from src.core.vector_store.chroma_store import ChromaStore
from src.schemas import ChromaQueryRequest


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

    logger.info("Pass 1: Bắt đầu tìm kiếm ứng viên (Greedy Match)")
    for vb2_record in vb2_records:
        vb2_id = vb2_record.chunk.metadata.section_id
        if not vb2_record.vector:
            continue

        retrieved = vector_store.query(ChromaQueryRequest(query_vector=vb2_record.vector, top_k=TOP_K))
        reranked = retrieval_service.rerank_with_scores(vb2_record.query_text, retrieved)

        if reranked:
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

    logger.info("Pass 2: Bắt đầu tính ma trận %d x %d cho các chunk còn lại", len(rem_vb2_records), len(rem_vb1_records))
    cost_matrix = np.full((len(rem_vb2_records), len(rem_vb1_records)), 1e6, dtype=float)
    candidate_meta = {}

    for i, vb2_record in enumerate(rem_vb2_records):
        vb2_id = vb2_record.chunk.metadata.section_id
        pos_b = vb2_index[vb2_id]
        for j, vb1_record in enumerate(rem_vb1_records):
            vb1_id = vb1_record.chunk.metadata.section_id
            pos_a = vb1_index[vb1_id]
            hybrid_score = calculate_hybrid_score(vb1_record, vb2_record, pos_a, pos_b, n_a, n_b)
            cost_matrix[i, j] = -hybrid_score
            candidate_meta[(i, j)] = {"hybrid_score": hybrid_score}

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
