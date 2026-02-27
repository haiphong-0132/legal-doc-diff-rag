from typing import Callable, List
from src.schemas import LegalDocument, ChunkDocument

# INTERFACE CHO HÀM CHUNKING

# Mọi hàm chunking (fixed_size, hierarchical, v.v.) đều phải tuân thủ chuẩn này:
# Nhận vào 1 đối tượng LegalDocument (Input) -> Trả về danh sách ChunkDocument (Output)
ChunkingFunction = Callable[[LegalDocument], List[ChunkDocument]]