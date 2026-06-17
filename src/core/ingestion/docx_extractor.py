import re
import pypandoc
from pathlib import Path

from src.core.ingestion.text_cleaner import extract_text_from_html


def extract_docx_text(input_file, return_tables: bool = False):
    """Convert DOCX to plain text for chunking/embedding.

    Quy trình chính: DOCX -> Pandoc HTML -> extract text.

    Fallback: Một số văn bản dùng numbered-list TỰ ĐỘNG của Word cho cấu trúc
    Điều/Khoản/Điểm (số "Điều 1, 2..." do Word sinh, không nằm trong text). Pandoc
    làm phẳng các list này nên số thứ tự bị mất -> parser không tách được Điều.
    Khi text của Pandoc KHÔNG có dấu "Điều N", ta dựng lại số thứ tự trực tiếp từ
    định nghĩa numbering trong file .docx (numbering.xml) để khôi phục cấu trúc.

    Args:
        input_file: Path to DOCX file

    Returns:
        Plain text string (ready for chunking/embedding)
    """
    input_path = Path(input_file)
    html = pypandoc.convert_file(
        str(input_path),
        "html",
        extra_args=["--wrap=none"],
    )
    text, tables = extract_text_from_html(html, return_tables=True)

    # Nếu đã có cấu trúc "Điều N" thì dùng luôn kết quả Pandoc (không đụng tới).
    if re.search(r"(?im)^\s*điều\s+\d+", text):
        return (text, tables) if return_tables else text

    # Fallback: dựng lại số thứ tự từ numbering của Word (path này không lấy bảng).
    try:
        rebuilt = _render_docx_with_numbering(str(input_path))
    except Exception:
        rebuilt = None

    if rebuilt and re.search(r"(?im)^\s*điều\s+\d+", rebuilt):
        return (rebuilt, []) if return_tables else rebuilt
    return (text, tables) if return_tables else text


# ---------------------------------------------------------------------------
# Khôi phục numbered-list của Word (numbering.xml) -> text có "Điều N", "1.", "a)"
# ---------------------------------------------------------------------------

def _roman(n: int, upper: bool = False) -> str:
    vals = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"),
        (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"),
        (5, "v"), (4, "iv"), (1, "i"),
    ]
    s = ""
    for v, sym in vals:
        while n >= v:
            s += sym
            n -= v
    return s.upper() if upper else s


def _fmt_num(n: int, num_fmt: str) -> str:
    if num_fmt == "decimal":
        return str(n)
    if num_fmt == "lowerLetter":
        return chr(96 + n) if 1 <= n <= 26 else str(n)
    if num_fmt == "upperLetter":
        return chr(64 + n) if 1 <= n <= 26 else str(n)
    if num_fmt == "lowerRoman":
        return _roman(n)
    if num_fmt == "upperRoman":
        return _roman(n, upper=True)
    return str(n)


def _render_docx_with_numbering(input_file: str) -> str:
    """Đọc paragraph + numbering của .docx, render số thứ tự theo đúng template
    (lvlText) mà Word hiển thị: "Điều %1." -> "Điều 1.", "%1." -> "1.", "%1)" -> "a)".
    """
    import docx
    from docx.oxml.ns import qn

    doc = docx.Document(input_file)
    numbering = doc.part.numbering_part.element

    # numId -> abstractNumId
    num2abs = {}
    for num in numbering.findall(qn("w:num")):
        a = num.find(qn("w:abstractNumId"))
        num2abs[num.get(qn("w:numId"))] = a.get(qn("w:val")) if a is not None else None

    # abstractNumId -> {ilvl: (numFmt, lvlText, start)}
    abs_map = {}
    for an in numbering.findall(qn("w:abstractNum")):
        aid = an.get(qn("w:abstractNumId"))
        levels = {}
        for lvl in an.findall(qn("w:lvl")):
            il = int(lvl.get(qn("w:ilvl")))
            fmt = lvl.find(qn("w:numFmt"))
            txt = lvl.find(qn("w:lvlText"))
            st = lvl.find(qn("w:start"))
            levels[il] = (
                fmt.get(qn("w:val")) if fmt is not None else "decimal",
                txt.get(qn("w:val")) if txt is not None else "%1.",
                int(st.get(qn("w:val"))) if st is not None else 1,
            )
        abs_map[aid] = levels

    counters = {}
    lines = []
    for p in doc.paragraphs:
        txt = re.sub(r"[ \t]+", " ", (p.text or "").strip())
        if not txt:
            continue

        num_id = None
        ilvl = 0
        pPr = p._p.pPr
        if pPr is not None and pPr.numPr is not None:
            if pPr.numPr.numId is not None:
                num_id = str(pPr.numPr.numId.val)
            if pPr.numPr.ilvl is not None:
                ilvl = pPr.numPr.ilvl.val

        aid = num2abs.get(num_id) if num_id else None
        if not aid or aid not in abs_map or ilvl not in abs_map[aid]:
            lines.append(txt)
            continue

        num_fmt, lvl_text, start = abs_map[aid][ilvl]
        if num_fmt == "bullet":
            lines.append(f"- {txt}")
            continue

        # Tăng counter cấp hiện tại, reset các cấp sâu hơn của cùng abstractNum
        key = (aid, ilvl)
        counters[key] = counters.get(key, start - 1) + 1
        for k in [k for k in counters if k[0] == aid and k[1] > ilvl]:
            del counters[k]

        # Thay %1..%n bằng số đã render của từng cấp
        prefix = lvl_text
        for lv in range(ilvl + 1):
            lv_fmt = abs_map[aid].get(lv, ("decimal", "%1.", 1))[0]
            lv_start = abs_map[aid].get(lv, ("decimal", "%1.", 1))[2]
            val = counters.get((aid, lv), lv_start)
            prefix = prefix.replace(f"%{lv + 1}", _fmt_num(val, lv_fmt))

        lines.append(f"{prefix} {txt}")

    return "\n".join(lines)
