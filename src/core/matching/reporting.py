from typing import Any, Dict, List, Optional

from src.core.embedding import decode_section_id
from src.schemas import ChangeItem


def _format_position(section_id: Optional[str]) -> str:
    if not section_id:
        return "Không rõ"
    try:
        return decode_section_id(section_id)
    except ValueError:
        return section_id


def _format_location(section_id: Optional[str], excerpt: str) -> str:
    position = _format_position(section_id)
    if excerpt:
        return f"{position}\n  Trích đoạn: {excerpt}"
    return position


def _append_item_header(lines: List[str], index: int, title: str) -> None:
    lines.append(f"#### {index}. {title}")
    lines.append("")


def _append_changes(lines: List[str], changes: List[str]) -> None:
    if not changes:
        return
    lines.append("Chi tiết thay đổi:")
    for change in changes:
        for line in change.splitlines():
            lines.append(f"- {line}")
    lines.append("")


def _format_score(value: Optional[float]) -> str:
    if value is None:
        return "Không có"
    return f"{value:.4f}"


def _append_semantic_match_details(lines: List[str], matches: List[Dict[str, Any]]) -> None:
    lines.append("### 4. Giống nhau ngữ nghĩa")
    if not matches:
        lines.append("0")
        lines.append("")
        return

    for index, item in enumerate(matches, start=1):
        _append_item_header(lines, index, "Cặp chunk giống nhau về ngữ nghĩa")
        lines.append(f"VB1: {_format_location(item.get('vb1_chunk_id'), item.get('vb1_content', ''))}")
        lines.append("")
        lines.append(f"VB2: {_format_location(item.get('vb2_chunk_id'), item.get('vb2_content', ''))}")
        lines.append("")


def render_change_report(change_items: List[ChangeItem], semantic_matches: Optional[List[Dict[str, Any]]] = None) -> str:
    grouped = {
        "sua_doi": [item for item in change_items if item.kind == "sua_doi"],
        "them_moi": [item for item in change_items if item.kind == "them_moi"],
        "xoa_bo": [item for item in change_items if item.kind == "xoa_bo"],
    }

    lines: List[str] = []
    lines.append("## Kết quả phân tích thay đổi")
    lines.append("")
    lines.append(
        f"Tổng cộng: {len(change_items)} mục "
        f"({len(grouped['sua_doi'])} sửa đổi, {len(grouped['them_moi'])} thêm mới, "
        f"{len(grouped['xoa_bo'])} xóa bỏ)."
    )
    lines.append("")

    lines.append("### 1. Sửa đổi")
    if not grouped["sua_doi"]:
        lines.append("Không phát hiện mục sửa đổi.")
        lines.append("")
    for index, item in enumerate(grouped["sua_doi"], start=1):
        _append_item_header(lines, index, item.summary or "Sửa đổi nội dung")
        lines.append(f"VB1 cũ: {_format_location(item.vb1_chunk_id, item.vb1_excerpt)}")
        lines.append("")
        lines.append(f"VB2 mới: {_format_location(item.vb2_chunk_id, item.vb2_excerpt)}")
        lines.append("")
        _append_changes(lines, item.changes)
        lines.append(f"Phương pháp ghép: {item.method or 'Không rõ'}")
        lines.append("")

    lines.append("### 2. Thêm mới")
    if not grouped["them_moi"]:
        lines.append("0")
        lines.append("")
    for index, item in enumerate(grouped["them_moi"], start=1):
        _append_item_header(lines, index, item.summary or "Nội dung thêm mới")
        lines.append(f"VB2 mới: {_format_location(item.vb2_chunk_id, item.vb2_excerpt)}")
        lines.append("")
        _append_changes(lines, item.changes)
        lines.append("Kết luận: Không tìm thấy đoạn tương ứng trong VB1.")
        lines.append("")

    lines.append("### 3. Xóa bỏ")
    if not grouped["xoa_bo"]:
        lines.append("0")
        lines.append("")
    for index, item in enumerate(grouped["xoa_bo"], start=1):
        _append_item_header(lines, index, item.summary or "Nội dung xóa bỏ")
        lines.append(f"VB1 cũ: {_format_location(item.vb1_chunk_id, item.vb1_excerpt)}")
        lines.append("")
        _append_changes(lines, item.changes)
        lines.append("Kết luận: Không tìm thấy đoạn tương ứng trong VB2.")
        lines.append("")

    _append_semantic_match_details(lines, semantic_matches or [])

    return "\n".join(lines)
