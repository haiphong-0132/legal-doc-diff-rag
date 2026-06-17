"""Chấm điểm benchmark: so khớp output hệ thống với groundtruth Results.xlsx.

Cách dùng:
    uv run python benchmark/eval.py                 # chấm từ benchmark/bench_output*.json đã có
    uv run python benchmark/eval.py --run VB01 VB02  # tự chạy pipeline rồi chấm

Quy tắc khớp item <-> GT:
  - Trích "khóa vị trí" (Điều / Khoản / Điểm) từ cả hai phía.
  - Khớp nếu cùng số Điều VÀ (cùng Khoản, hoặc một bên không nêu Khoản).
  - TP "đúng vị trí" = có khớp vị trí. TP "đúng loại" = khớp vị trí VÀ đúng sửa/thêm/xóa.
  - In chi tiết alignment để kiểm chứng (không phải hộp đen).
Metric: Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1 = 2PR/(P+R), + Macro & Weighted.
"""
import sys, os, re, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import openpyxl

BENCH = os.path.dirname(os.path.abspath(__file__))

# ----- chuẩn hóa loại thay đổi (trả None nếu ô không phải một loại thay đổi hợp lệ) -----
def norm_kind(loai: str):
    s = (loai or "").lower()
    has_sua = "sửa" in s or "sua" in s or "paraphrase" in s or "pharaphase" in s or "điều chỉnh" in s
    has_them = "thêm" in s or "them" in s or "bổ sung" in s
    has_xoa = "xóa" in s or "xoa" in s or "loại bỏ" in s
    if has_sua:           # "Sửa + Thêm" / "Sửa (Paraphrase)" -> sua_doi
        return "sua_doi"
    if has_xoa:
        return "xoa_bo"
    if has_them:
        return "them_moi"
    return None           # ô footer/ghi chú ("Đúng", "4.0", "Độ chính xác"...) -> bỏ qua


# ----- token hóa để so khớp theo NỘI DUNG -----
_WORD_RE = re.compile(r"[0-9]+[.,][0-9]+|[0-9]+|[a-zA-Zà-ỹĐđ]+", re.UNICODE)
_STOP = set("và của là các một có được trong cho về theo tại với khi như đã sẽ này đó những bên".split())

def toks(text: str) -> set:
    return {w.lower() for w in _WORD_RE.findall(text or "")
            if len(w) > 1 and w.lower() not in _STOP}

def overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))

# ----- trích khóa vị trí -----
def loc_from_text(text: str) -> dict:
    """Trích {dieu, khoan, diem} từ chuỗi GT (vd 'Điều 6, Khoản 2' hoặc '3.2.2.')."""
    t = text or ""
    loc = {"dieu": None, "khoan": None, "diem": None}
    md = re.search(r"[Đđ]i[ềe]u\s*([0-9]+)", t)
    if md: loc["dieu"] = md.group(1)
    mk = re.search(r"[Kk]ho[ảa]n\s*([0-9]+(?:\.[0-9]+)?)", t)
    if mk:
        parts = mk.group(1).split(".")
        loc["khoan"] = parts[-1]
        # "khoản 9.1" kiểu hợp đồng = Điều 9, Khoản 1 (khi snippet không nêu "Điều N")
        if loc["dieu"] is None and len(parts) == 2:
            loc["dieu"] = parts[0]
    mp = re.search(r"[Đđ]i[ểe]m\s*([0-9a-zđ]+)", t)
    if mp: loc["diem"] = mp.group(1)
    # kiểu hợp đồng: token "3.2.2" ở đầu dòng -> dieu.khoan.diem
    if loc["dieu"] is None:
        mc = re.match(r"\s*([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", t)
        if mc:
            loc["dieu"] = mc.group(1)
            if mc.group(2): loc["khoan"] = mc.group(2)
            if mc.group(3): loc["diem"] = mc.group(3)
    return loc

def loc_from_id(sid: str) -> dict:
    """Trích từ section_id hệ thống vd 'dieu_6.khoan_2' / 'dieu_3.khoan_3_2.diem_3_2_2'."""
    loc = {"dieu": None, "khoan": None, "diem": None}
    if not sid: return loc
    md = re.search(r"dieu_([0-9]+)", sid)
    if md: loc["dieu"] = md.group(1)
    mk = re.search(r"khoan_([0-9_]+)", sid)
    if mk: loc["khoan"] = mk.group(1).split("_")[-1]
    mp = re.search(r"diem_([0-9a-zđ_]+)", sid)
    if mp: loc["diem"] = mp.group(1).split("_")[-1]
    return loc

