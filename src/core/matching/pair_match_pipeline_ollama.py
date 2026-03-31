import json
import logging
import re
import time
import urllib.request
import difflib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from FlagEmbedding import FlagReranker
from scipy.optimize import linear_sum_assignment

from src.core.chunker.hierarchical import HierarchicalChunker
from src.core.chunker.legal_parser import build_json_tree
from src.core.embedding.embedding import EmbeddingPipeline
from src.core.embedding import decode_section_id
from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
from src.core.ingestion.extractor import extract_file
from src.core.retrieval.retrieval import RetrievalService
from src.core.vector_store.chroma_store import ChromaStore
from src.core.vector_store.vectorstore import VectorStorePipeline
from src.schemas import ChromaConfig, ChromaQueryRequest, ChunkDocumentForHierarchical, EmbeddingResult

# ---------------------------
# CONFIG
# ---------------------------
VB1_PATH = "vb1.docx"
VB2_PATH = "vb2.docx"
EMBEDDING_MODEL_DIR = "./models/Vietnamese_Embedding_v2"
RERANKER_MODEL_DIR = "./models/bge-reranker-v2-m3"
OLLAMA_MODEL = "qwen3:8b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

TOP_K = 8
DISTANCE_THRESHOLD = 0.185     # Dùng cho Pass 1 (Greedy Match)
RERANK_THRESHOLD = 0.985       # Dùng cho Pass 1 (Greedy Match)
HYBRID_THRESHOLD = 0.75        # Dùng cho Pass 2 (Hungarian Hybrid Match) - Điểm lai tổng hợp

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pair_match_pipeline")

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

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def format_chunk(chunk: ChunkDocumentForHierarchical, for_llm: bool = False) -> str:
    if not for_llm:
        raw = f"Tieu de: {chunk.tieu_de or ''}\nNoi dung: {chunk.noi_dung or ''}\nRef: {', '.join(chunk.ref or [])}"
        return re.sub(r"\s+", " ", raw).strip()
    
    ma_doan = chunk.metadata.section_id
    try: ma_doan = decode_section_id(ma_doan)
    except ValueError: pass
    
    noi_dung = chunk.noi_dung or chunk.tieu_de or "(trống)"
    vien_dan = ", ".join([decode_section_id(r) if r else r for r in (chunk.ref or [])]) or "Không có"
    
    return f"Mã đoạn: {ma_doan}\nNội dung: {noi_dung}\nCác viện dẫn: {vien_dan}"

def load_chunks(file_path: str) -> List[ChunkDocumentForHierarchical]:
    logger.info("Ingestion started for %s", file_path)
    payload = build_json_tree(extract_file(file_path))
    logger.info("Built JSON tree for %s", file_path)
    chunks = HierarchicalChunker().chunk({"payload": payload})
    logger.info(f"Loaded {len(chunks)} chunks from {file_path}")
    return chunks

def embed_chunks(chunks: List[ChunkDocumentForHierarchical], model: OnnxEmbeddingModel) -> List[ChunkRecord]:
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

def build_embedding_results(records: List[ChunkRecord]) -> List[EmbeddingResult]:
    results: List[EmbeddingResult] = []
    for record in records:
        if not record.vector:
            continue
        results.append(EmbeddingResult(chunk_id=record.chunk.metadata.section_id, text=record.query_text, vector=record.vector))
    logger.info("Prepared %d embedding results for vector store", len(results))
    return results

def call_ollama(prompt: str) -> str:
    logger.info("Calling Ollama model=%s url=%s prompt_chars=%d", OLLAMA_MODEL, OLLAMA_URL, len(prompt))
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"), 
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        response = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    logger.info("Ollama response received: %d chars", len(response))
    return response

def parse_json_response(raw_text: str) -> Dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))

# ---------------------------
# HYBRID SCORE FUNCTIONS
# ---------------------------
def extract_keywords(text: str) -> set:
    if not text: return set()
    numbers = set(re.findall(r'\b\d+\b', text))
    dates = set(re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text))
    names = set(re.findall(r'\b[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯ][a-zàáâãèéêìíòóôõùúýăđĩũơư]+\b', text))
    return numbers.union(dates).union(names)

