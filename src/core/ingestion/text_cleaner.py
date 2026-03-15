import re
import tempfile
import subprocess
from pathlib import Path
def clean_text(text: str) -> str:
    # 1. Xóa ký tự điều khiển ẩn
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # 2. Xóa comment HTML
    text = re.sub(r'<!--[\s\S]*?-->', '', text)

    # 3. DỌN RÁC MARKDOWN
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]*[-*+][ \t]+(?=\d)', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]*>[ \t]*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]*\|?[-: \|]+\|?[ \t]*$', '', text, flags=re.MULTILINE)
    text = text.replace('|', '')
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\xa0', ' ')
    # 4. GỠ BỎ KÝ TỰ ESCAPE
    text = text.replace('\\[', '[').replace('\\]', ']')
    text = text.replace('\\<', '<').replace('\\>', '>')
    text = text.replace('\\.', '.')
    text = text.replace('\\-', '-')
    # 5. CHUẨN HÓA DẤU CÂU & KHOẢNG TRẮNG
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\s+\.', '.', text)
    text = text.replace(',.', '.')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n+', '\n\n', text)
    return text.strip()