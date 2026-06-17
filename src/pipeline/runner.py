import argparse
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import requests

from src.config import EMBEDDING_MODEL_DIR, RERANKER_MODEL_DIR, VB1_PATH, VB2_PATH, logger
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
from src.schemas import ChangeItem, ChromaConfig, ChunkDocumentForHierarchical, ChunkMetadata, ChunkRecord, EmbeddingResult, MatchResult, PipelineResult


class DummyReranker:
    def __init__(self) -> None:
        logger.warning(
            "RERANKER WARNING: Local reranker weights not found in '%s'. Falling back to DummyReranker (scores = 1.0) to strictly prevent any internet downloads.",
            RERANKER_MODEL_DIR,
        )

    def compute_score(self, pairs: list, normalize: bool = True) -> list[float]:
        return [1.0] * len(pairs)


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
    
    # Kiểm tra nghiêm ngặt sự hiện diện của file cấu hình và file trọng số chính thức
    has_weights = any(
        (model_dir / f).exists()
        for f in ["pytorch_model.bin", "model.safetensors", "model.onnx", "onnx/model.onnx", "tf_model.h5"]
    )
    
    if (model_dir / "config.json").exists() and has_weights:
        return FlagReranker(str(model_dir), use_fp16=use_gpu, devices=device)

    # Nếu không đủ file trọng số local, tuyệt đối không tải từ mạng, trả về DummyReranker
    return DummyReranker()


_TABLE_MARKER_RE = re.compile(r"⟦BANG:(\d+)⟧")


def _strip_table_markers(text: str) -> str:
    if not text:
        return text
    return _TABLE_MARKER_RE.sub("", text).replace("\n\n", "\n").strip()


def _attach_tables(chunks, registry, tables):
    """Gắn HTML bảng gốc vào đúng đoạn (theo marker ⟦BANG:i⟧) rồi xóa marker khỏi text
    để matching/LLM không thấy marker."""
    def collect(text):
        return [int(i) for i in _TABLE_MARKER_RE.findall(text or "") if int(i) < len(tables)]

    for ch in chunks:
        idxs = collect(ch.noi_dung) + collect(ch.tieu_de)
        if idxs:
            seen = set()
            ch.tables = [tables[i] for i in idxs if not (i in seen or seen.add(i))]
        ch.noi_dung = _strip_table_markers(ch.noi_dung)
        ch.tieu_de = _strip_table_markers(ch.tieu_de)

    for node in registry.values():
        for key in ("noi_dung", "cached_merged_text", "tieu_de"):
            if key in node and isinstance(node[key], str):
                idxs = collect(node[key])
                if idxs:
                    node.setdefault("tables", [])
                    for i in idxs:
                        if tables[i] not in node["tables"]:
                            node["tables"].append(tables[i])
                node[key] = _strip_table_markers(node[key])


def _load_chunks(file_path: str) -> tuple[List[ChunkDocumentForHierarchical], dict]:
    logger.info("Ingestion started for %s", file_path)
    text, tables = extract_file(file_path, return_tables=True)
    payload = build_json_tree(text)
    logger.info("Built JSON tree for %s", file_path)

    # 1. Dựng Registry phẳng O(1) và tính sẵn cached_keywords từ dưới lên
    from src.core.chunker.hierarchical import build_node_registry
    registry = build_node_registry(payload)

    from src.config import CHUNK_MAX_TOKENS, CHUNK_BY
    chunks = HierarchicalChunker(max_tokens=CHUNK_MAX_TOKENS, chunk_by=CHUNK_BY).chunk({"payload": payload}, registry=registry)

    # 2. Gắn HTML bảng gốc vào đoạn tương ứng + xóa marker khỏi text
    if tables:
        _attach_tables(chunks, registry, tables)

    logger.info("Loaded %d chunks (%d tables) and built registry with %d nodes from %s", len(chunks), len(tables), len(registry), file_path)
    return chunks, registry