def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b: return 0.0
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

# ---------------------------
# GLOBAL MATCHING PIPELINE
# ---------------------------
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

    # === PASS 1: GREEDY MATCH (Ngưỡng tin cậy cao dựa trên Vector & Reranker) ===
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

            if distance < DISTANCE_THRESHOLD and rerank_score >= RERANK_THRESHOLD:
                if top_item.chunk_id not in matched_vb1:
                    matches.append(MatchResult(
                        vb2_chunk_id=vb2_id,
                        vb1_chunk_id=top_item.chunk_id,
                        method="high_confidence_greedy",
                        distance=distance,
                        rerank_score=rerank_score,
                    ))
                    matched_vb1.add(top_item.chunk_id)
                    matched_vb2.add(vb2_id)
                    logger.info("Pass 1 accepted: VB2=%s -> VB1=%s (Dist=%.3f, Rerank=%.3f)", vb2_id, top_item.chunk_id, distance, rerank_score)

    # === PASS 2: HUNGARIAN MATCH (So sánh chéo toàn bộ các chunk còn lại) ===
    rem_vb1_records = [r for r in vb1_records if r.chunk.metadata.section_id not in matched_vb1]
    rem_vb2_records = [r for r in vb2_records if r.chunk.metadata.section_id not in matched_vb2]
    
    if not rem_vb1_records or not rem_vb2_records:
        return matches

    logger.info("Pass 2: Bắt đầu tính ma trận %d x %d cho các chunk còn lại", len(rem_vb2_records), len(rem_vb1_records))
    
    huge_cost = 1e6
    cost_matrix = np.full((len(rem_vb2_records), len(rem_vb1_records)), huge_cost, dtype=float)
    candidate_meta = {}

    for i, vb2_record in enumerate(rem_vb2_records):
        vb2_id = vb2_record.chunk.metadata.section_id
        pos_b = vb2_index[vb2_id]
        
        for j, vb1_record in enumerate(rem_vb1_records):
            vb1_id = vb1_record.chunk.metadata.section_id
            pos_a = vb1_index[vb1_id]
            
            hybrid_score = calculate_hybrid_score(vb1_record, vb2_record, pos_a, pos_b, n_a, n_b)
            
            cost_matrix[i, j] = -hybrid_score
            candidate_meta[(i, j)] = {
                "hybrid_score": hybrid_score
            }

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    for i, j in zip(row_ind.tolist(), col_ind.tolist()):
        meta = candidate_meta.get((i, j))
        if not meta:
            continue
            
        vb2_id = rem_vb2_records[i].chunk.metadata.section_id
        vb1_id = rem_vb1_records[j].chunk.metadata.section_id
        
        if meta["hybrid_score"] >= HYBRID_THRESHOLD:
            matches.append(MatchResult(
                vb2_chunk_id=vb2_id,
                vb1_chunk_id=vb1_id,
                method="hungarian_hybrid",
                distance=None,      
                rerank_score=None,  
                hybrid_score=meta["hybrid_score"]
            ))
            logger.info("Pass 2 accepted: VB2=%s -> VB1=%s (Hybrid Score=%.3f)", vb2_id, vb1_id, meta["hybrid_score"])
        else:
            logger.info("Pass 2 rejected by Hybrid Threshold: VB2=%s -> VB1=%s (Hybrid Score=%.3f)", vb2_id, vb1_id, meta["hybrid_score"])

    return matches

# ---------------------------
# LLM REVIEW FUNCTIONS
# ---------------------------
def llm_review_pair(vb1_chunk: ChunkDocumentForHierarchical, vb2_chunk: ChunkDocumentForHierarchical, method: str) -> ChangeItem:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy so sánh 1 cặp chunk đã được ghép.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "kind": "sua_doi|khong_thay_doi|khong_du_can_cu",
  "summary": "tom tat ngan",
  "impact": "anh huong ngan hoac Chua ro",
  "vb1_excerpt": "trich doan ngan",
  "vb2_excerpt": "trich doan ngan",
  "important_points": ["y 1", "y 2"],
  "reason": "giai thich ngan"
}}

