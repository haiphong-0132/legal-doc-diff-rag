import argparse
import json
import time
from types import SimpleNamespace
from typing import Any, List

import requests

from src.config import EMBEDDING_MODEL_DIR, VB1_PATH, VB2_PATH, logger
from src.core.chunker.hierarchical import HierarchicalChunker
from src.core.chunker.legal_parser import build_json_tree
from src.core.api.call_api import DEFAULT_BASE_URL, call_embed_api, call_rerank_api
from src.core.embedding.embedding import EmbeddingPipeline
from src.core.embedding.embedding_model import EmbeddingModel
from src.core.ingestion.extractor import extract_file
from src.core.matching.chunk_formatter import format_chunk
from src.core.matching.llm_review import llm_review_pair, llm_review_single
from src.core.matching.matcher import build_global_matches
from src.core.matching.reporting import render_change_report
from src.core.retrieval.retrieval import RetrievalService, create_reranker
from src.core.vector_store.chroma_store import ChromaStore
from src.core.vector_store.vectorstore import VectorStorePipeline
from src.schemas import ChangeItem, ChromaConfig, ChunkDocumentForHierarchical, ChunkRecord, EmbeddingResult, MatchResult, PipelineResult


def _load_chunks(file_path: str) -> List[ChunkDocumentForHierarchical]:
    logger.info("Ingestion started for %s", file_path)
    payload = build_json_tree(extract_file(file_path))
    logger.info("Built JSON tree for %s", file_path)
    chunks = HierarchicalChunker().chunk({"payload": payload})
    logger.info("Loaded %d chunks from %s", len(chunks), file_path)
    return chunks


def _embed_chunks(chunks: List[ChunkDocumentForHierarchical], model: EmbeddingModel | None, use_api: bool) -> List[ChunkRecord]:
    logger.info("Embedding %d chunks", len(chunks))
    pipeline = EmbeddingPipeline(chunk_documents=chunks)
    requests = pipeline._to_embedding_requests()
    if use_api:
        api_result = call_embed_api([request.text for request in requests])
        embeddings = [
            EmbeddingResult(
                chunk_id=request.chunk_id,
                text=request.text,
                vector=vector,
                token_count=0,
            )
            for request, vector in zip(requests, api_result.get("embeddings", []))
        ]
    else:
        assert model is not None
        embeddings = model.embed(requests)

    req_map = {r.chunk_id: r.text for r in requests if r.chunk_id}
    vec_map = {e.chunk_id: e.vector for e in embeddings if e.chunk_id}

    records = [
        ChunkRecord(chunk=c, query_text=req_map.get(c.metadata.section_id, ""), vector=vec_map.get(c.metadata.section_id))
        for c in chunks
    ]
    logger.info("Embedding finished: %d/%d chunks have vectors", sum(1 for record in records if record.vector), len(records))
    return records


def _build_embedding_results(records: List[ChunkRecord]) -> List[EmbeddingResult]:
    results: List[EmbeddingResult] = []
    for record in records:
        if not record.vector:
            continue
        results.append(EmbeddingResult(chunk_id=record.chunk.metadata.section_id, text=record.query_text, vector=record.vector))
    logger.info("Prepared %d embedding results for vector store", len(results))
    return results


def _chunk_content_for_report(chunk: ChunkDocumentForHierarchical) -> str:
    return chunk.noi_dung or chunk.tieu_de or ""