def _embed_chunks(
    chunks: List[ChunkDocumentForHierarchical],
    model: EmbeddingModel | None,
    use_api: bool,
    registry: dict,
) -> List[ChunkRecord]:
    logger.info("Embedding %d chunks", len(chunks))
    pipeline = EmbeddingPipeline(chunk_documents=chunks)
    reqs = pipeline._to_embedding_requests()
    if use_api:
        api_result = call_embed_api([r.text for r in reqs])
        embeddings = [
            EmbeddingResult(
                chunk_id=r.chunk_id,
                text=r.text,
                vector=vector,
                token_count=0,
            )
            for r, vector in zip(reqs, api_result.get("embeddings", []))
        ]
    else:
        assert model is not None
        from src.config import EMBEDDING_BATCH_SIZE
        embeddings = model.embed(reqs, batch_size=EMBEDDING_BATCH_SIZE)

    req_map = {r.chunk_id: r.text for r in reqs if r.chunk_id}
    vec_map = {e.chunk_id: e.vector for e in embeddings if e.chunk_id}

    records = [
        ChunkRecord(
            chunk=c,
            query_text=req_map.get(c.metadata.section_id, ""),
            vector=vec_map.get(c.metadata.section_id),
            cached_keywords=registry.get(c.metadata.section_id.replace("_header", ""), {}).get("cached_keywords", set())
        )
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
    return chunk.tieu_de or chunk.noi_dung or ""


def strip_numbering(text: str) -> str:
    """
    Loại bỏ CHỈ tiền tố đánh số ĐƠN GIẢN (1., a), 1.a) - KHÔNG xóa con số bên trong nội dung (1.614).
    VD: "2. Giá mua bán điện là 1.614" → "Giá mua bán điện là 1.614"
    VD: "a) Điểm a" → "Điểm a"
    """
    if not text:
        return ""
    text = str(text).strip()
    # Regex: Match CHỈ tiền tố:
    # [0-9]{1,2} = 1-2 chữ số (1, 10, 99) - KHÔNG match 1.614 vì [.] được treat là literal
    # [a-z] = chữ cái (a, b, c)
    # Theo sau: optional [.), :, -]
    text = re.sub(
        r'^[\s]*'
        r'(?:điều|khoản|mục|chương|điểm|phần|article|section|clause)?[\s]*'
        r'(?:[0-9]{1,2}|[a-z])'  # CHỈ 1-2 chữ số HOẶC 1 chữ (KHÔNG [.\-] giữa để tránh 1.614)
        r'[\s]*[.):\-]*\s*',
        '',
        text.lower(),
        flags=re.IGNORECASE
    )
    return text.strip()


def get_node_context(node_id: str, registry: dict) -> str:
    """
    Dựng chuỗi bối cảnh phân cấp đầy đủ và chuẩn xác cho bất kỳ mã node nào trong registry.
    """
    clean_id = node_id.replace("_header", "")
    parts = clean_id.split(".")
    
    # 1. Thông tin cấp Điều (luôn là phần tử đầu tiên)
    art_id = parts[0]
    art_node = registry.get(art_id) or {}
    art_title = art_node.get("tieu_de") or art_node.get("noi_dung") or ""
    
    if len(parts) == 1:
        return art_title.strip()
        
    # 2. Thông tin cấp Khoản
    clause_id = f"{parts[0]}.{parts[1]}"
    clause_node = registry.get(clause_id) or {}
    clause_title = clause_node.get("tieu_de") or ""
    clause_content = clause_node.get("noi_dung") or ""
    
    if len(parts) == 2:
        clause_merged = clause_node.get("cached_merged_text") or clause_content
        return f"{art_title}\n{clause_title}:\n{clause_merged}".strip()
        
    # 3. Thông tin cấp Điểm
    point_node = registry.get(clean_id) or {}
    point_title = point_node.get("tieu_de") or ""
    point_content = point_node.get("cached_merged_text") or point_node.get("noi_dung") or ""
    
    return (
        f"{art_title}\n"
        f"{clause_title}: {clause_content}\n"
        f"{point_title}:\n"
        f"{point_content}"
    ).strip()


def run_pipeline(vb1_path: str = VB1_PATH, vb2_path: str = VB2_PATH, on_phase: Any = None) -> PipelineResult:
    start_time = time.time()
    _notify = on_phase or (lambda phase, msg: None)
    logger.info("Pipeline started")

    _notify("loading", "Đang đọc và phân tách văn bản...")
    vb1_chunks, registry_vb1 = _load_chunks(vb1_path)
    vb2_chunks, registry_vb2 = _load_chunks(vb2_path)
    vb1_map = {c.metadata.section_id: c for c in vb1_chunks}
    logger.info("Chunk loading finished: VB1=%d, VB2=%d", len(vb1_chunks), len(vb2_chunks))

    results: List[MatchResult] = []
    matched_vb1, matched_vb2 = set(), set()

    # Phase 0: Exact match
    _notify("phase_0", "Phase 0: So sánh text thô (exact match)...")
    logger.info("Phase 0 started: exact match")
    vb1_raw_map = {re.sub(r"\s+", " ", c.noi_dung or "").strip(): c for c in vb1_chunks}
    for vb2 in vb2_chunks:
        vb2_id = vb2.metadata.section_id
        match = vb1_raw_map.get(re.sub(r"\s+", " ", vb2.noi_dung or "").strip())
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
    use_api: bool = False  # Mặc định dùng local; sẽ được cập nhật nếu Phase 1 chạy

    if rem_vb1 and rem_vb2:
        _notify("phase_1", f"Phase 1: Embedding & matching {len(rem_vb1)}+{len(rem_vb2)} chunks...")
        logger.info(
            "Phase 1 started: embedding/global matching for remaining chunks VB1=%d, VB2=%d",
            len(rem_vb1),
            len(rem_vb2),
        )
        try:
            logger.info("Checking API at %s", f"{DEFAULT_BASE_URL.rstrip('/')}/docs")
            requests.get(f"{DEFAULT_BASE_URL.rstrip('/')}/docs", timeout=3).raise_for_status()
            use_api = True
        except requests.RequestException as exc:
            logger.warning("API Check failed: %s", exc)
            use_api = False

        logger.info("Local API available=%s", use_api)
        model = None if use_api else EmbeddingModel(model_dir=EMBEDDING_MODEL_DIR)
        vb1_records = _embed_chunks(rem_vb1, model, use_api, registry_vb1)
        vb2_records = _embed_chunks(rem_vb2, model, use_api, registry_vb2)
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
            reranker = _init_reranker()

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

    # Phase 2: Progressive Zoom-In & Unified LLM Review (Tối ưu hóa chạy SONG SONG)
    _notify("phase_2", "Phase 2: Lên lịch phân tích LLM...")
    logger.info("Phase 2 started")
    from src.core.matching.llm_review import llm_review_pair, llm_review_single
    from src.core.matching.matcher import match_sub_nodes

    vb2_map = {c.metadata.section_id: c for c in vb2_chunks}
    change_items: List[ChangeItem] = []

    # Khởi tạo danh sách các tác vụ (task) gọi LLM song song
    tasks = []

    # Lọc ra các cặp cần chạy LLM Review thực tế
    reviewable_matches = [
        match for match in results 
        if match.method in {"hungarian_hybrid", "high_confidence_greedy"} and match.vb1_chunk_id and match.vb2_chunk_id
    ]

    from tqdm import tqdm
    for match in tqdm(reviewable_matches, desc="Phase 2: Lập lịch LLM Tasks"):
        vb1_id = match.vb1_chunk_id
        vb2_id = match.vb2_chunk_id
        
        node_dieu_1 = registry_vb1.get(vb1_id)
        node_dieu_2 = registry_vb2.get(vb2_id)
        
        if not node_dieu_1 or not node_dieu_2:
            # Fallback to chunk pair review if registry not found (unlikely)
            vb1_c = vb1_map.get(vb1_id)
            vb2_c = vb2_map.get(vb2_id)
            if vb1_c and vb2_c:
                def cb_dieu_fallback(res, m=match):
                    item, _, _ = res
                    if item is not None:
                        change_items.append(item)
                    else:
                        # LLM coi là giống (kể cả khác đánh số / diễn đạt lại) → giong_nhau_hoan_toan
                        m.method = "raw_exact"
                tasks.append({
                    "func": llm_review_pair,
                    "args": (vb1_c, vb2_c, match.method),
                    "callback": cb_dieu_fallback
                })
            continue

        node_loai = str(node_dieu_1.get("loai") or "").strip().lower()

        # Định nghĩa các callback helper để xử lý kết quả LLM thu được sau song song
        def cb_dieu_intro(res, v1_id=vb1_id, v2_id=vb2_id):
            item, _, _ = res
            if item:
                if not item.vb1_chunk_id:
                    item.vb1_chunk_id = v1_id
                if not item.vb2_chunk_id:
                    item.vb2_chunk_id = v2_id
                change_items.append(item)

        def cb_unmatched_khoan_1(res, v1_id=vb1_id, v2_id=vb2_id):
            item, _ = res
            if item:
                if not item.vb1_chunk_id:
                    item.vb1_chunk_id = v1_id
                if not item.vb2_chunk_id:
                    item.vb2_chunk_id = v2_id
                change_items.append(item)

        def cb_unmatched_khoan_2(res, v1_id=vb1_id, v2_id=vb2_id):
            item, _ = res
            if item:
                if not item.vb1_chunk_id:
                    item.vb1_chunk_id = v1_id
                if not item.vb2_chunk_id:
                    item.vb2_chunk_id = v2_id
                change_items.append(item)

        def cb_matched_khoan(res, v1_id=vb1_id, v2_id=vb2_id):
            item, _, _ = res
            if item:
                if not item.vb1_chunk_id:
                    item.vb1_chunk_id = v1_id
                if not item.vb2_chunk_id:
                    item.vb2_chunk_id = v2_id
                change_items.append(item)

        def cb_khoan_with_diem(res, v1_id=vb1_id, v2_id=vb2_id):
            item, _ = res
            if item:
                if not item.vb1_chunk_id:
                    item.vb1_chunk_id = v1_id
                if not item.vb2_chunk_id:
                    item.vb2_chunk_id = v2_id
                change_items.append(item)

        if node_loai == "dieu":
            khoan_nodes_1 = node_dieu_1.get("con", [])
            khoan_nodes_2 = node_dieu_2.get("con", [])

            if not khoan_nodes_1 and not khoan_nodes_2:
                # Điều không có Khoản -> Chạy LLM Review trực tiếp cho cặp Điều
                vb1_c = vb1_map[vb1_id]
                vb2_c = vb2_map[vb2_id]
                def cb_dieu_no_khoan(res, m=match):
                    item, _, _ = res
                    if item is not None:
                        change_items.append(item)
                    else:
                        # LLM coi là giống (kể cả khác đánh số / diễn đạt lại) → giong_nhau_hoan_toan
                        m.method = "raw_exact"
                tasks.append({
                    "func": llm_review_pair,
                    "args": (vb1_c, vb2_c, match.method),
                    "callback": cb_dieu_no_khoan
                })
                continue

            # Check intro text of the Điều itself
            dieu_intro_1 = re.sub(r"\s+", " ", str(node_dieu_1.get("noi_dung", ""))).strip().lower()
            dieu_intro_2 = re.sub(r"\s+", " ", str(node_dieu_2.get("noi_dung", ""))).strip().lower()
            if dieu_intro_1 and dieu_intro_2 and dieu_intro_1 != dieu_intro_2:
                chunk1 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=node_dieu_1.get("id")),
                    tieu_de=f"{node_dieu_1.get('tieu_de', '')}\n{node_dieu_1.get('noi_dung', '')}".strip(),
                    noi_dung=node_dieu_1.get("noi_dung", ""),
                    ref=node_dieu_1.get("ref", [])
                )
                chunk2 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=node_dieu_2.get("id")),
                    tieu_de=f"{node_dieu_2.get('tieu_de', '')}\n{node_dieu_2.get('noi_dung', '')}".strip(),
                    noi_dung=node_dieu_2.get("noi_dung", ""),
                    ref=node_dieu_2.get("ref", [])
                )
                tasks.append({
                    "func": llm_review_pair,
                    "args": (chunk1, chunk2, "progressive_zoom_in"),
                    "callback": cb_dieu_intro
                })

            # Chạy so khớp các Khoản thuộc Điều này (sử dụng On-The-Fly embedding)
            matched_khoan_pairs, unmatched_khoan_1, unmatched_khoan_2 = match_sub_nodes(
                khoan_nodes_1, khoan_nodes_2, use_api=use_api
            )

            # Đăng ký các Khoản thêm mới/xóa bỏ
            for k1 in unmatched_khoan_1:
                context1 = get_node_context(k1["id"], registry_vb1)
                chunk1 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=k1["id"]),
                    tieu_de=k1.get("noi_dung") or k1.get("tieu_de", ""),
                    noi_dung=context1,
                    ref=k1.get("ref", [])
                )
                tasks.append({
                    "func": llm_review_single,
                    "args": (chunk1, "xoa_bo"),
                    "callback": cb_unmatched_khoan_1
                })
                
            for k2 in unmatched_khoan_2:
                context2 = get_node_context(k2["id"], registry_vb2)
                chunk2 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=k2["id"]),
                    tieu_de=k2.get("noi_dung") or k2.get("tieu_de", ""),
                    noi_dung=context2,
                    ref=k2.get("ref", [])
                )
                tasks.append({
                    "func": llm_review_single,
                    "args": (chunk2, "them_moi"),
                    "callback": cb_unmatched_khoan_2
                })

            # Với các cặp Khoản đã khớp, tiếp tục "Zoom-In" xuống mức ĐIỂM
            for id_khoan_1, id_khoan_2, _ in matched_khoan_pairs:
                node_khoan_1 = registry_vb1.get(id_khoan_1, {})
                node_khoan_2 = registry_vb2.get(id_khoan_2, {})

                # So sánh CHỈ tieu_de (không cached_merged_text) - LOGIC FIX
                tieu_de_1 = strip_numbering(node_khoan_1.get("tieu_de", ""))
                tieu_de_2 = strip_numbering(node_khoan_2.get("tieu_de", ""))
                
                # Nội dung Khoản để check nếu không có tieu_de
                noi_dung_1 = re.sub(r"\s+", " ", str(node_khoan_1.get("noi_dung", ""))).strip().lower()
                noi_dung_2 = re.sub(r"\s+", " ", str(node_khoan_2.get("noi_dung", ""))).strip().lower()
                
                diem_nodes_1 = node_khoan_1.get("con", [])
                diem_nodes_2 = node_khoan_2.get("con", [])
                
                # Bỏ qua hoàn toàn nếu chỉ đánh số khác (numbering-only): noi_dung giống nhưng tiền tố khác
                if noi_dung_1 and noi_dung_2 and not diem_nodes_1 and not diem_nodes_2:
                    # Loại bỏ tiền tố số đơn KHÔNG loại hết con số bên trong
                    noi_dung_1_stripped = strip_numbering(noi_dung_1)
                    noi_dung_2_stripped = strip_numbering(noi_dung_2)
                    if noi_dung_1_stripped == noi_dung_2_stripped and len(noi_dung_1_stripped) > 0:
                        # Nội dung giống nhau (sau loại tiền tố), chỉ đánh số khác → bỏ qua hoàn toàn
                        continue

                # ✅ PHẢI GỌI LLM nếu không có Điểm con để kiểm tra noi_dung (có thể sua_doi)
                # Không được skip chỉ vì tieu_de giống!
                if not diem_nodes_1 and not diem_nodes_2:
                    # Khoản không có Điểm -> Chạy LLM Review cho cặp Khoản (dù tieu_de có giống)
                    context1 = get_node_context(node_khoan_1["id"], registry_vb1)
                    context2 = get_node_context(node_khoan_2["id"], registry_vb2)

                    chunk1 = ChunkDocumentForHierarchical(
                        metadata=ChunkMetadata(section_id=node_khoan_1.get("id")),
                        tieu_de=node_khoan_1.get("noi_dung") or node_khoan_1.get("tieu_de", ""),
                        noi_dung=context1,
                        ref=node_khoan_1.get("ref", [])
                    )
                    chunk2 = ChunkDocumentForHierarchical(
                        metadata=ChunkMetadata(section_id=node_khoan_2.get("id")),
                        tieu_de=node_khoan_2.get("noi_dung") or node_khoan_2.get("tieu_de", ""),
                        noi_dung=context2,
                        ref=node_khoan_2.get("ref", [])
                    )
                    tasks.append({
                        "func": llm_review_pair,
                        "args": (chunk1, chunk2, "progressive_zoom_in"),
                        "callback": cb_matched_khoan
                    })
                    continue

                # Có Điểm con -> Match các Điểm
                matched_diem_pairs, unmatched_diem_1, unmatched_diem_2 = match_sub_nodes(
                    diem_nodes_1, diem_nodes_2, use_api=use_api
                )
                
                # Xử lý các Điểm không khớp (them_moi / xoa_bo)
                for d1 in unmatched_diem_1:
                    context_d1 = get_node_context(d1["id"], registry_vb1)
                    chunk_d1 = ChunkDocumentForHierarchical(
                        metadata=ChunkMetadata(section_id=d1["id"]),
                        tieu_de=d1.get("noi_dung") or d1.get("tieu_de", ""),
                        noi_dung=context_d1,
                        ref=d1.get("ref", [])
                    )
                    tasks.append({
                        "func": llm_review_single,
                        "args": (chunk_d1, "xoa_bo"),
                        "callback": cb_unmatched_khoan_1
                    })

                for d2 in unmatched_diem_2:
                    context_d2 = get_node_context(d2["id"], registry_vb2)
                    chunk_d2 = ChunkDocumentForHierarchical(
                        metadata=ChunkMetadata(section_id=d2["id"]),
                        tieu_de=d2.get("noi_dung") or d2.get("tieu_de", ""),
                        noi_dung=context_d2,
                        ref=d2.get("ref", [])
                    )
                    tasks.append({
                        "func": llm_review_single,
                        "args": (chunk_d2, "them_moi"),
                        "callback": cb_unmatched_khoan_2
                    })
                
                # Xử lý các Điểm khớp: so sánh tieu_de
                for d1_id, d2_id, _ in matched_diem_pairs:
                    d1_node = registry_vb1.get(d1_id, {})
                    d2_node = registry_vb2.get(d2_id, {})
                    
                    # So sánh NỘI DUNG (không phải tieu_de — với Điểm tieu_de chỉ là nhãn "Điểm a").
                    # strip_numbering để cặp chỉ-khác-đánh-số được coi là giống → bỏ qua.
                    d1_content = strip_numbering(re.sub(r"\s+", " ", str(d1_node.get("cached_merged_text") or d1_node.get("noi_dung") or "")).strip())
                    d2_content = strip_numbering(re.sub(r"\s+", " ", str(d2_node.get("cached_merged_text") or d2_node.get("noi_dung") or "")).strip())

                    # LLM review nếu nội dung khác (sửa đổi/paraphrase); giống nhau thì bỏ qua
                    if d1_content != d2_content and (d1_content or d2_content):
                        context_d1 = get_node_context(d1_id, registry_vb1)
                        context_d2 = get_node_context(d2_id, registry_vb2)

                        chunk_d1 = ChunkDocumentForHierarchical(
                            metadata=ChunkMetadata(section_id=d1_id),
                            tieu_de=d1_node.get("noi_dung") or d1_node.get("tieu_de", ""),
                            noi_dung=context_d1,
                            ref=d1_node.get("ref", [])
                        )
                        chunk_d2 = ChunkDocumentForHierarchical(
                            metadata=ChunkMetadata(section_id=d2_id),
                            tieu_de=d2_node.get("noi_dung") or d2_node.get("tieu_de", ""),
                            noi_dung=context_d2,
                            ref=d2_node.get("ref", [])
                        )
                        tasks.append({
                            "func": llm_review_pair,
                            "args": (chunk_d1, chunk_d2, "progressive_zoom_in"),
                            "callback": cb_matched_khoan
                        })

        elif node_loai == "khoan":
            # Điều khoản được so khớp ở cấp Khoản (chunk_by == "khoan")
            diem_nodes_1 = node_dieu_1.get("con", [])
            diem_nodes_2 = node_dieu_2.get("con", [])

            # So sánh CHỈ tieu_de (LOGIC FIX)
            tieu_de_1 = strip_numbering(node_dieu_1.get("tieu_de", ""))
            tieu_de_2 = strip_numbering(node_dieu_2.get("tieu_de", ""))
            
            noi_dung_1 = re.sub(r"\s+", " ", str(node_dieu_1.get("noi_dung", ""))).strip().lower()
            noi_dung_2 = re.sub(r"\s+", " ", str(node_dieu_2.get("noi_dung", ""))).strip().lower()

            # Bỏ qua hoàn toàn nếu chỉ đánh số khác (LOGIC FIX)
            if noi_dung_1 and noi_dung_2 and not diem_nodes_1 and not diem_nodes_2:
                # Loại bỏ tiền tố số đơn KHÔNG loại hết con số bên trong
                noi_dung_1_stripped = strip_numbering(noi_dung_1)
                noi_dung_2_stripped = strip_numbering(noi_dung_2)
                if noi_dung_1_stripped == noi_dung_2_stripped and len(noi_dung_1_stripped) > 0:
                    # Nội dung giống nhau (sau loại tiền tố), chỉ đánh số khác → bỏ qua hoàn toàn
                    continue

            # ✅ PHẢI GỌI LLM nếu không có Điểm con để kiểm tra noi_dung
            if not diem_nodes_1 and not diem_nodes_2:
                # Khoản không có Điểm -> Chạy LLM Review cho cặp Khoản (dù tieu_de có giống)
                context1 = get_node_context(node_dieu_1["id"], registry_vb1)
                context2 = get_node_context(node_dieu_2["id"], registry_vb2)

                chunk1 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=node_dieu_1.get("id")),
                    tieu_de=node_dieu_1.get("noi_dung") or node_dieu_1.get("tieu_de", ""),
                    noi_dung=context1,
                    ref=node_dieu_1.get("ref", [])
                )
                chunk2 = ChunkDocumentForHierarchical(
                    metadata=ChunkMetadata(section_id=node_dieu_2.get("id")),
                    tieu_de=node_dieu_2.get("noi_dung") or node_dieu_2.get("tieu_de", ""),
                    noi_dung=context2,
                    ref=node_dieu_2.get("ref", [])
                )
                tasks.append({
                    "func": llm_review_pair,
                    "args": (chunk1, chunk2, "progressive_zoom_in"),
                    "callback": cb_matched_khoan
                })
            else:
                # Có Điểm con -> Zoom-in thêm một cấp
                    matched_diem_pairs, unmatched_diem_1, unmatched_diem_2 = match_sub_nodes(
                        diem_nodes_1, diem_nodes_2, use_api=use_api
                    )
                    
                    # Xử lý các Điểm không khớp (them_moi / xoa_bo)
                    for d1 in unmatched_diem_1:
                        context_d1 = get_node_context(d1["id"], registry_vb1)
                        chunk_d1 = ChunkDocumentForHierarchical(
                            metadata=ChunkMetadata(section_id=d1["id"]),
                            tieu_de=d1.get("noi_dung") or d1.get("tieu_de", ""),
                            noi_dung=context_d1,
                            ref=d1.get("ref", [])
                        )
                        tasks.append({
                            "func": llm_review_single,
                            "args": (chunk_d1, "xoa_bo"),
                            "callback": cb_unmatched_khoan_1
                        })
                    
                    for d2 in unmatched_diem_2:
                        context_d2 = get_node_context(d2["id"], registry_vb2)
                        chunk_d2 = ChunkDocumentForHierarchical(
                            metadata=ChunkMetadata(section_id=d2["id"]),
                            tieu_de=d2.get("noi_dung") or d2.get("tieu_de", ""),
                            noi_dung=context_d2,
                            ref=d2.get("ref", [])
                        )
                        tasks.append({
                            "func": llm_review_single,
                            "args": (chunk_d2, "them_moi"),
                            "callback": cb_unmatched_khoan_2
                        })
                    
                    # Xử lý các Điểm khớp: so sánh tieu_de
                    for d1_id, d2_id, _ in matched_diem_pairs:
                        d1_node = registry_vb1.get(d1_id, {})
                        d2_node = registry_vb2.get(d2_id, {})
                        
                        # So sánh NỘI DUNG (Điểm có tieu_de chỉ là nhãn "Điểm a"); strip_numbering
                        # để cặp chỉ-khác-đánh-số coi là giống → bỏ qua.
                        d1_content = strip_numbering(re.sub(r"\s+", " ", str(d1_node.get("cached_merged_text") or d1_node.get("noi_dung") or "")).strip())
                        d2_content = strip_numbering(re.sub(r"\s+", " ", str(d2_node.get("cached_merged_text") or d2_node.get("noi_dung") or "")).strip())

                        # LLM review nếu nội dung khác (sửa đổi/paraphrase); giống nhau thì bỏ qua
                        if d1_content != d2_content and (d1_content or d2_content):
                            context_d1 = get_node_context(d1_id, registry_vb1)
                            context_d2 = get_node_context(d2_id, registry_vb2)
                            
                            chunk_d1 = ChunkDocumentForHierarchical(
                                metadata=ChunkMetadata(section_id=d1_id),
                                tieu_de=d1_node.get("noi_dung") or d1_node.get("tieu_de", ""),
                                noi_dung=context_d1,
                                ref=d1_node.get("ref", [])
                            )
                            chunk_d2 = ChunkDocumentForHierarchical(
                                metadata=ChunkMetadata(section_id=d2_id),
                                tieu_de=d2_node.get("noi_dung") or d2_node.get("tieu_de", ""),
                                noi_dung=context_d2,
                                ref=d2_node.get("ref", [])
                            )
                            tasks.append({
                                "func": llm_review_pair,
                                "args": (chunk_d1, chunk_d2, "progressive_zoom_in"),
                                "callback": cb_matched_khoan
                            })

        else:
            # node_loai == "diem" hoặc khác -> So sánh trực tiếp qua llm_review_pair
            context1 = get_node_context(node_dieu_1["id"], registry_vb1)
            context2 = get_node_context(node_dieu_2["id"], registry_vb2)

            chunk1 = ChunkDocumentForHierarchical(
                metadata=ChunkMetadata(section_id=node_dieu_1.get("id")),
                tieu_de=node_dieu_1.get("noi_dung") or node_dieu_1.get("tieu_de", ""),
                noi_dung=context1,
                ref=node_dieu_1.get("ref", [])
            )
            chunk2 = ChunkDocumentForHierarchical(
                metadata=ChunkMetadata(section_id=node_dieu_2.get("id")),
                tieu_de=node_dieu_2.get("noi_dung") or node_dieu_2.get("tieu_de", ""),
                noi_dung=context2,
                ref=node_dieu_2.get("ref", [])
            )
            tasks.append({
                "func": llm_review_pair,
                "args": (chunk1, chunk2, "progressive_zoom_in"),
                "callback": cb_matched_khoan
            })

    unmatched_vb2 = [record.chunk for record in vb2_records if record.chunk.metadata.section_id not in matched_vb2]
    unmatched_vb1 = [record.chunk for record in vb1_records if record.chunk.metadata.section_id not in matched_vb1]

    for chunk in unmatched_vb2:
        def cb_unmatched_vb2(res):
            item, _ = res
            if item:
                change_items.append(item)
        tasks.append({
            "func": llm_review_single,
            "args": (chunk, "them_moi"),
            "callback": cb_unmatched_vb2
        })

    for chunk in unmatched_vb1:
        def cb_unmatched_vb1(res):
            item, _ = res
            if item:
                change_items.append(item)
        tasks.append({
            "func": llm_review_single,
            "args": (chunk, "xoa_bo"),
            "callback": cb_unmatched_vb1
        })

    # THỰC THI GỌI LLM SONG SONG ĐỒNG LOẠT (PARALLEL EXECUTION WITH ASYNC WORKERS)
    if tasks:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        logger.info("Executing %d LLM review tasks in parallel...", len(tasks))
        _notify("phase_2", f"Phase 2: Đang phân tích song song {len(tasks)} điều khoản bằng LLM...")
        
        def task_wrapper(task_item):
            func = task_item["func"]
            args = task_item["args"]
            try:
                return func(*args)
            except Exception as e:
                logger.error("Error running parallel LLM call %s: %s", func.__name__, e)
                return None

        async def run_async_pool():
            loop = asyncio.get_running_loop()
            # Sử dụng 16 luồng song song để đạt tốc độ tối đa
            with ThreadPoolExecutor(max_workers=16) as pool:
                futures = [
                    loop.run_in_executor(pool, task_wrapper, t)
                    for t in tasks
                ]
                return await asyncio.gather(*futures)

        try:
            # Khởi chạy loop async đồng bộ
            results_list = asyncio.run(run_async_pool())
        except RuntimeError:
            # Fallback nếu đang nằm trong một event loop đang chạy của FastAPI
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=16) as executor:
                results_list = list(executor.map(task_wrapper, tasks))

        # Phân phối kết quả thông qua các callbacks
        for task_item, res in zip(tasks, results_list):
            if res is not None:
                task_item["callback"](res)
                
        logger.info("Parallel LLM execution completed! Collected %d change items.", len(change_items))

    # Gộp các ChangeItem trùng lặp về cặp đoạn và phân loại kind
    merged_items = []
    seen = {}
    for item in change_items:
        key = (item.vb1_chunk_id, item.vb2_chunk_id, item.kind)
        if key in seen:
            existing = seen[key]
            if item.summary and item.summary != "LLM khong tra ve ket qua hop le.":
                if existing.summary == "LLM khong tra ve ket qua hop le." or not existing.summary:
                    existing.summary = item.summary
                else:
                    if not existing.summary.endswith(".") and not existing.summary.endswith(";"):
                        existing.summary += "."
                    existing.summary += " " + item.summary
            existing.changes.extend(item.changes)
            if not existing.vb1_excerpt:
                existing.vb1_excerpt = item.vb1_excerpt
            if not existing.vb2_excerpt:
                existing.vb2_excerpt = item.vb2_excerpt
        else:
            seen[key] = item
            merged_items.append(item)
    change_items = merged_items

    # ------------------------------------------------------------------
    # LAN TRUYỀN NGƯỢC TRẠNG THÁI THAY ĐỔI (PROPAGATION)
    # ------------------------------------------------------------------
    # Nếu một phần tử con (ví dụ: Điểm c) có thay đổi thực tế (ChangeItem),
    # thì tất cả các phần tử cha (Khoản, Điều) chứa nó cũng coi như bị thay đổi.
    # Ta thu thập toàn bộ các section_id bị biến động và phả hệ cha của chúng.
    changed_section_ids = set()
    for item in change_items:
        if item.vb1_chunk_id:
            changed_section_ids.add(item.vb1_chunk_id)
            parts = item.vb1_chunk_id.split(".")
            for i in range(1, len(parts) + 1):
                changed_section_ids.add(".".join(parts[:i]))
        if item.vb2_chunk_id:
            changed_section_ids.add(item.vb2_chunk_id)
            parts = item.vb2_chunk_id.split(".")
            for i in range(1, len(parts) + 1):
                changed_section_ids.add(".".join(parts[:i]))

    # Cập nhật nhãn khớp cho MatchResult: Giáng cấp từ 'high_confidence_greedy' hoặc
    # sang 'modified_by_llm' khi có con thay đổi (để không bị tính là khớp 'giống nhau')
    for match in results:
        if match.vb1_chunk_id in changed_section_ids or match.vb2_chunk_id in changed_section_ids:
            if match.method == "high_confidence_greedy":
                match.method = "modified_by_llm"

    raw_exact_count = len([r for r in results if r.method == "raw_exact"])
    high_confidence_greedy_count = len([r for r in results if r.method == "high_confidence_greedy"])
    hungarian_hybrid_count = len([r for r in results if r.method == "hungarian_hybrid"])
    modified_count = len([item for item in change_items if item.kind == "sua_doi"])
    added_count = len([item for item in change_items if item.kind == "them_moi"])
    deleted_count = len([item for item in change_items if item.kind == "xoa_bo"])
    logger.info("Phase 2 finished: llm_items=%d", len(change_items))

    report = render_change_report(change_items)

    logger.info(
        "Pipeline summary: raw_exact=%d greedy=%d hungarian_hybrid=%d llm_items=%d",
        raw_exact_count,
        high_confidence_greedy_count,
        hungarian_hybrid_count,
        len(change_items),
    )
    logger.info("Pipeline Finished in %.2fs.", time.time() - start_time)
    stats = {
        "so_luong_chunk_vb1": len(vb1_chunks),
        "so_luong_chunk_vb2": len(vb2_chunks),
        "giong_nhau_hoan_toan": raw_exact_count,
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
