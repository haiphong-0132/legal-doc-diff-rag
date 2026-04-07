import argparse
import time
from pathlib import Path
from typing import Any, List

from src.config import EMBEDDING_MODEL_DIR, RERANKER_MODEL_DIR, VB1_PATH, VB2_PATH, logger
from src.core.chunker.hierarchical import HierarchicalChunker
from src.core.chunker.legal_parser import build_json_tree
from src.core.embedding.embedding import EmbeddingPipeline
from src.core.embedding.embedding_model import OnnxEmbeddingModel
from src.core.ingestion.extractor import extract_file
from src.core.matching.chunk_formatter import format_chunk
from src.core.matching.llm_review import llm_review_pair, llm_review_single
from src.core.matching.matcher import build_global_matches
from src.core.matching.reporting import render_change_report
from src.core.retrieval.retrieval import RetrievalService, create_reranker
from src.core.vector_store.chroma_store import ChromaStore
from src.core.vector_store.vectorstore import VectorStorePipeline
from src.schemas import ChangeItem, ChromaConfig, ChunkDocumentForHierarchical, ChunkRecord, EmbeddingResult, MatchResult, PipelineResult


def _init_reranker() -> Any:
    model_dir = Path(RERANKER_MODEL_DIR)
    try:
        from FlagEmbedding import FlagReranker
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency `FlagEmbedding`. Please install it in the environment used to run the pipeline."
        ) from exc

    try:
        import torch
        use_gpu = torch.cuda.is_available()
    except ImportError:
        use_gpu = False

    device = "cuda" if use_gpu else "cpu"
    if (model_dir / "config.json").exists():
        return FlagReranker(str(model_dir), use_fp16=use_gpu, devices=device)

    # Fall back to shared retrieval utility (can download/cache model if available).
    return create_reranker()


def _load_chunks(file_path: str) -> List[ChunkDocumentForHierarchical]:
    logger.info("Ingestion started for %s", file_path)
    payload = build_json_tree(extract_file(file_path))
    logger.info("Built JSON tree for %s", file_path)
    chunks = HierarchicalChunker().chunk({"payload": payload})
    logger.info("Loaded %d chunks from %s", len(chunks), file_path)
    return chunks


def _embed_chunks(chunks: List[ChunkDocumentForHierarchical], model: OnnxEmbeddingModel) -> List[ChunkRecord]:
    logger.info("Embedding %d chunks", len(chunks))
    pipeline = EmbeddingPipeline(chunk_documents=chunks)
    requests = pipeline._to_embedding_requests()
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
        model = OnnxEmbeddingModel(model_dir=EMBEDDING_MODEL_DIR)
        vb1_records = _embed_chunks(rem_vb1, model)
        vb2_records = _embed_chunks(rem_vb2, model)
        vb1_embeddings = _build_embedding_results(vb1_records)

        vector_store = ChromaStore(
            ChromaConfig(collection_name=f"vb1_idx_{int(time.time())}", is_persist=False, distance_metric="ip")
        )
        logger.info("Vector store created: collection=%s", vector_store.config.collection_name)
        VectorStorePipeline(embeddings=vb1_embeddings).run(vector_store, batch_size=32)
        logger.info("Vector store upsert finished: %d embeddings", len(vb1_embeddings))

        retrieval_service = RetrievalService(
            embedding_model=None,
            vector_store=vector_store,
            reranker=_init_reranker(),
        )
        logger.info("Reranker initialized")

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

    unmatched_vb2 = [record.chunk for record in vb2_records if record.chunk.metadata.section_id not in matched_vb2]
    unmatched_vb1 = [record.chunk for record in vb1_records if record.chunk.metadata.section_id not in matched_vb1]

    for chunk in unmatched_vb2:
        item, _ = llm_review_single(chunk, "them_moi")
        change_items.append(item)

    for chunk in unmatched_vb1:
        item, _ = llm_review_single(chunk, "xoa_bo")
        change_items.append(item)

    llm_output = render_change_report(change_items)
    logger.info("Phase 2 finished: llm_items=%d", len(change_items))

    # Phase 3: Reporting
    logger.info("Phase 3 started: writing report")

    report = f"""# Báo cáo luồng so khớp pháp lý (Pair Matching Pipeline)
- **VB1 (Cũ):** `{vb1_path}`
- **VB2 (Mới):** `{vb2_path}`

## Thống kê tổng quan:
- **Giống hệt nhau (Raw Exact matches):** {len([r for r in results if r.method == 'raw_exact'])} cặp
- **Giống nhau tin cậy cao (Greedy Vector matches):** {len([r for r in results if r.method == 'high_confidence_greedy'])} cặp
- **Sửa đổi cần phân tích (Hungarian Hybrid matches):** {len([r for r in results if r.method == 'hungarian_hybrid'])} cặp
- **Số lượng yêu cầu đẩy lên LLM:** {len(change_items)} (Gồm các cặp sửa đổi + Các đoạn thêm mới/xóa bỏ)

---
{llm_output}
"""
    logger.info(
        "Phase 3 finished: raw_exact=%d greedy=%d hungarian_hybrid=%d llm_items=%d",
        len([r for r in results if r.method == "raw_exact"]),
        len([r for r in results if r.method == "high_confidence_greedy"]),
        len([r for r in results if r.method == "hungarian_hybrid"]),
        len(change_items),
    )
    logger.info("Pipeline Finished in %.2fs.", time.time() - start_time)
    stats = {
        "raw_exact": len([r for r in results if r.method == "raw_exact"]),
        "high_confidence_greedy": len([r for r in results if r.method == "high_confidence_greedy"]),
        "hungarian_hybrid": len([r for r in results if r.method == "hungarian_hybrid"]),
        "llm_items": len(change_items),
        "vb1_total": len(vb1_chunks),
        "vb2_total": len(vb2_chunks),
        "elapsed_s": round(time.time() - start_time, 2),
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
