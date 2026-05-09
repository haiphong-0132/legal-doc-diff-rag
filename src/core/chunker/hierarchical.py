from __future__ import annotations

from typing import Any, Dict, List, Literal

from src.schemas import (
    ChunkDocumentForHierarchical,
    ChunkMetadata,
    HierarchicalChunkInput,
)
from src.core.matching.scoring import extract_keywords


def build_node_registry(nodes: List[Dict[str, Any]], registry: Dict[str, Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Phẳng hóa và tối ưu hóa cây JSON bằng duyệt đệ quy bottom-up (Post-order Traversal).
    Mỗi node chỉ được duyệt đúng 1 lần duy nhất (O(N) Complexity).
    """
    if registry is None:
        registry = {}

    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue

        # 1. Đăng ký node vào Registry phẳng O(1)
        registry[node_id] = node

        # 2. Đệ quy xử lý tất cả các con trước (Bottom-Up)
        children = node.get("con", [])
        build_node_registry(children, registry)

        # 3. Gộp tiêu đề và nội dung của chính nó với nội dung đã gộp & cache sẵn của các con trực tiếp.
        node_loai = str(node.get("loai") or "").strip().lower()
        own_title = str(node.get("tieu_de") or "").strip()
        own_content = str(node.get("noi_dung") or "").strip()
        
        all_texts = []
        # Chỉ gộp tiêu đề vào merged_text nếu node không phải là "khoan" hoặc "diem"
        if own_title and node_loai not in ["khoan", "diem"]:
            all_texts.append(own_title)
        if own_content:
            all_texts.append(own_content)

        # Lấy trực tiếp kết quả cache O(1) từ các con trực tiếp đã tính xong ở bước đệ quy trước
        for child in children:
            child_merged = child.get("cached_merged_text", "")
            if child_merged:
                all_texts.append(child_merged)

        merged_text = "\n".join(all_texts) if all_texts else ""
        
        # 4. Cache kết quả gộp văn bản của node hiện tại
        node["cached_merged_text"] = merged_text

        # 5. Phân tích và Cache sẵn tập keywords
        node["cached_keywords"] = set(extract_keywords(merged_text))

    return registry


class HierarchicalChunker:

    def __init__(self, max_tokens: int = 512, chunk_by: Literal["dieu", "khoan", "diem"] = "dieu"):
        self.max_tokens = max_tokens
        self.chunk_by = chunk_by

    def _count_tokens(self, text: str) -> int:
        """Ước lượng số lượng token cho tiếng Việt: 1 từ tiếng Việt ~ 1.5 tokens."""
        if not text:
            return 0
        words = text.split()
        return int(len(words) * 1.5)

    def chunk(
        self,
        data: HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        document = self._validate_input(data)
        root_nodes = self._get_root_nodes(document)

        # 1. Dựng registry phẳng và pre-calculate/cache toàn bộ nội dung gộp
        registry = build_node_registry(root_nodes)

        # 2. Duyệt cây để tạo chunks dựa trên dữ liệu đã cache
        chunks: List[ChunkDocumentForHierarchical] = []
        for node in root_nodes:
            chunks.extend(self._walk_node(node=node, registry=registry))

        return chunks

    def _validate_input(
        self,
        data: HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> HierarchicalChunkInput:
        if isinstance(data, HierarchicalChunkInput):
            return data

        if isinstance(data, list):
            return HierarchicalChunkInput(payload=data)

        if isinstance(data, dict) and ("json" in data or "payload" in data):
            return HierarchicalChunkInput.model_validate(data)

        if isinstance(data, dict):
            return HierarchicalChunkInput(payload=data)

        raise TypeError("HierarchicalChunker.chunk expects HierarchicalChunkInput, dict, or list[dict]")

    def _get_root_nodes(self, document: HierarchicalChunkInput) -> List[Dict[str, Any]]:
        if isinstance(document.payload, list):
            return document.payload
        return [document.payload]

    def _walk_node(
        self,
        *,
        node: Dict[str, Any],
        registry: Dict[str, Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        chunks: List[ChunkDocumentForHierarchical] = []

        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("loai") or "").strip().lower()

        # Nếu gặp node Điều
        if node_type == "dieu":
            article_title = self._as_clean_str(node.get("tieu_de")) or ""

            if self.chunk_by == "dieu":
                # Chế độ mặc định: Thử gộp Điều, nếu dài quá thì rã xuống Khoản/Điểm
                return self._process_dieu_level(node, registry)

            elif self.chunk_by == "khoan":
                # Chế độ Khoản: Bỏ qua tạo chunk Điều gộp, đi thẳng xuống các Khoản con để xử lý
                for child in self._get_children(node):
                    chunks.extend(self._process_clause_node(child, node_id, registry))
                return chunks

            elif self.chunk_by == "diem":
                # Chế độ Điểm: Đi thẳng xuống các Khoản và Điểm con
                for child in self._get_children(node):
                    clause_title = self._as_clean_str(child.get("tieu_de")) or ""
                    clause_content = self._as_clean_str(child.get("noi_dung")) or ""

                    diem_nodes = self._get_children(child)
                    for diem in diem_nodes:
                        chunks.extend(self._process_point_node(
                            node=diem,
                            article_title=article_title,
                            clause_title=clause_title,
                            clause_content=clause_content,
                            registry=registry
                        ))
                return chunks

        # Nếu gặp trực tiếp node Khoản ngoài luồng (khi chạy chunk trên một Khoản riêng biệt)
        if self.chunk_by == "diem" and node_type == "khoan":
            parent_id = "mo_dau"
            if ".khoan_" in node_id:
                parent_id = node_id.split(".khoan_")[0]
            
            article_node = registry.get(parent_id) or {}
            article_title = self._as_clean_str(article_node.get("tieu_de")) or ""
            
            clause_title = self._as_clean_str(node.get("tieu_de")) or ""
            clause_content = self._as_clean_str(node.get("noi_dung")) or ""

            diem_nodes = self._get_children(node)
            for diem in diem_nodes:
                chunks.extend(self._process_point_node(
                    node=diem,
                    article_title=article_title,
                    clause_title=clause_title,
                    clause_content=clause_content,
                    registry=registry
                ))
            return chunks

        # Lấy nội dung riêng của node đó (không gộp)
        chunk = self._build_chunk_from_registry(node_id, registry, use_merged=False)
        if chunk is not None:
            chunks.append(chunk)

        # Tiếp tục duyệt sâu vào các con
        for child in self._get_children(node):
            chunks.extend(self._walk_node(node=child, registry=registry))

        return chunks

    def _process_dieu_level(
        self,
        node: Dict[str, Any],
        registry: Dict[str, Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        chunks: List[ChunkDocumentForHierarchical] = []
        node_id = str(node.get("id") or "").strip()

        # 1. Thử tạo chunk cho cả Điều (gộp)
        article_chunk = self._build_chunk_from_registry(node_id, registry, use_merged=True)
        if article_chunk:
            content_text = article_chunk.noi_dung or ""
            token_count = self._count_tokens(content_text)
            
            # NẾU CẢ ĐIỀU <= max_tokens -> TRẢ VỀ CHUNK ĐIỀU DUY NHẤT
            if token_count <= self.max_tokens:
                return [article_chunk]
        
        # 2. NẾU CẢ ĐIỀU > max_tokens -> FALLBACK 1: Duyệt xuống các Khoản con
        if article_chunk and article_chunk.tieu_de:
            chunks.append(ChunkDocumentForHierarchical(
                metadata=ChunkMetadata(section_id=f"{node_id}_header"),
                tieu_de=article_chunk.tieu_de,
                noi_dung="",
                ref=article_chunk.ref
            ))

        # Duyệt qua các Khoản trực thuộc Điều này
        for child in self._get_children(node):
            chunks.extend(self._process_clause_node(child, node_id, registry))
            
        return chunks

    def _process_clause_node(
        self,
        node: Dict[str, Any],
        parent_article_id: str,
        registry: Dict[str, Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        chunks: List[ChunkDocumentForHierarchical] = []
        node_id = str(node.get("id") or "").strip()
        
        # 1. Dựng nội dung Khoản theo định dạng chính xác của người dùng:
        # Điều <số điều>: <Tiêu đề điều> (article_title)
        # Khoản <số khoản>: (clause_title)
        # <nội dung khoản gộp cả điểm> (clause_merged_text)
        article_node = registry.get(parent_article_id) or {}
        article_title = self._as_clean_str(article_node.get("tieu_de")) or ""
        
        clause_title = self._as_clean_str(node.get("tieu_de")) or ""
        clause_content = self._as_clean_str(node.get("noi_dung")) or ""
        clause_merged_text = self._as_clean_str(node.get("cached_merged_text")) or ""
        
        clause_chunk_content = f"{article_title}\n{clause_title}:\n{clause_merged_text}".strip()
        
        token_count = self._count_tokens(clause_chunk_content)
        
        # NẾU KHOẢN <= max_tokens -> TRẢ VỀ CHUNK KHOẢN HOÀN CHỈNH
        if token_count <= self.max_tokens:
            chunks.append(ChunkDocumentForHierarchical(
                metadata=ChunkMetadata(section_id=node_id),
                tieu_de=clause_content,  # tieu_de là nội dung gốc của chính khoản đó
                noi_dung=clause_chunk_content,  # noi_dung là full_text lồng ghép đầy đủ ngữ cảnh
                ref=self._get_refs(node)
            ))
            return chunks
            
        # 2. NẾU KHOẢN VẪN > max_tokens -> FALLBACK 2: Duyệt xuống các Điểm con
        diem_nodes = self._get_children(node)
        if not diem_nodes:
            # Nếu không có Điểm con mà Khoản vẫn quá dài, bắt buộc giữ lại Khoản làm chunk duy nhất
            chunks.append(ChunkDocumentForHierarchical(
                metadata=ChunkMetadata(section_id=node_id),
                tieu_de=clause_content,
                noi_dung=clause_chunk_content,
                ref=self._get_refs(node)
            ))
            return chunks

        for child in diem_nodes:
            chunks.extend(self._process_point_node(
                node=child,
                article_title=article_title,
                clause_title=clause_title,
                clause_content=clause_content,
                registry=registry
            ))
            
        return chunks

    def _process_point_node(
        self,
        node: Dict[str, Any],
        article_title: str,
        clause_title: str,
        clause_content: str,
        registry: Dict[str, Dict[str, Any]],
    ) -> List[ChunkDocumentForHierarchical]:
        node_id = str(node.get("id") or "").strip()
        point_title = self._as_clean_str(node.get("tieu_de")) or ""
        point_content = self._as_clean_str(node.get("noi_dung")) or ""
        
        # Định dạng nội dung của chunk Điểm:
        # Điều <số điều>: <Tiêu đề điều>
        # Khoản <số khoản>: <Tiêu đề + nội dung khoản chứa điều>
        # Điểm <số điểm>:
        # Tiêu đề điểm + nội dung
        point_chunk_content = (
            f"{article_title}\n"
            f"{clause_title}: {clause_content}\n"
            f"{point_title}:\n"
            f"{point_content}"
        ).strip()
        
        return [ChunkDocumentForHierarchical(
            metadata=ChunkMetadata(section_id=node_id),
            tieu_de=point_content,  # tieu_de là nội dung gốc của chính điểm đó
            noi_dung=point_chunk_content,  # noi_dung là full_text lồng ghép đầy đủ ngữ cảnh
            ref=self._get_refs(node)
        )]

    def _build_chunk_from_registry(
        self,
        node_id: str,
        registry: Dict[str, Dict[str, Any]],
        use_merged: bool = False,
    ) -> ChunkDocumentForHierarchical | None:
        node = registry.get(node_id)
        if not node:
            return None

        title = self._as_clean_str(node.get("tieu_de"))
        
        # Sử dụng nội dung gộp đã cache hoặc nội dung thô riêng lẻ
        if use_merged:
            content = self._as_clean_str(node.get("cached_merged_text"))
        else:
            content = self._as_clean_str(node.get("noi_dung"))

        refs = self._get_refs(node)

        if not any([title, content, refs]):
            return None
        if not node_id:
            raise ValueError("Each hierarchical node must contain a non-empty 'id'")

        metadata = ChunkMetadata(section_id=node_id)

        return ChunkDocumentForHierarchical(
            metadata=metadata,
            tieu_de=title,
            noi_dung=content,
            ref=refs,
        )

    def _get_children(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        children = node.get("con", [])
        if not isinstance(children, list):
            return []
        return [child for child in children if isinstance(child, dict)]

    def _get_refs(self, node: Dict[str, Any]) -> List[str]:
        refs = node.get("ref", [])
        if not isinstance(refs, list):
            return []
        return [str(ref).strip() for ref in refs if str(ref).strip()]

    def _as_clean_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None