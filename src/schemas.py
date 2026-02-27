from typing import List, Optional, Any, Literal
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
    con: List['Section'] = [] # Đệ quy tự trỏ vào chính nó

class PhuLuc(BaseModel):
    tieu_de: Optional[str] = None
    noi_dung: Optional[str] = None

class ChuThich(BaseModel):
    chi_so: Optional[str] = None
    noi_dung: Optional[str] = None

class Khac(BaseModel):
    noi_dung: Optional[str] = None

class LegalDocument(BaseModel):
    """Đại diện cho toàn bộ Input JSON"""
    metadata: DocMetadata
    can_cu: List[Any] = []
    dinh_nghia: List[DinhNghia] = []
    noi_dung_chinh: List[Section] = []
    phu_luc: List[PhuLuc] = []
    chu_thich: List[ChuThich] = []
    khac: List[Khac] = Field(default=[], alias="Khac")


class ChunkMetadata(BaseModel):
    # Bắt buộc phải có section_id theo format: doc_id_cấp1_cấp2_..._cấp_hiện_tại
    section_id: str 

class ChunkDocument(BaseModel):
    """Đại diện cho Output sau khi chunking"""
    text: str
    metadata: ChunkMetadata