Method ghep cap: {method}

VB1:
{format_chunk(vb1_chunk, True)}

VB2:
{format_chunk(vb2_chunk, True)}
"""
    try:
        data = parse_json_response(call_ollama(prompt))
    except Exception as exc:
        logger.warning("LLM pair review failed for VB1=%s VB2=%s: %s", vb1_chunk.metadata.section_id, vb2_chunk.metadata.section_id, exc)
        return ChangeItem(
            kind="khong_du_can_cu",
            vb1_chunk_id=vb1_chunk.metadata.section_id,
            vb2_chunk_id=vb2_chunk.metadata.section_id,
            vb1_excerpt=vb1_chunk.noi_dung or vb1_chunk.tieu_de or "",
            vb2_excerpt=vb2_chunk.noi_dung or vb2_chunk.tieu_de or "",
            summary="LLM khong tra ve ket qua hop le.",
            impact="Chua ro",
            reason=str(exc),
            method=method,
        )

    return ChangeItem(
        kind=str(data.get("kind", "khong_du_can_cu")).strip().lower(),
        vb1_chunk_id=vb1_chunk.metadata.section_id,
        vb2_chunk_id=vb2_chunk.metadata.section_id,
        vb1_excerpt=str(data.get("vb1_excerpt", "")).strip(),
        vb2_excerpt=str(data.get("vb2_excerpt", "")).strip(),
        summary=str(data.get("summary", "")).strip(),
        impact=str(data.get("impact", "Chua ro")).strip() or "Chua ro",
        reason=str(data.get("reason", "")).strip(),
        method=method,
        important_points=[str(point).strip() for point in data.get("important_points", []) if str(point).strip()],
    )

def llm_review_single(chunk: ChunkDocumentForHierarchical, kind: str) -> ChangeItem:
    prompt = f"""Bạn là chuyên gia phân tích thay đổi văn bản pháp lý.
Hãy phân tích 1 chunk đơn lẻ đã được xác định sơ bộ là `{kind}`.
Trả về duy nhất JSON hợp lệ theo schema:
{{
  "kind": "{kind}|khong_du_can_cu",
  "summary": "tom tat ngan",
  "impact": "anh huong ngan hoac Chua ro",
  "excerpt": "trich doan ngan",
  "important_points": ["y 1", "y 2"],
  "reason": "giai thich ngan"
}}

