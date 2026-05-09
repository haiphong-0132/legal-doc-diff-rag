import json
import argparse
from typing import List, Optional

import numpy as np
import requests
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification


HOST = "127.0.0.1"
PORT = 8000

EMBED_MODEL_NAME = "AITeamVN/Vietnamese_Embedding"
RERANK_MODEL_NAME = "AITeamVN/Vietnamese_Reranker"
LLM_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

API_EMBED_DIM = 1024

EMBED_MAX_LENGTH = 256
RERANK_MAX_LENGTH = 2304
GENERATE_MAX_INPUT_LENGTH = 8000

# Tự ưu tiên GPU NVIDIA nếu có
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Using device: {DEVICE}")

embed_model: Optional[SentenceTransformer] = None
reranker_model: Optional[CrossEncoder] = None
llm_tokenizer: Optional[AutoTokenizer] = None
llm_model: Optional[AutoModelForCausalLM] = None


class EmbedRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)


class GenerateRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[dict]] = None
    max_length: int = 200
    temperature: float = 0.7


class RerankRequest(BaseModel):
    query: str
    documents: List[str] = Field(..., min_length=1)
    top_k: int = 5


app = FastAPI(
    title="Local Multi-Model API",
    description="Embedding + Generation + Rerank APIs chạy local bằng GPU/CPU",
    version="1.0.0",
)


def ensure_embed_dim(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)

    current_dim = arr.shape[1]
    if current_dim == API_EMBED_DIM:
        return arr
    if current_dim > API_EMBED_DIM:
        return arr[:, :API_EMBED_DIM]

    pad_width = API_EMBED_DIM - current_dim
    return np.pad(arr, ((0, 0), (0, pad_width)), mode="constant", constant_values=0.0)


def get_llm_dtype():
    if DEVICE == "cuda":
        # Qwen2.5 chạy tối ưu hơn với bfloat16 nếu GPU hỗ trợ (ví dụ RTX 4090)
        if torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    return torch.float32


def load_models() -> None:
    global embed_model, reranker_model, llm_tokenizer, llm_model

    if embed_model is None:
        print(f"[LOAD] Embedding model: {EMBED_MODEL_NAME}")
        embed_model = SentenceTransformer(EMBED_MODEL_NAME, device=DEVICE)
        embed_model.max_seq_length = EMBED_MAX_LENGTH
        print("[OK] Embedding model loaded")

    if reranker_model is None:
        print(f"[LOAD] Reranker model: {RERANK_MODEL_NAME}")
        reranker_model = CrossEncoder(
            RERANK_MODEL_NAME,
            device=DEVICE,
            max_length=RERANK_MAX_LENGTH,
        )
        print("[OK] Reranker model loaded")

    if llm_tokenizer is None or llm_model is None:
        print(f"[LOAD] LLM model: {LLM_MODEL_NAME}")
        llm_tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)

        llm_model = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL_NAME,
            torch_dtype=get_llm_dtype(),
            low_cpu_mem_usage=True,
        )

        if llm_tokenizer.pad_token is None:
            llm_tokenizer.pad_token = llm_tokenizer.eos_token

        if llm_model.config.pad_token_id is None:
            llm_model.config.pad_token_id = llm_tokenizer.eos_token_id

        llm_model.to(DEVICE)
        llm_model.eval()
        print("[OK] LLM model loaded")


def validate_embed_inputs_not_truncated(
    texts: List[str],
    max_length: int,
) -> None:
    """
    Kiểm tra input embedding có vượt max_length không.

    Nếu vượt, SentenceTransformer có thể truncate text ngầm khi encode.
    Với indexing/vector search, truncate ngầm có thể làm embedding mất thông tin,
    nên trả lỗi rõ ràng.
    """
    assert embed_model is not None

    tokenizer = embed_model.tokenizer
    too_long_items = []

    for index, text in enumerate(texts):
        encoded = tokenizer(
            text,
            add_special_tokens=True,
            truncation=False,
        )

        token_length = len(encoded["input_ids"])

        if token_length > max_length:
            too_long_items.append(
                {
                    "index": index,
                    "token_length": token_length,
                    "max_length": max_length,
                    "text_preview": text[:200],
                }
            )

    if too_long_items:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Embedding input is too long and would be truncated. "
                    "Please chunk the text into smaller pieces or increase EMBED_MAX_LENGTH."
                ),
                "max_length": max_length,
                "too_long_items": too_long_items,
            },
        )


