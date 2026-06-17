import re
import tempfile
import subprocess
from pathlib import Path
from html import unescape

def flatten_tables_in_html(html_str: str):
    """Finds all table elements in the HTML and flattens them into semantic text lines
    so that chunking and embedding processes can read and compare them easily.

    Trả về (html_đã_thay_bảng_bằng_text, danh_sách_HTML_bảng_gốc). Mỗi bảng được chèn
    một marker ⟦BANG:i⟧ vào text để sau này gắn lại HTML bảng gốc cho đúng đoạn (hiển thị UI).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html_str, []

    captured_tables = []
    try:
        soup = BeautifulSoup(html_str, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return html_str, []

        for table in tables:
            trs = table.find_all("tr")
            if not trs:
                continue

            all_rows = []
            for tr in trs:
                cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                if any(cells):
                    all_rows.append(cells)

            if not all_rows:
                table.decompose()
                continue

            # Identify headers
            headers = []
            thead = table.find("thead")
            if thead:
                first_tr = thead.find("tr")
                if first_tr:
                    headers = [c.get_text(strip=True) for c in first_tr.find_all(["th", "td"])]
            
            if not headers and all_rows:
                first_tr = trs[0]
                if first_tr.find("th") or len(all_rows) > 1:
                    headers = all_rows[0]

            headers = [h for h in headers if h]
            data_rows = all_rows[1:] if headers else all_rows

            flattened_lines = []
            for row in data_rows:
                if not row or not any(row):
                    continue
                
                if headers and len(headers) > 0:
                    if len(row) == len(headers) + 1:
                        row_label = row[0]
                        row_parts = []
                        for h_idx, h_val in enumerate(headers):
                            val = row[h_idx + 1]
                            row_parts.append(f"{h_val}: {val}")
                        flattened_lines.append(f"{row_label}: {'; '.join(row_parts)}")
                    elif len(row) == len(headers):
                        row_parts = []
                        for h_idx, h_val in enumerate(headers):
                            val = row[h_idx]
                            row_parts.append(f"{h_val}: {val}")
                        if len(row) > 1:
                            row_label = row[0]
                            remaining_parts = row_parts[1:]
                            flattened_lines.append(f"{row_label}: {'; '.join(remaining_parts)}")
                        else:
                            flattened_lines.append("; ".join(row_parts))
                    else:
                        row_parts = []
                        for col_idx, val in enumerate(row):
                            h_val = headers[col_idx] if col_idx < len(headers) else f"Cột {col_idx+1}"
                            row_parts.append(f"{h_val}: {val}")
                        if len(row) > 1:
                            row_label = row[0]
                            remaining_parts = row_parts[1:]
                            flattened_lines.append(f"{row_label}: {'; '.join(remaining_parts)}")
                        else:
                            flattened_lines.append("; ".join(row_parts))
                else:
                    if len(row) > 1:
                        flattened_lines.append(f"{row[0]}: {'; '.join(row[1:])}")
                    else:
                        flattened_lines.append(row[0])

            # Lưu HTML bảng gốc + chèn marker ⟦BANG:i⟧ để gắn lại đúng đoạn khi hiển thị
            table_idx = len(captured_tables)
            captured_tables.append(str(table))

            new_tag = soup.new_tag("p")
            new_tag.string = f"⟦BANG:{table_idx}⟧\n" + "\n".join(flattened_lines)
            table.replace_with(new_tag)

        return str(soup), captured_tables
    except Exception:
        return html_str, []


def extract_text_from_html(html: str, return_tables: bool = False):
    """Extract plain text from HTML content for chunking and embedding.

    Removes all HTML tags and entities, normalizes whitespace.

    Args:
        html: HTML content from Pandoc conversion
        return_tables: nếu True, trả (text, tables_html) — tables_html là HTML bảng gốc
            theo thứ tự marker ⟦BANG:i⟧ còn trong text.

    Returns:
        Clean plain text (mặc định), hoặc (text, tables_html) khi return_tables=True
    """
    # 0. Duỗi phẳng bảng biểu thành các dòng text ngữ nghĩa (giữ lại HTML bảng gốc)
    html, captured_tables = flatten_tables_in_html(html)

    # 1. Xóa ký tự điều khiển ẩn
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', html)
    
    # 2. Xóa script/style tags và nội dung
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Xóa HTML comments
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    
    # 4. LOẠI BỎ HTML TAGS - thay thế br, hr, p tags bằng newline
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<hr\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(div|section|article|header|footer|main)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(li|ul|ol)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(tr|td|th|table|thead|tbody)[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # 5. Xóa tất cả các tags còn lại
    text = re.sub(r'<[^>]+>', '', text)
    
    # 6. Giải mã HTML entities
    text = unescape(text)
    
    # 7. Thay &nbsp; và unicode whitespace
    text = text.replace('\xa0', ' ')
    text = text.replace('\u200b', '')  # Zero-width space
    text = text.replace('\u200c', '')  # Zero-width non-joiner
    
    # 8. Chuẩn hóa dấu ngoặc
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('「', '"').replace('」', '"')
    
    # 9. Chuẩn hóa dấu gạch ngang
    text = re.sub(r'—+', ' - ', text)
    text = re.sub(r'–+', ' - ', text)
    text = re.sub(r'―+', ' - ', text)
    
    # 10. Gỡ bỏ ký tự escape
    text = text.replace('\\[', '[').replace('\\]', ']')
    text = text.replace('\\<', '<').replace('\\>', '>')
    text = text.replace('\\.', '.').replace('\\-', '-')
    
    # 11. Chuẩn hóa dấu câu
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\s+\.', '.', text)
    text = re.sub(r'\.+', '.', text)
    text = text.replace(',.', '.')
    
    # 12. Chuẩn hóa whitespace
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\n[ \t]+', '\n', text)  # Remove indent
    text = re.sub(r'\n\n+', '\n\n', text)  # Multiple newlines to double
    text = re.sub(r' *\n *', '\n', text)  # Clean spaces around newlines

    text = text.strip()
    if return_tables:
        return text, captured_tables
    return text


def clean_text(text: str) -> str:
    """Clean and minify HTML while preserving tags and structure.
    
    Use for: Storage, retrieval, downstream HTML-aware processing
    For chunking/embedding: Use extract_text_from_html() instead
    
    Args:
        text: HTML content from Pandoc conversion
        
    Returns:
        Cleaned HTML (minified) with tags preserved
    """
    # 1. Xóa ký tự điều khiển ẩn
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # 2. Xóa comment HTML
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    
    # 3. Chuẩn hóa khoảng trắng (NHƯng GIỮ HTML tags)
    # - Thay &nbsp; thành space
    text = text.replace('\xa0', ' ')
    text = text.replace('&nbsp;', ' ')
    
    # - Chuẩn hóa khoảng trắng thừa bên trong text (không phải HTML)
    # Cẩn thận: không xóa whitespace trong tags
    text = re.sub(r'>\s+<', '><', text)  # Xóa whitespace giữa tags
    text = re.sub(r'([^>])\s+([^<])', r'\1 \2', text)  # Normalize spaces inside text
    text = re.sub(r' +', ' ', text)  # Multiple spaces to single space
    
    # 4. Xóa dòng trống thừa (nhưng giữ structure)
    text = re.sub(r'</p>\s*<p>', '</p><p>', text)  # Remove space between paragraphs
    text = re.sub(r'</p>\n\n+', '</p>\n', text)  # Normalize paragraph breaks
    
    # 5. Gỡ bỏ ký tự escape (nếu có)
    text = text.replace('\\[', '[').replace('\\]', ']')
    text = text.replace('\\<', '<').replace('\\>', '>')
    text = text.replace('\\.', '.').replace('\\-', '-')
    
    return text.strip()