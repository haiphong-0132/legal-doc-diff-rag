from typing import List

from src.schemas import ChangeItem


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