def validate_generate_input_not_truncated(
    prompt: str,
    max_length: int,
) -> None:
    """
    Kiểm tra prompt generate có vượt max_length không.

    Nếu vượt, tokenizer sẽ truncate prompt ngầm. Với RAG, truncate prompt
    có thể làm mất context, nên trả lỗi rõ ràng.
    """
    assert llm_tokenizer is not None

    encoded = llm_tokenizer(
        prompt,
        return_tensors="pt",
        truncation=False,
    )

    token_length = encoded["input_ids"].shape[1]

    if token_length > max_length:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Generate input prompt is too long and would be truncated. "
                    "Please reduce context length or increase GENERATE_MAX_INPUT_LENGTH."
                ),
                "token_length": token_length,
                "max_length": max_length,
                "prompt_preview": prompt[:300],
            },
        )


def validate_rerank_inputs_not_truncated(
    query: str,
    documents: List[str],
    max_length: int,
) -> None:
    """
    Kiểm tra query-document pair có vượt max_length không.

    Nếu vượt, CrossEncoder có thể truncate text ngầm khi predict.
    Với rerank, truncate có thể làm score sai, nên trả lỗi rõ ràng.
    """
    assert reranker_model is not None

    tokenizer = reranker_model.tokenizer
    too_long_items = []

    for index, document in enumerate(documents):
        encoded = tokenizer(
            query,
            document,
            add_special_tokens=True,
            truncation=False,
        )

        token_length = len(encoded["input_ids"])

        if token_length > max_length:
            too_long_items.append(
                {
                    "index": index,
                    "token_length": token_length,
                    "max_length": max_length,
                    "document_preview": document[:200],
                }
            )

    if too_long_items:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Rerank input is too long and would be truncated. "
                    "Please chunk the document into smaller pieces or increase RERANK_MAX_LENGTH."
                ),
                "max_length": max_length,
                "too_long_items": too_long_items,
            },
        )


@app.on_event("startup")
def startup_event() -> None:
    print("[START] Server starting...")
    print(f"[INFO] HOST={HOST} PORT={PORT} DEVICE={DEVICE}")

    if DEVICE == "cuda":
        print(f"[INFO] CUDA device count: {torch.cuda.device_count()}")
        print(f"[INFO] CUDA device name: {torch.cuda.get_device_name(0)}")

    load_models()
    print("[READY] All models loaded successfully")


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "FastAPI server is running",
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "endpoints": ["/embed", "/generate", "/rerank", "/docs"],
    }


