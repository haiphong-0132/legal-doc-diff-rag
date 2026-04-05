import difflib
from typing import List

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.core.retrieval.retrieval import RetrievalService
from src.core.vector_store.chroma_store import ChromaStore
from src.schemas import ChromaQueryRequest, ChunkDocumentForHierarchical

from src.core.matching.config import DISTANCE_THRESHOLD, HYBRID_THRESHOLD, RERANK_THRESHOLD, TOP_K, logger
from src.core.matching.helpers import call_ollama, format_chunk, parse_json_response
from src.core.matching.types import ChangeItem, ChunkRecord, MatchResult


def extract_keywords(text: str) -> set:
    if not text:
        return set()
    import re

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

            if distance < DISTANCE_THRESHOLD and rerank_score >= RERANK_THRESHOLD:
                if top_item.chunk_id not in matched_vb1:
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
                    distance=None,
                    rerank_score=None,
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
        logger.warning(
            "LLM pair review failed for VB1=%s VB2=%s: %s",
            vb1_chunk.metadata.section_id,
            vb2_chunk.metadata.section_id,
            exc,
        )
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
