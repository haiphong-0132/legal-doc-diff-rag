import json
import re
import urllib.request
from typing import Any, Dict, List

from src.core.chunker.hierarchical import HierarchicalChunker
from src.core.chunker.legal_parser import build_json_tree
from src.core.embedding import decode_section_id
from src.core.embedding.embedding import EmbeddingPipeline
from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
from src.core.ingestion.extractor import extract_file
from src.schemas import ChunkDocumentForHierarchical, EmbeddingResult

from src.core.matching.config import OLLAMA_MODEL, OLLAMA_URL, logger
from src.core.matching.types import ChunkRecord


def format_chunk(chunk: ChunkDocumentForHierarchical, for_llm: bool = False) -> str:
    if not for_llm:
        raw = f"Tieu de: {chunk.tieu_de or ''}\nNoi dung: {chunk.noi_dung or ''}\nRef: {', '.join(chunk.ref or [])}"
        return re.sub(r"\s+", " ", raw).strip()

    ma_doan = chunk.metadata.section_id
    try:
        ma_doan = decode_section_id(ma_doan)
    except ValueError:
        pass

    noi_dung = chunk.noi_dung or chunk.tieu_de or "(trống)"
    vien_dan = ", ".join([decode_section_id(r) if r else r for r in (chunk.ref or [])]) or "Không có"

    return f"Mã đoạn: {ma_doan}\nNội dung: {noi_dung}\nCác viện dẫn: {vien_dan}"


def load_chunks(file_path: str) -> List[ChunkDocumentForHierarchical]:
    logger.info("Ingestion started for %s", file_path)
    payload = build_json_tree(extract_file(file_path))
    logger.info("Built JSON tree for %s", file_path)
    chunks = HierarchicalChunker().chunk({"payload": payload})
    logger.info("Loaded %d chunks from %s", len(chunks), file_path)
    return chunks


def embed_chunks(chunks: List[ChunkDocumentForHierarchical], model: OnnxEmbeddingModel) -> List[ChunkRecord]:
    logger.info("Embedding %d chunks", len(chunks))
    pipeline = EmbeddingPipeline(chunk_documents=chunks)
    requests = pipeline._to_embedding_requests()
    embeddings = model.embed(requests)

    req_map = {r.chunk_id: r.text for r in requests if r.chunk_id}
    vec_map = {e.chunk_id: e.vector for e in embeddings if e.chunk_id}

    records = [
        ChunkRecord(chunk=c, query_text=req_map.get(c.metadata.section_id, ""), vector=vec_map.get(c.metadata.section_id))
        for c in chunks
    ]
    logger.info("Embedding finished: %d/%d chunks have vectors", sum(1 for record in records if record.vector), len(records))
    return records


def build_embedding_results(records: List[ChunkRecord]) -> List[EmbeddingResult]:
    results: List[EmbeddingResult] = []
    for record in records:
        if not record.vector:
            continue
        results.append(EmbeddingResult(chunk_id=record.chunk.metadata.section_id, text=record.query_text, vector=record.vector))
    logger.info("Prepared %d embedding results for vector store", len(results))
    return results


def call_ollama(prompt: str) -> str:
    logger.info("Calling Ollama model=%s url=%s prompt_chars=%d", OLLAMA_MODEL, OLLAMA_URL, len(prompt))
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        response = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    logger.info("Ollama response received: %d chars", len(response))
    return response


def parse_json_response(raw_text: str) -> Dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))