@app.post("/embed")
def embed(req: EmbedRequest):
    try:
        assert embed_model is not None

        validate_embed_inputs_not_truncated(
            texts=req.texts,
            max_length=EMBED_MAX_LENGTH,
        )

        embeddings = embed_model.encode(
            req.texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        embeddings = ensure_embed_dim(np.asarray(embeddings, dtype=np.float32))
        return {
            "embeddings": embeddings.tolist(),
            "dimension": API_EMBED_DIM,
            "device": DEVICE,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding error: {exc}") from exc


@app.post("/generate")
def generate(req: GenerateRequest):
    try:
        assert llm_tokenizer is not None and llm_model is not None

        if req.messages is not None:
            messages = req.messages
        elif req.prompt is not None:
            messages = [{"role": "user", "content": req.prompt}]
        else:
            raise HTTPException(
                status_code=422,
                detail="Either 'prompt' or 'messages' must be provided in the request body."
            )

        # Sử dụng chat template của Qwen2.5-7B-Instruct để định dạng prompt có cấu trúc hệ thống/người dùng
        formatted_prompt = llm_tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        validate_generate_input_not_truncated(
            prompt=formatted_prompt,
            max_length=GENERATE_MAX_INPUT_LENGTH,
        )

        max_new_tokens = max(1, min(req.max_length, 512))

        inputs = llm_tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=False,
        )
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

        with torch.no_grad():
            gen_kwargs = {
                "max_new_tokens": max_new_tokens,
                "pad_token_id": llm_tokenizer.eos_token_id,
                "eos_token_id": llm_tokenizer.eos_token_id,
            }

            # Only add sampling parameters if model supports them
            if req.temperature > 0:
                gen_kwargs["do_sample"] = True
                gen_kwargs["temperature"] = max(req.temperature, 1e-5)
                gen_kwargs["top_p"] = 0.95

            try:
                output_ids = llm_model.generate(**inputs, **gen_kwargs)
            except TypeError:
                # Fallback: model doesn't support these parameters
                gen_kwargs = {
                    "max_new_tokens": max_new_tokens,
                    "pad_token_id": llm_tokenizer.eos_token_id,
                    "eos_token_id": llm_tokenizer.eos_token_id,
                }
                output_ids = llm_model.generate(**inputs, **gen_kwargs)

        # Lấy chiều dài của input ban đầu để chỉ cắt và decode phần text mới sinh ra (answer)
        input_length = inputs["input_ids"].shape[1]
        new_ids = output_ids[0][input_length:]
        answer = llm_tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        return {
            "prompt": req.prompt if req.prompt is not None else "",
            "messages": messages,
            "answer": answer,
            "device": DEVICE,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation error: {exc}") from exc


@app.post("/rerank")
def rerank(req: RerankRequest):
    try:
        assert reranker_model is not None

        validate_rerank_inputs_not_truncated(
            query=req.query,
            documents=req.documents,
            max_length=RERANK_MAX_LENGTH,
        )

        pairs = [[req.query, doc] for doc in req.documents]
        scores = reranker_model.predict(pairs)

        ranked = sorted(
            [
                {
                    "index": index,
                    "document": doc,
                    "score": float(score),
                }
                for index, (doc, score) in enumerate(zip(req.documents, scores))
            ],
            key=lambda x: x["score"],
            reverse=True,
        )

        top_k = max(1, min(req.top_k, len(ranked)))
        results = []
        for i, item in enumerate(ranked[:top_k], start=1):
            results.append(
                {
                    "rank": i,
                    "index": item["index"],
                    "document": item["document"],
                    "score": item["score"],
                }
            )

        return {
            "query": req.query,
            "results": results,
            "device": DEVICE,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rerank error: {exc}") from exc


def pretty_print(title: str, data) -> None:
    print(f"\n--- {title} ---")
    try:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
    except Exception:
        print(data)


def run_self_test(base_url: str) -> None:
    print(f"[TEST] Testing APIs via: {base_url}")

    embed_payload = {
        "texts": [
            "Xin chào, đây là câu tiếng Việt.",
            "FastAPI chạy local bằng GPU.",
        ]
    }
    r1 = requests.post(f"{base_url}/embed", json=embed_payload, timeout=120)
    embed_result = r1.json()
    pretty_print(
        "TEST /embed",
        {
            "status_code": r1.status_code,
            "dimension": embed_result.get("dimension"),
            "num_embeddings": len(embed_result.get("embeddings", [])),
            "device": embed_result.get("device"),
        },
    )

    generate_payload = {
        "prompt": "Question: FastAPI là gì?\nAnswer:",
        "max_length": 80,
        "temperature": 0.7,
    }
    r2 = requests.post(f"{base_url}/generate", json=generate_payload, timeout=180)
    pretty_print("TEST /generate", {"status_code": r2.status_code, "response": r2.json()})

    rerank_payload = {
        "query": "framework để build API Python nhanh",
        "documents": [
            "FastAPI là framework hiện đại để xây dựng API với Python.",
            "NumPy dùng cho tính toán ma trận.",
            "Localhost là địa chỉ loopback trên máy tính.",
            "Transformers hỗ trợ mô hình ngôn ngữ.",
        ],
        "top_k": 3,
    }
    r3 = requests.post(f"{base_url}/rerank", json=rerank_payload, timeout=120)
    pretty_print("TEST /rerank", {"status_code": r3.status_code, "response": r3.json()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local NLP FastAPI service")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")
    parser.add_argument("--self-test", action="store_true", help="Run HTTP tests after server starts")
    args = parser.parse_args()

    if args.self_test:
        import threading
        import time

        def run_server() -> None:
            uvicorn.run(app, host=args.host, port=args.port, log_level="info")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        base_url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"

        start = time.time()
        while time.time() - start < 180:
            try:
                r = requests.get(f"{base_url}/", timeout=3)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("FastAPI server did not start in time.")

        run_self_test(base_url)
    else:
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)