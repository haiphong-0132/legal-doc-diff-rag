import re

def clean_text(text: str) -> str:
    """
    Làm sạch Markdown/text thuần để `output.md` gọn gàng hơn
    """
    # Bỏ YAML frontmatter (--- ... ---) ở đầu file
    text = re.sub(r"^---\s*\n.*?^---\s*\n?", "", text, count=1, flags=re.DOTALL | re.MULTILINE)

    # Bỏ các comment dạng <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Chuẩn hóa newline
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip khoảng trắng đầu/cuối mỗi dòng và bỏ TẤT CẢ dòng trống
    raw_lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in raw_lines if line]

    cleaned = "\n".join(lines)
    return cleaned.strip()
