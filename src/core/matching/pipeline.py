from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from FlagEmbedding import FlagReranker

from src.core.embedding.embedding import EmbeddingPipeline
from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
from src.core.vector_store.chroma_store import ChromaStore
from src.core.vector_store.vectorstore import VectorStorePipeline
from src.schemas import ChromaConfig, ChromaQueryRequest, ChunkDocumentForHierarchical

from .config import PipelineConfig
from .ollama_client import OllamaClient, parse_llm_json
from .report import write_pair_match_report
from .types import Candidate, ChunkRecord, MatchResult, UnresolvedItem
from .utils import chunk_raw_key, chunk_text_for_display, load_hierarchical_chunks

logger = logging.getLogger("pair_match_pipeline")


class PairMatchPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        embedding_model: Optional[OnnxEmbeddingModel] = None,
        reranker: Optional[FlagReranker] = None,
        ollama: Optional[OllamaClient] = None,
        vector_store: Optional[Any] = None,
        chunks_loader=load_hierarchical_chunks,
    ):
        self.config = config
        self.config.validate()

        self.embedding_model = embedding_model or OnnxEmbeddingModel(model_dir=self.config.embedding_model_dir)
        self.reranker = reranker or FlagReranker(self.config.reranker_model_dir, use_fp16=False, devices="cpu")
        self.ollama = ollama or OllamaClient(self.config)
        self.vector_store = vector_store
        self.chunks_loader = chunks_loader

        self.results: List[MatchResult] = []
        self.unresolved: List[UnresolvedItem] = []

        self.vb1_records: List[ChunkRecord] = []
        self.vb2_records: List[ChunkRecord] = []
        self.vb1_map: Dict[str, ChunkDocumentForHierarchical] = {}
        self.vb2_map: Dict[str, ChunkDocumentForHierarchical] = {}
        self.vb1_record_map: Dict[str, ChunkRecord] = {}

    def _build_records(
        self, source: str, chunks: List[ChunkDocumentForHierarchical]
    ) -> Tuple[List[ChunkRecord], List[Any]]:
        logger.info("Embedding all chunks for %s (count=%d)", source, len(chunks))
        pipeline = EmbeddingPipeline(chunk_documents=chunks)
        requests = pipeline._to_embedding_requests()
        embeddings = self.embedding_model.embed(requests)

        request_by_id = {r.chunk_id: r.text for r in requests if r.chunk_id}
        vector_by_id = {e.chunk_id: e.vector for e in embeddings if e.chunk_id}

        records = [
            ChunkRecord(
                source=source,
                chunk=chunk,
                query_text=request_by_id.get(chunk.metadata.section_id, ""),
                vector=vector_by_id[chunk.metadata.section_id],
            )
            for chunk in chunks
            if chunk.metadata.section_id in vector_by_id
        ]
        return records, embeddings

    def _phase_exact_match(self) -> List[ChunkRecord]:
        vb1_pool: Dict[str, List[ChunkRecord]] = {}
        for rec in self.vb1_records:
            vb1_pool.setdefault(chunk_raw_key(rec.chunk), []).append(rec)

        unmatched_vb2: List[ChunkRecord] = []
        for vb2_record in self.vb2_records:
            key = chunk_raw_key(vb2_record.chunk)
            chosen = next((c for c in vb1_pool.get(key, []) if not c.matched), None)

            if not chosen:
                unmatched_vb2.append(vb2_record)
                continue

            vb2_record.set_match(chosen.section_id, "raw_exact")
            chosen.set_match(vb2_record.section_id, "raw_exact")

            self.results.append(
                MatchResult(
                    vb2_chunk_id=vb2_record.section_id,
                    vb1_chunk_id=chosen.section_id,
                    method="raw_exact",
                    distance=None,
                    rerank_score=None,
                    confidence=1.0,
                    reason="Exact raw-content match (ignore section_id)",
                )
            )
            logger.info("Raw exact match: VB2 %s -> VB1 %s", vb2_record.section_id, chosen.section_id)

        return unmatched_vb2

    def _phase_semantic_match(self, retrieval_targets: List[ChunkRecord]) -> None:
        total_targets = len(retrieval_targets)
        logger.info("Starting retrieval phase for remaining VB2 chunks (total=%d)", total_targets)

        for idx, vb2_record in enumerate(retrieval_targets, start=1):
            pct = (idx / max(total_targets, 1)) * 100.0
            logger.info("[Retrieval %d/%d - %.1f%%] chunk=%s", idx, total_targets, pct, vb2_record.section_id)

            retrieved = self.vector_store.query(
                ChromaQueryRequest(query_vector=vb2_record.vector, top_k=self.config.top_k)
            )

            pairs = [[vb2_record.query_text, r.text] for r in retrieved]
            if not pairs:
                self.unresolved.append({"vb2_record": vb2_record, "candidates": []})
                continue

            scores = self.reranker.compute_score(pairs, normalize=True)
            scored = sorted(zip(retrieved, scores), key=lambda x: x[1], reverse=True)
            candidates = [
                Candidate(chunk_id=item.chunk_id, distance=float(item.distance), rerank_score=float(score))
                for item, score in scored
            ]

            best = candidates[0]
            if best.distance < self.config.distance_threshold and best.rerank_score >= self.config.rerank_threshold:
                vb2_record.set_match(best.chunk_id, "threshold")
                if best.chunk_id in self.vb1_record_map:
                    self.vb1_record_map[best.chunk_id].set_match(vb2_record.section_id, "threshold")

                self.results.append(
                    MatchResult(
                        vb2_chunk_id=vb2_record.section_id,
                        vb1_chunk_id=best.chunk_id,
                        method="threshold",
                        distance=best.distance,
                        rerank_score=best.rerank_score,
                        confidence=1.0,
                        reason="Matched by distance+rerank threshold",
                    )
                )
            else:
                self.unresolved.append({"vb2_record": vb2_record, "candidates": candidates})

    def _phase_llm_fallback(self) -> None:
        logger.info("Retrieval phase complete. Unresolved=%d", len(self.unresolved))

        for item in self.unresolved:
            vb2_record = item["vb2_record"]
            candidates: List[Candidate] = item["candidates"]

            llm_data = self._llm_prompt_match(vb2_record.chunk, candidates)
            match_id = str(llm_data.get("match_chunk_id", "NONE"))
            confidence = float(llm_data.get("confidence", 0.0))
            reason = str(llm_data.get("reason", "No suitable match"))

            if match_id != "NONE" and match_id in self.vb1_map:
                chosen = next((c for c in candidates if c.chunk_id == match_id), None)
                vb2_record.set_match(match_id, "llm")
                if match_id in self.vb1_record_map:
                    self.vb1_record_map[match_id].set_match(vb2_record.section_id, "llm")

                self.results.append(
                    MatchResult(
                        vb2_chunk_id=vb2_record.section_id,
                        vb1_chunk_id=match_id,
                        method="llm",
                        distance=chosen.distance if chosen else None,
                        rerank_score=chosen.rerank_score if chosen else None,
                        confidence=confidence,
                        reason=reason,
                    )
                )
            else:
                best = candidates[0] if candidates else None
                vb2_record.set_match(None, "unmatched")
                self.results.append(
                    MatchResult(
                        vb2_chunk_id=vb2_record.section_id,
                        vb1_chunk_id=None,
                        method="unmatched",
                        distance=best.distance if best else None,
                        rerank_score=best.rerank_score if best else None,
                        confidence=confidence,
                        reason=reason,
                    )
                )

    def _llm_prompt_match(self, vb2_chunk: ChunkDocumentForHierarchical, candidates: List[Candidate]) -> Dict[str, Any]:
        if not candidates:
            return {"match_chunk_id": "NONE", "confidence": 0.0, "reason": "No candidate retrieved"}

        candidate_lines: List[str] = []
        for idx, c in enumerate(candidates, start=1):
            vb1_text = chunk_text_for_display(self.vb1_map.get(c.chunk_id))
            candidate_lines.append(
                f"{idx}. chunk_id={c.chunk_id}\ndistance={c.distance:.6f}\nrerank_score={c.rerank_score:.6f}\n{vb1_text}\n"
            )

        prompt = f"""
Ban la tro ly ghep cap dieu khoan phap ly giua 2 phien ban van ban.
Nhiem vu: chon dung 1 chunk VB1 phu hop nhat voi chunk VB2, hoac tra ve NONE.

QUY TAC:
- Uu tien ma doan (dieu/khoan/diem), noi dung ngu nghia, vi tri tuong doi.
- Co the chap nhan khong trung khop 1-1 neu cau truc bi gop/tach.
- Neu khong du tin cay, tra ve NONE.
- Chi tra ve JSON hop le, KHONG them text.

JSON schema:
{{
  "match_chunk_id": "<VB1 chunk_id or NONE>",
  "confidence": <float 0..1>,
  "reason": "<ngan gon>"
}}

VB2 chunk:
chunk_id={vb2_chunk.metadata.section_id}
{chunk_text_for_display(vb2_chunk)}

Candidates from VB1:
{chr(10).join(candidate_lines)}
""".strip()

        try:
            raw = self.ollama.generate(prompt)
            return parse_llm_json(raw)
        except Exception as exc:
            return {"match_chunk_id": "NONE", "confidence": 0.0, "reason": f"LLM error: {exc}"}

    def _ensure_vector_store(self, vb1_embeddings: List[Any]) -> None:
        if self.vector_store is not None:
            return
        collection_name = self.config.chroma_collection_name or f"vb1_idx_{int(time.time())}"
        self.vector_store = ChromaStore(
            ChromaConfig(
                collection_name=collection_name,
                is_persist=bool(self.config.chroma_is_persist),
                persist_directory=str(Path(self.config.chroma_persist_directory)) if self.config.chroma_is_persist else None,
                distance_metric=self.config.chroma_distance_metric,
            )
        )
        VectorStorePipeline(embeddings=vb1_embeddings).run(self.vector_store, batch_size=32)
        logger.info("VB1 indexed into vector store: %s", collection_name)

    def run(self) -> Any:
        start_time = time.time()
        logger.info("=== Pair Match Pipeline Started ===")

        vb1_chunks = self.chunks_loader(self.config.vb1_path)
        vb2_chunks = self.chunks_loader(self.config.vb2_path)

        self.vb1_records, vb1_embeddings = self._build_records("VB1", vb1_chunks)
        self.vb2_records, _ = self._build_records("VB2", vb2_chunks)

        self.vb1_map = {r.section_id: r.chunk for r in self.vb1_records}
        self.vb2_map = {r.section_id: r.chunk for r in self.vb2_records}
        self.vb1_record_map = {r.section_id: r for r in self.vb1_records}

        self._ensure_vector_store(vb1_embeddings)

        unmatched_vb2 = self._phase_exact_match()
        self._phase_semantic_match(unmatched_vb2)
        self._phase_llm_fallback()

        out_path = write_pair_match_report(
            results=self.results,
            vb1_map=self.vb1_map,
            vb2_map=self.vb2_map,
            vb1_path=self.config.vb1_path,
            vb2_path=self.config.vb2_path,
            distance_threshold=self.config.distance_threshold,
            rerank_threshold=self.config.rerank_threshold,
        )
        logger.info("Report saved to: %s", out_path)
        logger.info("=== Pipeline Finished in %.2fs ===", time.time() - start_time)
        return out_path