Chunk:
{format_chunk(chunk, True)}
"""
    try:
        data = parse_json_response(call_ollama(prompt))
    except Exception as exc:
        logger.warning("LLM single review failed for %s=%s: %s", kind, chunk.metadata.section_id, exc)
        data = {
            "kind": "khong_du_can_cu",
            "summary": "LLM khong tra ve ket qua hop le.",
            "impact": "Chua ro",
            "excerpt": chunk.noi_dung or chunk.tieu_de or "",
            "important_points": [],
            "reason": str(exc),
        }

    excerpt = str(data.get("excerpt", "")).strip()
    return ChangeItem(
        kind=str(data.get("kind", "khong_du_can_cu")).strip().lower(),
        vb1_chunk_id=chunk.metadata.section_id if kind == "xoa_bo" else None,
        vb2_chunk_id=chunk.metadata.section_id if kind == "them_moi" else None,
        vb1_excerpt=excerpt if kind == "xoa_bo" else "",
        vb2_excerpt=excerpt if kind == "them_moi" else "",
        summary=str(data.get("summary", "")).strip(),
        impact=str(data.get("impact", "Chua ro")).strip() or "Chua ro",
        reason=str(data.get("reason", "")).strip(),
        method=kind,
        important_points=[str(point).strip() for point in data.get("important_points", []) if str(point).strip()],
    )

def render_change_report(change_items: List[ChangeItem]) -> str:
    summary_points: List[str] = []
    for item in change_items:
        for point in item.important_points:
            if point and point not in summary_points:
                summary_points.append(point)

    if not summary_points:
        summary_points = ["Không phát hiện điểm thay đổi quan trọng từ các mục đã phân tích."]

    grouped = {
        "sua_doi": [item for item in change_items if item.kind == "sua_doi"],
        "them_moi": [item for item in change_items if item.kind == "them_moi"],
        "xoa_bo": [item for item in change_items if item.kind == "xoa_bo"],
        "khong_du_can_cu": [item for item in change_items if item.kind == "khong_du_can_cu"],
    }

    lines: List[str] = []
    lines.append("# Báo cáo thay đổi")
    lines.append("")
    lines.append("## Tóm tắt thay đổi quan trọng")
    for point in summary_points[:10]:
        lines.append(f"- {point}")
    lines.append("")
    lines.append("## Danh sách thay đổi")
    lines.append("")

    lines.append("### Sửa đổi (Chỉ phân tích bằng LLM cho các phần thay đổi lớn)")
    if not grouped["sua_doi"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["sua_doi"]:
        lines.append(f"- Vị trí VB1: {item.vb1_chunk_id}")
        lines.append(f"- Vị trí VB2: {item.vb2_chunk_id}")
        lines.append(f'- Trích đoạn VB1: "{item.vb1_excerpt}"')
        lines.append(f'- Trích đoạn VB2: "{item.vb2_excerpt}"')
        lines.append(f"- Tóm tắt thay đổi: {item.summary or 'Chưa có mô tả.'}")
        lines.append(f"- Ảnh hưởng pháp lý/nghiệp vụ: {item.impact or 'Chưa rõ'}")
    lines.append("")

    lines.append("### Thêm mới")
    if not grouped["them_moi"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["them_moi"]:
        lines.append(f"- Vị trí VB2: {item.vb2_chunk_id}")
        lines.append(f'- Trích đoạn VB2: "{item.vb2_excerpt}"')
        lines.append(f"- Lý do: {item.reason or item.summary or 'Không ghép được với VB1.'}")
    lines.append("")

    lines.append("### Xóa bỏ")
    if not grouped["xoa_bo"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["xoa_bo"]:
        lines.append(f"- Vị trí VB1: {item.vb1_chunk_id}")
        lines.append(f'- Trích đoạn VB1: "{item.vb1_excerpt}"')
        lines.append(f"- Lý do: {item.reason or item.summary or 'Không ghép được với VB2.'}")
    lines.append("")

    lines.append("### Không đủ căn cứ")
    if not grouped["khong_du_can_cu"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["khong_du_can_cu"]:
        pos = item.vb2_chunk_id or item.vb1_chunk_id or "Không rõ"
        lines.append(f"- Vị trí VB2 hoặc VB1: {pos}")
        lines.append(f"- Ghi chú: {item.reason or item.summary or 'Chưa đủ căn cứ kết luận.'}")

    return "\n".join(lines)

# ---------------------------
# MAIN PIPELINE
# ---------------------------
def run_pipeline() -> Path:
    start_time = time.time()
    logger.info("Pipeline started")
    vb1_chunks, vb2_chunks = load_chunks(VB1_PATH), load_chunks(VB2_PATH)
    vb1_map = {c.metadata.section_id: c for c in vb1_chunks}
    logger.info("Chunk loading finished: VB1=%d, VB2=%d", len(vb1_chunks), len(vb2_chunks))
    
    results: List[MatchResult] = []
    matched_vb1, matched_vb2 = set(), set()
    
    # Phase 0: Exact match
    logger.info("Phase 0 started: exact match")
    vb1_raw_map = {format_chunk(c): c for c in vb1_chunks}
    for vb2 in vb2_chunks:
        vb2_id = vb2.metadata.section_id
        if match := vb1_raw_map.get(format_chunk(vb2)):
            if match.metadata.section_id not in matched_vb1:
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
        logger.info("Phase 1 started: embedding/global matching for remaining chunks VB1=%d, VB2=%d", len(rem_vb1), len(rem_vb2))
        model = OnnxEmbeddingModel(model_dir=EMBEDDING_MODEL_DIR)
        vb1_records = embed_chunks(rem_vb1, model)
        vb2_records = embed_chunks(rem_vb2, model)
        vb1_embeddings = build_embedding_results(vb1_records)
        
        vector_store = ChromaStore(ChromaConfig(collection_name=f"vb1_idx_{int(time.time())}", is_persist=False, distance_metric="ip"))
        logger.info("Vector store created: collection=%s", vector_store.config.collection_name)
        VectorStorePipeline(embeddings=vb1_embeddings).run(vector_store, batch_size=32)
        logger.info("Vector store upsert finished: %d embeddings", len(vb1_embeddings))
        
        retrieval_service = RetrievalService(embedding_model=None, vector_store=vector_store, reranker=FlagReranker(RERANKER_MODEL_DIR, use_fp16=False, devices="cpu"))
        logger.info("Reranker initialized: model_dir=%s", RERANKER_MODEL_DIR)
        
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
    logger.info("Phase 2 started")
    vb2_map = {c.metadata.section_id: c for c in vb2_chunks}
    change_items: List[ChangeItem] = []

    for match in results:
        # CHỈ phân tích LLM cho các cặp "khó nhằn" từ thuật toán hybrid, bỏ qua các đoạn giống nhau sẵn
        if match.method != "hungarian_hybrid":
            continue
            
        if not match.vb1_chunk_id:
            continue
            
        logger.info("Phase 2 pair review: VB2=%s -> VB1=%s (%s)", match.vb2_chunk_id, match.vb1_chunk_id, match.method)
        change_items.append(llm_review_pair(vb1_map[match.vb1_chunk_id], vb2_map[match.vb2_chunk_id], match.method))

    unmatched_vb2 = [record.chunk for record in vb2_records if record.chunk.metadata.section_id not in matched_vb2]
    unmatched_vb1 = [record.chunk for record in vb1_records if record.chunk.metadata.section_id not in matched_vb1]

    for chunk in unmatched_vb2:
        logger.info("Phase 2 addition review: VB2=%s", chunk.metadata.section_id)
        change_items.append(llm_review_single(chunk, "them_moi"))

    for chunk in unmatched_vb1:
        logger.info("Phase 2 deletion review: VB1=%s", chunk.metadata.section_id)
        change_items.append(llm_review_single(chunk, "xoa_bo"))

    llm_output = render_change_report(change_items)
    logger.info("Phase 2 finished")

    # Phase 3: Reporting
    logger.info("Phase 3 started: writing report")
    out_path = Path("results") / "pair_match" / f"pair_match_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    report = f"""# Báo cáo luồng so khớp pháp lý (Pair Matching Pipeline)
