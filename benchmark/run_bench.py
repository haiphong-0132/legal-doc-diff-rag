"""Chạy pipeline trên các bộ benchmark và dump change_items ra JSON để đánh giá."""
import sys, os, json, glob, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))


def find_docs(folder):
    """Tìm cặp văn bản gốc (V1) / sửa đổi (V2). Hỗ trợ nhiều quy ước đặt tên:
    *V1*/*V2*, hoặc <ten>.docx (gốc) + <ten>-sua-doi.docx (sửa đổi); cả .docx lẫn .pdf.
    """
    docs = [f for f in glob.glob(os.path.join(folder, "*"))
            if f.lower().endswith((".docx", ".pdf")) and not os.path.basename(f).startswith("~")]
    if len(docs) < 2:
        return (None, None)

    def is_v2(p):
        b = os.path.basename(p).lower()
        return "v2" in b or "sua-doi" in b or "sua_doi" in b or "suadoi" in b or "sửa" in b
    def is_v1(p):
        b = os.path.basename(p).lower()
        return "v1" in b

    v2 = next((d for d in docs if is_v2(d)), None)
    if v2 is None:  # không có dấu hiệu V2 -> lấy 2 doc đầu theo thứ tự tên
        docs_sorted = sorted(docs)
        return (docs_sorted[0], docs_sorted[1])

    # gốc V1: ưu tiên doc có tên là "gốc" của V2 (bỏ hậu tố -sua-doi/_v2), rồi tới doc có 'v1'
    import re as _re
    base = _re.sub(r"[-_ ]?(sua[-_ ]?doi|v2|sửa.*)$", "",
                   os.path.splitext(os.path.basename(v2))[0], flags=_re.IGNORECASE).strip(" -_").lower()
    others = [d for d in docs if d != v2]
    v1 = next((d for d in others if os.path.splitext(os.path.basename(d))[0].lower() == base), None)
    if v1 is None:
        v1 = next((d for d in others if is_v1(d)), None)
    if v1 is None:
        v1 = next((d for d in others if base and base in os.path.basename(d).lower()), None)
    if v1 is None:
        v1 = others[0] if others else None
    return (v1, v2)


def main():
    from src.pipeline.runner import run_pipeline
    targets = sys.argv[1:] or ["VB01", "VB02", "VB03", "VB04", "VB05"]
    out = {}
    for name in targets:
        folder = os.path.join(BENCH_DIR, name)
        v1, v2 = find_docs(folder)
        if not v1:
            print(f"[SKIP] {name}: khong tim thay docx", flush=True)
            continue
        print(f"\n===== {name} =====\nV1={os.path.basename(v1)} V2={os.path.basename(v2)}", flush=True)
        t0 = time.time()
        try:
            res = run_pipeline(vb1_path=v1, vb2_path=v2)
        except Exception as exc:
            print(f"[ERROR] {name}: {exc}", flush=True)
            out[name] = {"error": str(exc)}
            continue
        items = []
        for it in res.change_items:
            items.append({
                "kind": it.kind,
                "vb1_id": it.vb1_chunk_id,
                "vb2_id": it.vb2_chunk_id,
                "vb1_excerpt": (it.vb1_excerpt or "")[:300],
                "vb2_excerpt": (it.vb2_excerpt or "")[:300],
                "summary": it.summary,
                "changes": it.changes,
                "method": it.method,
            })
        out[name] = {"stats": res.stats, "items": items, "elapsed": round(time.time() - t0, 1)}
        print(f"[DONE] {name} stats={res.stats} ({out[name]['elapsed']}s)", flush=True)

    with open(os.path.join(BENCH_DIR, "bench_output.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nSaved -> benchmark/bench_output.json", flush=True)


if __name__ == "__main__":
    main()
