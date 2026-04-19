import re
from pathlib import Path
import json

def parse_heading(line):
    if not line: return None

    PATTERNS = [
        ('dieu', r'(?i)^điều\s+([0-9a-z]+)[\.\:\)]?\s*(.*)$'),
        ('so_cap_3',   r'^(\d+\.\d+\.\d+)[\.\)]?\s*(.*)$'),
        ('so_cap_2',   r'^(\d+\.\d+)[\.\)]?\s*(.*)$'),
        ('so_cap_1',   r'^(\d+)[\.\)]\s*(.*)$'),

        # --- NHÓM CHỮ (LETTER) ---
        ('chu_thuong', r'^([a-zđ])[\.\)\,]\s*(.*)$')        # Bắt: a., a), a, đ)
    ]

    for p_type, pattern in PATTERNS:
        match = re.match(pattern, line)
        if match:
            return {
                "type": p_type,
                "id_raw": match.group(1).lower(),
                "content": line
            }

    return None

def chunk_text_approx(text, max_tokens=1000):
    """
    Hàm chia nhỏ văn bản (chunking) nhưng vẫn giữ trọn vẹn câu.
    """
    sentences = text.split('. ')
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence.split())
        if current_len + sentence_len > max_tokens and current_chunk:
            chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))
            current_chunk = [sentence]
            current_len = sentence_len
        else:
            current_chunk.append(sentence)
            current_len += sentence_len

    if current_chunk:
        chunks.append(". ".join(current_chunk))

    return chunks

def extract_refs(text, current_dieu_id=None):
    """
    Hàm bắt tham chiếu chéo.
    - current_dieu_id: ID của Điều hiện tại (để giải quyết trường hợp "Điều này")
    """
    if not text:
        return []
    
    # Regex bắt Điểm, Khoản (có thể là số, chữ cái, hoặc số phân cấp như 1.1, 1.1.1)
    # Bắt Điều: Chỉ lấy nếu bắt đầu bằng số (có thể kèm 1 chữ cái như 5a) HOẶC chữ "này"
    pattern = r'(?i)(?:điểm\s+([a-zđ0-9\.]+)\s+)?(?:khoản\s+([a-zđ0-9\.]+)\s+)?điều\s+(\d+[a-zđ]?|này)'
    matches = re.findall(pattern, text)
    
    refs = []
    for diem, khoan, dieu in matches:
        
        # 1. Xử lý cấp ĐIỀU
        if dieu.lower() == 'này':
            if current_dieu_id:
                ref_id = current_dieu_id # Lấy ID của Điều hiện tại
            else:
                continue # Nếu ở phần mở đầu (không thuộc Điều nào) mà ghi "Điều này" thì bỏ qua
        else:
            ref_id = f"dieu_{dieu.lower()}"
            
        # 2. Xử lý cấp KHOẢN (chuyển dấu chấm thành gạch dưới cho chuẩn ID, VD: 1.1 -> 1_1)
        if khoan:
            safe_khoan = khoan.replace('.', '_').lower()
            ref_id += f".khoan_{safe_khoan}"
            
        # 3. Xử lý cấp ĐIỂM
        if diem:
            safe_diem = diem.replace('.', '_').lower()
            ref_id += f".diem_{safe_diem}"
            
        # Tránh trùng lặp ID trong cùng một đoạn
        if ref_id not in refs:
            refs.append(ref_id)
            
    return refs