- **VB1 (Cũ):** `{VB1_PATH}`
- **VB2 (Mới):** `{VB2_PATH}`

## Thống kê tổng quan:
- **Giống hệt nhau (Raw Exact matches):** {len([r for r in results if r.method == 'raw_exact'])} cặp
- **Giống nhau tin cậy cao (Greedy Vector matches):** {len([r for r in results if r.method == 'high_confidence_greedy'])} cặp
- **Sửa đổi cần phân tích (Hungarian Hybrid matches):** {len([r for r in results if r.method == 'hungarian_hybrid'])} cặp
- **Số lượng yêu cầu đẩy lên LLM:** {len(change_items)} (Gồm các cặp sửa đổi + Các đoạn thêm mới/xóa bỏ)

---
{llm_output}
"""
    out_path.write_text(report, encoding="utf-8")
    logger.info(
        "Phase 3 finished: report written raw_exact=%d greedy=%d hungarian_hybrid=%d llm_items=%d",
        len([r for r in results if r.method == "raw_exact"]),
        len([r for r in results if r.method == "high_confidence_greedy"]),
        len([r for r in results if r.method == "hungarian_hybrid"]),
        len(change_items),
    )
    logger.info(f"Pipeline Finished in {time.time() - start_time:.2f}s. Report: {out_path}")
    return out_path

if __name__ == "__main__":
    run_pipeline()