def run_pipeline(vb1_path: str = VB1_PATH, vb2_path: str = VB2_PATH, on_phase: Any = None) -> PipelineResult:
    start_time = time.time()
    _notify = on_phase or (lambda phase, msg: None)
    logger.info("Pipeline started")

    _notify("loading", "Đang đọc và phân tách văn bản...")
    vb1_chunks = _load_chunks(vb1_path)
    vb2_chunks = _load_chunks(vb2_path)
    vb1_map = {c.metadata.section_id: c for c in vb1_chunks}
    logger.info("Chunk loading finished: VB1=%d, VB2=%d", len(vb1_chunks), len(vb2_chunks))

    results: List[MatchResult] = []
    matched_vb1, matched_vb2 = set(), set()

    # Phase 0: Exact match
    _notify("phase_0", "Phase 0: So sánh text thô (exact match)...")
    logger.info("Phase 0 started: exact match")
    vb1_raw_map = {format_chunk(c): c for c in vb1_chunks}
    for vb2 in vb2_chunks:
        vb2_id = vb2.metadata.section_id
        match = vb1_raw_map.get(format_chunk(vb2))
        if match and match.metadata.section_id not in matched_vb1:
            matched_vb1.add(match.metadata.section_id)
            matched_vb2.add(vb2_id)
            results.append(MatchResult(vb2_chunk_id=vb2_id, vb1_chunk_id=match.metadata.section_id, method="raw_exact"))
    logger.info(
        "Phase 0 finished: raw_exact=%d, remaining VB1=%d, remaining VB2=%d",
        len([r for r in results if r.method == "raw_exact"]),
        len(vb1_chunks) - len(matched_vb1),
        len(vb2_chunks) - len(matched_vb2),
    )

    # Phase 1: Embeddings & Hybrid Hungarian matching
    rem_vb1 = [c for c in vb1_chunks if c.metadata.section_id not in matched_vb1]
    rem_vb2 = [c for c in vb2_chunks if c.metadata.section_id not in matched_vb2]
    vb1_records: List[ChunkRecord] = []
    vb2_records: List[ChunkRecord] = []

    if rem_vb1 and rem_vb2:
        _notify("phase_1", f"Phase 1: Embedding & matching {len(rem_vb1)}+{len(rem_vb2)} chunks...")
        logger.info(
            "Phase 1 started: embedding/global matching for remaining chunks VB1=%d, VB2=%d",
            len(rem_vb1),
            len(rem_vb2),
        )
        try:
            requests.get(DEFAULT_BASE_URL, timeout=3).raise_for_status()
            use_api = True
        except requests.RequestException:
            use_api = False

        logger.info("Local API available=%s", use_api)
        model = None if use_api else EmbeddingModel(model_dir=EMBEDDING_MODEL_DIR)
        vb1_records = _embed_chunks(rem_vb1, model, use_api)
        vb2_records = _embed_chunks(rem_vb2, model, use_api)
        vb1_embeddings = _build_embedding_results(vb1_records)

        vector_store = ChromaStore(
            ChromaConfig(collection_name=f"vb1_idx_{int(time.time())}", is_persist=False, distance_metric="ip")
        )
        logger.info("Vector store created: collection=%s", vector_store.config.collection_name)
        VectorStorePipeline(embeddings=vb1_embeddings).run(vector_store, batch_size=32)
        logger.info("Vector store upsert finished: %d embeddings", len(vb1_embeddings))

        if use_api:
            def compute_score(pairs, normalize=True):
                if not pairs:
                    return []
                queries = [pair[0] for pair in pairs]
                documents = [pair[1] for pair in pairs]
                if len(set(queries)) == 1:
                    rerank_result = call_rerank_api(queries[0], documents, top_k=len(documents))
                    scores = [0.0] * len(documents)
                    for item in rerank_result.get("results", []):
                        scores[int(item["index"])] = float(item["score"])
                    return scores
                scores = []
                for query, document in pairs:
                    rerank_result = call_rerank_api(query, [document], top_k=1)
                    results_ = rerank_result.get("results", [])
                    scores.append(float(results_[0]["score"]) if results_ else 0.0)
                return scores

            reranker = SimpleNamespace(compute_score=compute_score)
        else:
            reranker = create_reranker()

        retrieval_service = RetrievalService(
            embedding_model=None,
            vector_store=vector_store,
            reranker=reranker,
        )
        logger.info("Reranker initialized via %s", "api" if use_api else "local model")

        global_matches = build_global_matches(vb1_records, vb2_records, vector_store, retrieval_service)
        results.extend(global_matches)
        for match in global_matches:
            matched_vb1.add(match.vb1_chunk_id)
            matched_vb2.add(match.vb2_chunk_id)

        logger.info(
            "Phase 1 finished: global_matches=%d, remaining VB1=%d, remaining VB2=%d",
            len(global_matches),
            len([record for record in vb1_records if record.chunk.metadata.section_id not in matched_vb1]),
            len([record for record in vb2_records if record.chunk.metadata.section_id not in matched_vb2]),
        )
    else:
        logger.info("Phase 1 skipped: remaining VB1=%d, remaining VB2=%d", len(rem_vb1), len(rem_vb2))

    # Phase 2: LLM per matched pair / addition / deletion
    _notify("phase_2", "Phase 2: LLM phân tích các cặp thay đổi...")
    logger.info("Phase 2 started")
    vb2_map = {c.metadata.section_id: c for c in vb2_chunks}
    change_items: List[ChangeItem] = []
    llm_identical_pairs = 0

    for match in results:
        if match.method != "hungarian_hybrid":
            continue
        if not match.vb1_chunk_id:
            continue
        vb1_c = vb1_map[match.vb1_chunk_id]
        vb2_c = vb2_map[match.vb2_chunk_id]
        item, _ = llm_review_pair(vb1_c, vb2_c, match.method)
        if item is not None:
            change_items.append(item)
        else:
            match.method = "llm_semantic_identical"
            llm_identical_pairs += 1

    unmatched_vb2 = [record.chunk for record in vb2_records if record.chunk.metadata.section_id not in matched_vb2]
    unmatched_vb1 = [record.chunk for record in vb1_records if record.chunk.metadata.section_id not in matched_vb1]

    for chunk in unmatched_vb2:
        item, _ = llm_review_single(chunk, "them_moi")
        change_items.append(item)

    for chunk in unmatched_vb1:
        item, _ = llm_review_single(chunk, "xoa_bo")
        change_items.append(item)

    raw_exact_count = len([r for r in results if r.method == "raw_exact"])
    high_confidence_greedy_count = len([r for r in results if r.method == "high_confidence_greedy"])
    hungarian_hybrid_count = len([r for r in results if r.method == "hungarian_hybrid"])
    high_confidence_total = high_confidence_greedy_count + llm_identical_pairs
    modified_count = len([item for item in change_items if item.kind == "sua_doi"])
    added_count = len([item for item in change_items if item.kind == "them_moi"])
    deleted_count = len([item for item in change_items if item.kind == "xoa_bo"])
    logger.info("Phase 2 finished: llm_items=%d", len(change_items))
    semantic_match_methods = {"high_confidence_greedy", "llm_semantic_identical"}
    semantic_matches = []
    for match in results:
        if match.method not in semantic_match_methods or not match.vb1_chunk_id:
            continue
        vb1_chunk = vb1_map.get(match.vb1_chunk_id)
        vb2_chunk = vb2_map.get(match.vb2_chunk_id)
        if not vb1_chunk or not vb2_chunk:
            continue
        semantic_matches.append(
            {
                "vb1_chunk_id": match.vb1_chunk_id,
                "vb2_chunk_id": match.vb2_chunk_id,
                "vb1_content": _chunk_content_for_report(vb1_chunk),
                "vb2_content": _chunk_content_for_report(vb2_chunk),
                "method": match.method,
                "distance": match.distance,
                "rerank_score": match.rerank_score,
                "hybrid_score": match.hybrid_score,
            }
        )

    report = render_change_report(change_items, semantic_matches=semantic_matches)

    logger.info(
        "Pipeline summary: raw_exact=%d high_conf_total=%d (greedy=%d llm_identical=%d) hungarian_hybrid=%d llm_items=%d",
        raw_exact_count,
        high_confidence_total,
        high_confidence_greedy_count,
        llm_identical_pairs,
        hungarian_hybrid_count,
        len(change_items),
    )
    logger.info("Pipeline Finished in %.2fs.", time.time() - start_time)
    stats = {
        "so_luong_chunk_vb1": len(vb1_chunks),
        "so_luong_chunk_vb2": len(vb2_chunks),
        "giong_nhau_hoan_toan": raw_exact_count,
        "giong_nhau_ngu_nghia": high_confidence_total,
        "sua_doi": modified_count,
        "them_moi": added_count,
        "xoa_bo": deleted_count,
    }
    _notify("done", "Hoàn thành!")
    return PipelineResult(
        report_path=None,
        vb1_chunks=vb1_chunks,
        vb2_chunks=vb2_chunks,
        match_results=results,
        change_items=change_items,
        stats=stats,
        report_text=report,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pair-matching legal diff pipeline.")
    parser.add_argument("--vb1", default=VB1_PATH, help="Path to old legal document.")
    parser.add_argument("--vb2", default=VB2_PATH, help="Path to new legal document.")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    result = run_pipeline(vb1_path=args.vb1, vb2_path=args.vb2)
    print(json.dumps(result.stats, ensure_ascii=False, indent=2))
    print(json.dumps(result.report_text, ensure_ascii=False, indent=2))
