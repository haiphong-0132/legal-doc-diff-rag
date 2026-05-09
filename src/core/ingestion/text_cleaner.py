import re
import tempfile
import subprocess
from pathlib import Path
from html import unescape

def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML content for chunking and embedding.
    
    Removes all HTML tags and entities, normalizes whitespace.
    
    Args:
        html: HTML content from Pandoc conversion
        
    Returns:
        Clean plain text ready for chunking and embedding
    """
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
    
    return text.strip()


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