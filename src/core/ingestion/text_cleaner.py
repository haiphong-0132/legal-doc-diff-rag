import re


def clean_text(text: str) -> str:
    """
    Làm sạch nhẹ nhàng văn bản trước khi chuẩn hoá:
    - Chuẩn hoá xuống dòng
    - Loại bỏ khoảng trắng dư ở đầu/cuối dòng
    - Chuẩn hoá một số bullet (•, –, —) về dấu '-'
    - Giảm số dòng trống liên tiếp
    """
    if not text:
        return ""

    # Chuẩn hoá newline
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Chuẩn hoá bullet dạng ký hiệu sang '- '
    bullet_chars = ["•", "‣", "∙", "◦", "–", "—"]
    for ch in bullet_chars:
        text = text.replace(f"{ch} ", "- ").replace(ch, "- ")

    lines = text.split("\n")
    cleaned_lines = []
    empty_count = 0

    for line in lines:
        # Chỉ strip hai bên, giữ indent nhỏ nếu có
        stripped = line.rstrip()
        if stripped.strip() == "":
            empty_count += 1
            # giới hạn tối đa 1 dòng trống liên tiếp
            if empty_count > 1:
                continue
            cleaned_lines.append("")
        else:
            empty_count = 0
            # thu gọn khoảng trắng giữa các từ
            inner = re.sub(r"\s+", " ", stripped)
            cleaned_lines.append(inner.strip())
    return "\n".join(cleaned_lines).strip()


__all__ = ["clean_text"]

