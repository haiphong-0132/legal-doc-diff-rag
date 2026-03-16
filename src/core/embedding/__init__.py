dictionary = {
    'modau': 'Mở đầu',
    'chinh': 'Chính',
    'dieu': 'Điều',
    'khoan': 'Khoản',
    'diem': 'Điểm',
}

def decode_section_id(chunk_id: str) -> str:
    """
    Chuyển đổi chunk_id về dạng dễ hiểu. Ví dụ: "dieu_6.diem_2" -> "Điểm 2 điều 6"
    """
    try:

        levels = chunk_id.strip().split('.')
    
    except Exception as e:
        raise ValueError(f"Invalid chunk_id format: {chunk_id}. Error: {e}")
    
    result = []
    for level in levels:
        le, index = level.split('_', 1)
        index = '.'.join(index.split('_'))
        if le in dictionary:
            result.append(f"{dictionary[le]} {index}")
        else:
            raise ValueError(f"Không nhận diện được loại section {le} trong chunk_id {chunk_id}")
    return ' '.join(result[::-1])