def build_json_tree(text):
    """
    Hàm phân tích văn bản luật thành cấu trúc cây JSON (Điều -> Khoản -> Điểm)
    có bóc tách tham chiếu chéo thông minh (giải quyết được "Điều này").
    """
    lines = text.strip().split('\n')
    tree = []

    # BƯỚC 1: TÁCH THÔ THEO ĐIỀU VÀ PHẦN MỞ ĐẦU
    dieu_blocks = []
    current_b_loai = 'mo_dau'
    current_b_id = 'mo_dau'
    current_b_tieu_de = ''
    current_lines = []

    for line in lines:
        if not line: continue

        m = re.match(r'(?i)^điều\s+([0-9a-z]+)[\.\:\)]?\s*(.*)$', line)
        if m:
            if current_lines or current_b_loai == 'mo_dau':
                dieu_blocks.append((current_b_loai, current_b_id, current_b_tieu_de, current_lines))

            current_b_loai = 'dieu'
            current_b_id = f"dieu_{m.group(1).lower()}"
            current_b_tieu_de = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines or current_b_loai != 'mo_dau':
        dieu_blocks.append((current_b_loai, current_b_id, current_b_tieu_de, current_lines))

    # BƯỚC 2: XỬ LÝ CHUNKING & TÁCH KHOẢN/ĐIỂM
    for b_loai, b_id, b_tieu_de, b_lines in dieu_blocks:

        # --- XỬ LÝ PHẦN MỞ ĐẦU ---
        if b_loai == 'mo_dau':
            if b_lines:
                mo_dau_text = ". ".join(b_lines)
                chunks = chunk_text_approx(mo_dau_text, max_tokens=1000)

                for i, chunk in enumerate(chunks, 1):
                    tree.append({
                        "id": f"modau_{i}",
                        "loai": "mo_dau",
                        "noi_dung": chunk,
                        "ref": extract_refs(chunk, current_dieu_id=None) # Mở đầu thì không có 'Điều này'
                    })
            continue

        # --- XỬ LÝ PHÂN CẤP KHOẢN / ĐIỂM CHO "ĐIỀU" ---
        dieu_noi_dung = []
        con_list = []

        khoan_pattern = None
        diem_pattern = None
        current_khoan = None
        current_diem = None

        for line in b_lines:
            parsed = parse_heading(line)
            level = 'text'

            if parsed and parsed.get('type') != 'dieu':
                p_type = parsed['type']
                raw_id = parsed['id_raw']

                if khoan_pattern is None:
                    khoan_pattern = p_type
                    level = 'khoan'
                elif p_type == khoan_pattern:
                    level = 'khoan'
                else:
                    if diem_pattern is None:
                        diem_pattern = p_type
                        level = 'diem'
                    elif p_type == diem_pattern:
                        level = 'diem'
                    else:
                        level = 'text'

            # --- Xếp dòng hiện tại vào đúng túi ---
            if level == 'khoan':
                if current_diem:
                    current_diem['noi_dung'] = ". ".join(current_diem.pop('lines'))
                    # Truyền b_id vào hàm để biết "Điều này" là điều nào
                    current_diem['ref'] = extract_refs(current_diem['noi_dung'], b_id) 
                    if current_khoan: current_khoan['con'].append(current_diem)
                    else: con_list.append(current_diem)
                    current_diem = None

                if current_khoan:
                    current_khoan['noi_dung'] = ". ".join(current_khoan.pop('lines'))
                    current_khoan['ref'] = extract_refs(current_khoan['noi_dung'], b_id)
                    con_list.append(current_khoan)

                safe_id = raw_id.replace('.', '_')
                current_khoan = {
                    "id": f"{b_id}.khoan_{safe_id}", "loai": "khoan",
                    "lines": [line], "con": []
                }

            elif level == 'diem':
                if current_diem:
                    current_diem['noi_dung'] = ". ".join(current_diem.pop('lines'))
                    current_diem['ref'] = extract_refs(current_diem['noi_dung'], b_id)
                    if current_khoan: current_khoan['con'].append(current_diem)
                    else: con_list.append(current_diem)

                safe_id = raw_id.replace('.', '_')
                parent_id = current_khoan['id'] if current_khoan else b_id
                current_diem = {
                    "id": f"{parent_id}.diem_{safe_id}", "loai": "diem", "lines": [line]
                }

            elif level == 'text':
                if current_diem: current_diem['lines'].append(line)
                elif current_khoan: current_khoan['lines'].append(line)
                else: dieu_noi_dung.append(line)

        # --- Dọn dẹp túi cuối cùng ---
        if current_diem:
            current_diem['noi_dung'] = ". ".join(current_diem.pop('lines'))
            current_diem['ref'] = extract_refs(current_diem['noi_dung'], b_id)
            if current_khoan: current_khoan['con'].append(current_diem)
            else: con_list.append(current_diem)

        if current_khoan:
            current_khoan['noi_dung'] = ". ".join(current_khoan.pop('lines'))
            current_khoan['ref'] = extract_refs(current_khoan['noi_dung'], b_id)
            con_list.append(current_khoan)

        # --- Hoàn thiện Node của Điều ---
        dieu_noi_dung_str = ". ".join(dieu_noi_dung)
        dieu_node = {
            "id": b_id,
            "loai": "dieu",
            "tieu_de": b_tieu_de,
            "noi_dung": dieu_noi_dung_str,
            "ref": extract_refs(dieu_noi_dung_str, b_id) # Bắt ref trong văn bản tự do của Điều
        }
        if con_list:
            dieu_node["con"] = con_list

        tree.append(dieu_node)

    return tree