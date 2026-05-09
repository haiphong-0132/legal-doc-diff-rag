from typing import List, Optional

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

_MATCHER_WORKERS = min(os.cpu_count() or 2, 4)


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
    vector_store: Optional[ChromaStore] = None,
    retrieval_service: Optional[RetrievalService] = None,
    hybrid_threshold: float = HYBRID_THRESHOLD,
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
    if vector_store and retrieval_service:
        logger.info("Pass 1: Bắt đầu tìm kiếm ứng viên (Greedy Match) — %d workers", _MATCHER_WORKERS)
        reranker_lock = threading.Lock()
        rerank_results: dict = {}

        with ThreadPoolExecutor(max_workers=_MATCHER_WORKERS) as executor:
            future_to_id = {
                executor.submit(_pass1_worker, vb2_rec, vector_store, retrieval_service, reranker_lock): vb2_rec.chunk.metadata.section_id
                for vb2_rec in vb2_records
            }
            for future in as_completed(future_to_id):
                try:
                    vb2_id, reranked = future.result()
                    rerank_results[vb2_id] = reranked
                except Exception as exc:
                    vb2_id = future_to_id[future]
                    logger.warning("Pass 1 worker failed for VB2=%s: %s", vb2_id, exc)

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
        if meta["hybrid_score"] >= hybrid_threshold:
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



_EMBED_MODEL = None

def get_embed_model():
    """
    Cache singleton OnnxEmbeddingModel để tránh việc đọc ổ đĩa lặp lại nhiều lần.
    """
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from src.config import EMBEDDING_MODEL_DIR
        from src.core.embedding.embedding_model import OnnxEmbeddingModel
        _EMBED_MODEL = OnnxEmbeddingModel(model_dir=EMBEDDING_MODEL_DIR)
    return _EMBED_MODEL


def match_sub_nodes(
    nodes_1: List[dict],
    nodes_2: List[dict],
) -> tuple[List[tuple[str, str, float]], List[dict], List[dict]]:
    """
    So khớp cục bộ các con (Khoản hoặc Điểm) sử dụng mô hình nhúng On-The-Fly
    và thuật toán Hungarian tối ưu hóa toàn cục.
    """
    if not nodes_1 or not nodes_2:
        return [], nodes_1, nodes_2

    from src.schemas import ChunkRecord, ChunkDocumentForHierarchical, ChunkMetadata

    # 1. Chuyển đổi các dict nodes thành ChunkRecord để đồng bộ dữ liệu
    rec_list_1 = []
    for n1 in nodes_1:
        doc = ChunkDocumentForHierarchical(
            metadata=ChunkMetadata(section_id=str(n1.get("id") or "")),
            tieu_de=n1.get("tieu_de", ""),
            noi_dung=n1.get("noi_dung", ""),
            ref=n1.get("ref", [])
        )
        rec = ChunkRecord(
            chunk=doc,
            query_text=n1.get("noi_dung") or n1.get("tieu_de") or "",
            vector=None,
            cached_keywords=n1.get("cached_keywords", set())
        )
        rec_list_1.append(rec)

    rec_list_2 = []
    for n2 in nodes_2:
        doc = ChunkDocumentForHierarchical(
            metadata=ChunkMetadata(section_id=str(n2.get("id") or "")),
            tieu_de=n2.get("tieu_de", ""),
            noi_dung=n2.get("noi_dung", ""),
            ref=n2.get("ref", [])
        )
        rec = ChunkRecord(
            chunk=doc,
            query_text=n2.get("noi_dung") or n2.get("tieu_de") or "",
            vector=None,
            cached_keywords=n2.get("cached_keywords", set())
        )
        rec_list_2.append(rec)

    # 2. Sinh vector On-The-Fly để giải quyết triệt để vấn đề diễn đạt lại (Paraphrase)
    try:
        from src.schemas import EmbeddingRequest
        reqs_1 = [EmbeddingRequest(chunk_id=r.chunk.metadata.section_id, text=r.query_text) for r in rec_list_1]
        reqs_2 = [EmbeddingRequest(chunk_id=r.chunk.metadata.section_id, text=r.query_text) for r in rec_list_2]
        
        embed_model = get_embed_model()
        vecs_1 = {res.chunk_id: res.vector for res in embed_model.embed(reqs_1)}
        vecs_2 = {res.chunk_id: res.vector for res in embed_model.embed(reqs_2)}
        
        for r in rec_list_1:
            r.vector = vecs_1.get(r.chunk.metadata.section_id)
        for r in rec_list_2:
            r.vector = vecs_2.get(r.chunk.metadata.section_id)
    except (RuntimeError, ValueError) as e:
        logger.warning("Không thể chạy Embedding On-The-Fly cho sub-nodes: %s. Chuyển sang so khớp không vector.", e)

    # 3. Gọi hàm build_global_matches (truyền vector_store=None để bỏ qua Pass 1)
    from src.config import HYBRID_THRESHOLD
    matches = build_global_matches(
        vb1_records=rec_list_1,
        vb2_records=rec_list_2,
        vector_store=None,
        retrieval_service=None,
        hybrid_threshold=HYBRID_THRESHOLD
    )

    matched_pairs = []
    matched_1_ids = set()
    matched_2_ids = set()
    for m in matches:
        matched_pairs.append((m.vb1_chunk_id, m.vb2_chunk_id, m.hybrid_score or 0.0))
        if m.vb1_chunk_id:
            matched_1_ids.add(m.vb1_chunk_id)
        if m.vb2_chunk_id:
            matched_2_ids.add(m.vb2_chunk_id)

    unmatched_1 = [n for n in nodes_1 if n.get("id") not in matched_1_ids]
    unmatched_2 = [n for n in nodes_2 if n.get("id") not in matched_2_ids]

    return matched_pairs, unmatched_1, unmatched_2

