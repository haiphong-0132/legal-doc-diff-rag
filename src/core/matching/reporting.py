from typing import List, Optional

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
        return f'{position} — "{excerpt}"'
    return position


def render_change_report(change_items: List[ChangeItem]) -> str:
    grouped = {
        "sua_doi": [item for item in change_items if item.kind == "sua_doi"],
        "them_moi": [item for item in change_items if item.kind == "them_moi"],
        "xoa_bo": [item for item in change_items if item.kind == "xoa_bo"],
        "khong_du_can_cu": [item for item in change_items if item.kind == "khong_du_can_cu"],
    }

    lines: List[str] = []
    lines.append("# Báo cáo thay đổi")
    lines.append("")
    lines.append("## Danh sách thay đổi")
    lines.append("")

    lines.append("### Sửa đổi")
    if not grouped["sua_doi"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["sua_doi"]:
        lines.append(f"- VB1: {_format_location(item.vb1_chunk_id, item.vb1_excerpt)}")
        lines.append(f"- VB2: {_format_location(item.vb2_chunk_id, item.vb2_excerpt)}")
        if item.changes:
            lines.append("- Các thay đổi:")
            for change in item.changes:
                lines.append(f"  + {change}")
        lines.append(f"- Tóm tắt: {item.summary or 'Chưa có mô tả.'}")
        lines.append("")

    lines.append("### Thêm mới")
    if not grouped["them_moi"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["them_moi"]:
        lines.append(f"- VB2: {_format_location(item.vb2_chunk_id, item.vb2_excerpt)}")
        if item.changes:
            lines.append("- Các thay đổi:")
            for change in item.changes:
                lines.append(f"  + {change}")
        lines.append(f"- Lý do: {item.summary or 'Không ghép được với VB1.'}")
        lines.append("")

    lines.append("### Xóa bỏ")
    if not grouped["xoa_bo"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["xoa_bo"]:
        lines.append(f"- VB1: {_format_location(item.vb1_chunk_id, item.vb1_excerpt)}")
        if item.changes:
            lines.append("- Các thay đổi:")
            for change in item.changes:
                lines.append(f"  + {change}")
        lines.append(f"- Lý do: {item.summary or 'Không ghép được với VB2.'}")
        lines.append("")

    lines.append("### Không đủ căn cứ")
    if not grouped["khong_du_can_cu"]:
        lines.append("- Không phát hiện mục nào.")
    for item in grouped["khong_du_can_cu"]:
        sid = item.vb2_chunk_id or item.vb1_chunk_id
        excerpt = item.vb2_excerpt or item.vb1_excerpt
        lines.append(f"- Vị trí: {_format_location(sid, excerpt)}")
        lines.append(f"- Ghi chú: {item.summary or 'Chưa đủ căn cứ kết luận.'}")

    return "\n".join(lines)
