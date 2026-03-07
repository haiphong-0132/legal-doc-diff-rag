from __future__ import annotations

import re

def clean_text(text: str) -> str:
    """
    Làm sạch Markdown/text thuần để `output.txt` gọn gàng hơn:
    - Chuẩn hóa xuống dòng: \r\n, \r -> \n
    - Xóa khoảng trắng dư ở đầu/cuối mỗi dòng
    - Loại bỏ các comment HTML kiểu `<!-- image -->`
    - Loại bỏ TẤT CẢ dòng trống
    - Loại bỏ khoảng trắng thừa ở đầu/cuối toàn bộ văn bản
    """
    # Bỏ các comment dạng <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Chuẩn hóa newline
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip khoảng trắng đầu/cuối mỗi dòng và bỏ TẤT CẢ dòng trống
    raw_lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in raw_lines if line]

    cleaned = "\n".join(lines)
    return cleaned.strip()
