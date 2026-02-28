from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class ThongTinKyKet(BaseModel):
    vai_tro: Optional[str] = None
    ghi_chu: Optional[str] = None
    noi_dung: Optional[str] = None


class DocMetadata(BaseModel):
    quoc_hieu: Optional[str] = None
    tieu_ngu: Optional[str] = None
    ten_van_ban: Optional[str] = None
    so_hieu: Optional[str] = None
    ngay_ky: Optional[str] = None
    thong_tin_ky_ket: List[ThongTinKyKet] = []


class DinhNghia(BaseModel):
    tu_khoa: str
    y_nghia: str


class Section(BaseModel):
    id: str
    loai: Literal["phan", "chuong", "muc", "tieu_muc", "dieu", "khoan", "diem"]
    tieu_de: Optional[str] = None
    noi_dung: Optional[str] = None
    con: List["Section"] = []


class PhuLuc(BaseModel):
    tieu_de: Optional[str] = None
    noi_dung: Optional[str] = None


class ChuThich(BaseModel):
    chi_so: Optional[str] = None
    noi_dung: Optional[str] = None


class Khac(BaseModel):
    noi_dung: Optional[str] = None


class LegalDocument(BaseModel):
    """Dai dien cho toan bo input JSON."""

    metadata: DocMetadata
    can_cu: List[Any] = []
    dinh_nghia: List[DinhNghia] = []
    noi_dung_chinh: List[Section] = []
    phu_luc: List[PhuLuc] = []
    chu_thich: List[ChuThich] = []
    khac: List[Khac] = Field(default=[], alias="Khac")

class ChunkMetadata(BaseModel):
    """Metadata cho 1 chunk.

    section_id dung de truy vet vi tri chunk trong cau truc van ban.
    Hien tai voi hierarchical chunker, format thuc te la: "HD_<section.id>"
    vi du: "HD_dieu_6.diem_2".
    """

    section_id: str


class ChunkDocument(BaseModel):
    """Dinh dang output chuan cho moi phuong phap chunking.

    Chunker luon tra ve List[ChunkDocument].

    Fields:
    - text: noi dung chunk (string).
    - metadata:
      - hierarchical: co metadata.section_id.
      - fixed_size: thuong la None.

    Vi du (hierarchical):
    {
      "text": "Viec thanh toan tien...",
      "metadata": {"section_id": "HD_dieu_6.diem_2"}
    }

    Vi du (fixed_size):
    {
      "text": "...",
      "metadata": null
    }
    """

    text: str
    metadata: Optional[ChunkMetadata] = None
class EmbeddingRequest(BaseModel):
    """Một đơn vị chunk cần embedding"""
    chunk_id: str   # Duy nhất, lấy từ ChunkMetadata.section_id
    text: str

class EmbeddingResult(BaseModel):
    """Kết quả embed 1 chunk"""
    chunk_id: str
    vector: List[float]     # Vector embedding
    model_name: str         
    token_count: Optional[int] = None   # Số token của chunk để kiểm tra có vượt giới hạn mô hình hay không

# Store in vector database

class ChromaConfig(BaseModel):
    collection_name: str
    persist_directory: str      # Nơi lưu trữ
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"  # Khoảng cách sử dụng trong ChromaDB

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