def sys_loc(item: dict) -> dict:
    # ưu tiên id cụ thể hơn (cái nào có nhiều cấp hơn)
    a = loc_from_id(item.get("vb1_id") or "")
    b = loc_from_id(item.get("vb2_id") or "")
    pick = a if sum(v is not None for v in a.values()) >= sum(v is not None for v in b.values()) else b
    if pick["dieu"] is None:  # fallback: parse summary
        pick = loc_from_text(item.get("summary") or "")
    return pick

def loc_match(g: dict, s: dict) -> bool:
    if g["dieu"] is None or s["dieu"] is None:
        return False
    if g["dieu"] != s["dieu"]:
        return False
    # Khoản: khớp nếu bằng nhau, hoặc một bên thiếu (Điều phẳng / item gộp)
    if g["khoan"] and s["khoan"] and g["khoan"] != s["khoan"]:
        return False
    return True

# ----- đọc GT (chịu được nhiều layout cột khác nhau giữa các VB) -----
KIND_HDR = ("loại thay đổi", "phân loại thay đổi", "phân loại", "loại", "thao tác")

def _find_gt_file(folder: str):
    cands = [f for f in glob.glob(os.path.join(folder, "*"))
             if f.lower().endswith((".xlsx", ".xls", ".csv")) and not os.path.basename(f).startswith("~")]
    # ưu tiên Results.xlsx, rồi file có tên giống VBxx, rồi file đầu tiên
    cands.sort(key=lambda p: (0 if "results" in os.path.basename(p).lower() else 1, len(os.path.basename(p))))
    return cands[0] if cands else None

def read_gt(vb: str) -> list:
    f = _find_gt_file(os.path.join(BENCH, vb))
    if not f: return []
    ws = openpyxl.load_workbook(f).active
    raw = [list(r) for r in ws.iter_rows(values_only=True)]
    if not raw: return []

    # 1. Tìm hàng header + cột "loại thay đổi"
    hdr_idx, kind_col = None, None
    for i, row in enumerate(raw[:5]):
        for j, c in enumerate(row):
            if c and any(k == str(c).strip().lower() or k in str(c).strip().lower() for k in KIND_HDR):
                hdr_idx, kind_col = i, j
                break
        if hdr_idx is not None:
            break
    if kind_col is None:  # fallback: giả định layout cũ STT|V1|V2|Loại
        hdr_idx, kind_col = 0, 3

    rows = []
    stt = 0
    for row in raw[hdr_idx + 1:]:
        if kind_col >= len(row):
            continue
        loai = row[kind_col]
        kind = norm_kind(str(loai or ""))
        if kind is None:           # bỏ qua hàng footer/ghi chú không phải thay đổi
            continue
        # gom toàn bộ text các cột (vị trí + nội dung) để trích vị trí + so khớp nội dung
        ctx = " ".join(str(x) for x in row if x)
        stt += 1
        rows.append({"stt": stt, "loai": str(loai), "kind": kind,
                     "loc": loc_from_text(ctx), "toks": toks(ctx),
                     "text": ctx[:80].replace("\n", " ")})
    return rows

# ----- chấm 1 văn bản -----
def sys_toks(it: dict) -> set:
    return toks(" ".join([it.get("vb1_excerpt", ""), it.get("vb2_excerpt", ""),
                          " ".join(it.get("changes", []) or []), it.get("summary", "")]))

