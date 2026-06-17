import json
from pathlib import Path
from src.pipeline.runner import run_pipeline

VB1_PATH = r"D:\Downloads\VB2_V1.docx"
VB2_PATH = r"D:\Downloads\VB2_V2.docx"

def main():
    print(f"Running document matching:\n- VB1 (Old): {VB1_PATH}\n- VB2 (New): {VB2_PATH}\n")
    
    # Thực thi pipeline
    result = run_pipeline(vb1_path=VB1_PATH, vb2_path=VB2_PATH)
    
    # Tạo báo cáo Markdown
    report_lines = []
    report_lines.append("# BÁO CÁO ĐỐI SÁNH CHI TIẾT (DEBUG MATCHING)")
    report_lines.append(f"- **VB1 (Cũ):** `{VB1_PATH}`")
    report_lines.append(f"- **VB2 (Mới):** `{VB2_PATH}`")
    report_lines.append("")
    
    report_lines.append("## 1. Thống kê chung (Stats)")
    report_lines.append("```json")
    report_lines.append(json.dumps(result.stats, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    
    report_lines.append("## 2. Kết quả ghép cặp từng đoạn (Chunk Matching)")
    report_lines.append("| STT | Đoạn VB2 (Mới) | Đoạn VB1 (Cũ) Ghép Cặp | Phương Pháp (Method) | Khoảng cách Vector (Distance) | Điểm Rerank | Điểm Hybrid |")
    report_lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    
    for idx, m in enumerate(result.match_results, 1):
        vb2_id = m.vb2_chunk_id
        vb1_id = m.vb1_chunk_id if m.vb1_chunk_id else "*(Không khớp - Thêm mới)*"
        method = m.method
        dist = f"{m.distance:.4f}" if m.distance is not None else "-"
        rerank = f"{m.rerank_score:.4f}" if m.rerank_score is not None else "-"
        hybrid = f"{m.hybrid_score:.4f}" if m.hybrid_score is not None else "-"
        
        # Highlight các đoạn không khớp hoặc khớp bằng LLM để dễ debug
        style_vb1 = f"**{vb1_id}**" if m.vb1_chunk_id else vb1_id
        report_lines.append(f"| {idx} | `{vb2_id}` | {style_vb1} | `{method}` | {dist} | {rerank} | {hybrid} |")
        
    report_lines.append("")
    
    report_lines.append("## 3. Danh sách các thay đổi chi tiết phát hiện được (Change Items)")
    if not result.change_items:
        report_lines.append("*(Không phát hiện thay đổi nào)*")
    else:
        for idx, item in enumerate(result.change_items, 1):
            kind_txt = {
                "sua_doi": "SỬA ĐỔI",
                "them_moi": "THÊM MỚI",
                "xoa_bo": "XÓA BỎ"
            }.get(item.kind, item.kind.upper())
            
            report_lines.append(f"### {idx}. [{kind_txt}] - Đoạn: VB2=`{item.vb2_chunk_id}` ↔ VB1=`{item.vb1_chunk_id}`")
            report_lines.append(f"- **Tóm tắt (Summary):** {item.summary}")
            report_lines.append(f"- **Ảnh hưởng (Impact):** {item.impact}")
            report_lines.append(f"- **Phương pháp nhận diện:** `{item.method}`")
            if item.changes:
                report_lines.append("- **Chi tiết các điểm thay đổi:**")
                for diff in item.changes:
                    if isinstance(diff, dict):
                        report_lines.append(f"  * **Cũ:** {diff.get('old_content', '')}")
                        report_lines.append(f"    **Mới:** {diff.get('new_content', '')}")
                    else:
                        report_lines.append(f"  * {diff}")
            report_lines.append("")
            
    # Ghi vào file báo cáo
    out_file = Path("matching_debug_report.md")
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    
    print(f"\n[OK] Saved detailed matching report to: {out_file.resolve()}")

if __name__ == "__main__":
    main()
