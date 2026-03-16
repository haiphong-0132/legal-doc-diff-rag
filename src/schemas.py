from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict



class HierarchicalChunkInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    payload: Dict[str, Any] | List[Dict[str, Any]] = Field(
        alias="json",
        description="Raw JSON đầu vào dùng cho hierarchical chunker."
    )


class ChunkMetadata(BaseModel):
    """Metadata cho 1 chunk.
    section_id dung de truy vet vi tri chunk trong cau truc van ban.
    Hien tai voi hierarchical chunker, format thuc te la: "<section.id>"
    vi du: "dieu_6.diem_2".
    """

    section_id: str


class ChunkDocument(BaseModel):
    text: str
    metadata: Optional[ChunkMetadata] = None


#
class ChunkDocumentForHierarchical(BaseModel):
    """Chunk output cho hierarchical gom metadata + tieu de + noi dung + ref."""

    metadata: ChunkMetadata
    tieu_de: Optional[str] = None
    noi_dung: Optional[str] = None
    ref: List[str] = Field(default_factory=list)


class EmbeddingRequest(BaseModel):
    """Một đơn vị chunk cần embedding, hoặc truy vấn của người dùng"""
    chunk_id: str | None = None  # Duy nhất, lấy từ ChunkMetadata.section_id hoặc tự tạo khi khởi tạo
    text: str

class EmbeddingResult(BaseModel):
    """Kết quả embed 1 chunk"""
    chunk_id: str | None = None
    text: str
    vector: List[float]     # Vector embedding
    token_count: Optional[int] = None   # Số token của chunk để kiểm tra có vượt giới hạn mô hình hay không

# Store in vector database

class ChromaConfig(BaseModel):
    collection_name: str
    persist_directory: Optional[str] = None      # Nơi lưu trữ
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"  # Khoảng cách sử dụng trong ChromaDB
    is_persist: bool = False

    @model_validator(mode='after')
    def validate_persistence(self):
        if self.is_persist and not self.persist_directory:
            raise ValueError('persist_directory is required when is_persist=True')
        return self

class ChromaUpsertRequest(BaseModel):
    """Dữ liệu cần upsert vào ChromaDB"""
    chunk_id: str
    vector: List[float]         # Lấy từ EmbeddingResult.vector
    text: str                   # Lấy từ ChunkDocument.text
    metadata: Dict[str, Any]    # Lấy từ ChunkMetadata tương ứng và có thể thêm thông tin khác nếu cần

class ChromaQueryRequest(BaseModel):
    """Yêu cầu truy vấn từ ChromaDB"""
    query_vector: List[float]                   # Embeding của câu truy vấn
    top_k: int = Field(5, gt=0)
    filter: Optional[Dict[str, Any]] = None     # Bộ lọc theo metadata nếu cần

class ChromaQueryResult(BaseModel):
    """Kết quả trả về từ ChromaDB sau khi truy vấn"""
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    distance: float