def score_vb(vb: str, items: list, verbose=True):
    gt = read_gt(vb)
    sys_items = [{**it, "loc": sys_loc(it), "toks": sys_toks(it)} for it in items]
    gt_hit = [False] * len(gt)
    sys_hit = [False] * len(sys_items)
    pairs = []

    # Tính điểm khớp cho mọi cặp (item, GT): kết hợp VỊ TRÍ và NỘI DUNG.
    # - khớp vị trí Điều/Khoản: +1.0
    # - độ trùng nội dung (overlap token): +giá trị overlap
    # - cùng loại (sửa/thêm/xóa): +0.3
    # Chỉ chấp nhận khi có bằng chứng đủ mạnh (vị trí khớp HOẶC nội dung trùng >=0.4).
    cand = []
    for si, s in enumerate(sys_items):
        for gi, g in enumerate(gt):
            lm = loc_match(g["loc"], s["loc"])
            ov = overlap(s["toks"], g["toks"])
            if not lm and ov < 0.4:
                continue
            score = (1.0 if lm else 0.0) + ov + (0.3 if g["kind"] == s["kind"] else 0.0)
            cand.append((score, si, gi))

    # Gán tham lam theo điểm giảm dần (mỗi item & mỗi GT chỉ khớp 1 lần).
    cand.sort(reverse=True)
    for score, si, gi in cand:
        if sys_hit[si] or gt_hit[gi]:
            continue
        sys_hit[si] = True; gt_hit[gi] = True
        pairs.append((gi, si, gt[gi]["kind"] == sys_items[si]["kind"]))

    TP = sum(gt_hit)
    FP = sum(1 for h in sys_hit if not h)
    FN = sum(1 for h in gt_hit if not h)
    P = TP / (TP + FP) if (TP + FP) else 0.0
    R = TP / (TP + FN) if (TP + FN) else 0.0
    F1 = 2 * P * R / (P + R) if (P + R) else 0.0
    if verbose:
        print(f"\n===== {vb} ===== GT={len(gt)} | trả về={len(sys_items)} | TP={TP} FP={FP} FN={FN}")
        for gi, si, kind_ok in pairs:
            flag = "" if kind_ok else "  [SAI LOẠI]"
            print(f"  ✓ GT#{gt[gi]['stt']}[{gt[gi]['kind']}] <- {sys_items[si]['vb1_id']}/{sys_items[si]['vb2_id']}[{sys_items[si]['kind']}]{flag}")
        for gi, h in enumerate(gt_hit):
            if not h: print(f"  ✗ SÓT GT#{gt[gi]['stt']}[{gt[gi]['kind']}] {gt[gi]['text']}")
        for si, h in enumerate(sys_hit):
            if not h: print(f"  ! THỪA {sys_items[si]['vb1_id']}/{sys_items[si]['vb2_id']}[{sys_items[si]['kind']}]")
        print(f"  -> P={P:.2f} R={R:.2f} F1={F1:.2f}")
    return {"vb": vb, "gt": len(gt), "tp": TP, "fp": FP, "fn": FN, "P": P, "R": R, "F1": F1}

def load_outputs():
    out = {}
    for fn in ["bench_output_fixed.json", "bench_output.json", "bench_output_vb01.json", "bench_output_2345.json"]:
        p = os.path.join(BENCH, fn)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            for k, v in d.items():
                out.setdefault(k, v)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs="*", help="Chạy pipeline cho các VB này trước khi chấm")
    ap.add_argument("vbs", nargs="*", help="Các VB cần chấm (mặc định: tất cả có trong output)")
    args = ap.parse_args()

    if args.run:
        from src.pipeline.runner import run_pipeline
        from run_bench import find_docs
        out = {}
        for vb in args.run:
            v1, v2 = find_docs(os.path.join(BENCH, vb))
            if not v1 or not v2:
                print(f"[SKIP] {vb}: thiếu V1/V2"); continue
            res = run_pipeline(vb1_path=v1, vb2_path=v2)
            out[vb] = {"items": [{"kind": it.kind, "vb1_id": it.vb1_chunk_id, "vb2_id": it.vb2_chunk_id,
                                  "summary": it.summary} for it in res.change_items]}
    else:
        out = load_outputs()

    targets = args.vbs or sorted(out.keys())
    rows = [score_vb(vb, out[vb]["items"]) for vb in targets if vb in out and "items" in out[vb]]
    if not rows: return

    print("\n" + "=" * 64)
    print(f"{'VB':6} {'GT':>3} {'TP':>3} {'FP':>3} {'FN':>3} {'P':>6} {'R':>6} {'F1':>6}")
    for r in rows:
        note = "  (không có groundtruth — bỏ khỏi TB)" if r["gt"] == 0 else ""
        print(f"{r['vb']:6} {r['gt']:>3} {r['tp']:>3} {r['fp']:>3} {r['fn']:>3} {r['P']:>6.2f} {r['R']:>6.2f} {r['F1']:>6.2f}{note}")
    scored = [r for r in rows if r["gt"] > 0]   # chỉ tính trung bình trên VB có groundtruth
    n = len(scored)
    macroP = sum(r["P"] for r in scored) / n
    macroR = sum(r["R"] for r in scored) / n
    macroF = sum(r["F1"] for r in scored) / n
    tot = sum(r["gt"] for r in scored)
    wP = sum(r["P"] * r["gt"] for r in scored) / tot
    wR = sum(r["R"] * r["gt"] for r in scored) / tot
    wF = sum(r["F1"] * r["gt"] for r in scored) / tot
    print("-" * 64)
    print(f"{'Macro':6} ({n} VB)      {macroP:>6.2f} {macroR:>6.2f} {macroF:>6.2f}")
    print(f"{'Weight':6} (theo GT)    {wP:>6.2f} {wR:>6.2f} {wF:>6.2f}")

if __name__ == "__main__":
    main()
