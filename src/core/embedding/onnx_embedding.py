import torch
from glob import glob
from typing import List
import numpy as np
from transformers import AutoTokenizer
import onnxruntime as ort
from src.schemas import EmbeddingRequest, EmbeddingResult


class OnnxEmbeddingModel:
    """
    Class này chạy mô hình embedding được export sang ONNX. 
    Mô hình trả về một tensor last_hidden_state có 
    shape (batch, seq_len, hidden_size) hoặc đã được pooling sẵn thành 
    (batch, hidden_size). Tokenizer được tải từ thư mục model_dir.
    """

    def __init__(self, model_dir: str, onnx_path: str = None):
        self.model_dir = model_dir
        
        try:
            self.onnx_path = onnx_path if onnx_path else glob(f"{model_dir}/onnx/*.onnx")[0]
        except IndexError:
            raise ValueError(f"Không tìm thấy file ONNX trong {model_dir}/onnx/")

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)

        self.providers = ["CUDAExecutionProvider"] if torch.cuda.is_available() else ["CPUExecutionProvider"]

        # Load và tối ưu graph ONNX và tạo runtime session
        self.session = ort.InferenceSession(self.onnx_path, providers=self.providers)
        
        # Lấy tên input và output của session để ánh xạ đúng khi inference
        self.input_names = [inp.name for inp in self.session.get_inputs()]
        self.output_names = [out.name for out in self.session.get_outputs()]
    
    def _prepare_inputs(self, texts: List[str]):
        tokenized = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            return_tensors="np",
        )

        ort_inputs = {}

        if "input_ids" in self.input_names:
            ort_inputs['input_ids'] = tokenized['input_ids'].astype(np.int64)
        else:
            ort_inputs[self.input_names[0]] = tokenized['input_ids'].astype(np.int64)

        if "attention_mask" in self.input_names:
            ort_inputs['attention_mask'] = tokenized['attention_mask'].astype(np.int64)
        elif len(self.input_names) > 1:
            ort_inputs[self.input_names[1]] = tokenized['attention_mask'].astype(np.int64)

        return ort_inputs, tokenized

    def _pool_embeddings(self, model_output: np.ndarray, attention_mask: np.ndarray):
        # Nếu model_output có shape (batch, seq_len, hidden), tức một token được biểu diễn bằng một vector, thì thực hiện mean pooling
        # Nếu model_output đã được pooling sẵn, có shape là (batch, hidden), thì trả về trực tiếp        
        if model_output.ndim == 3:
            mask = attention_mask.astype(np.float32)
            summed = (model_output * mask[..., None]).sum(axis=1)
            denom = mask.sum(axis=1, keepdims=True).clip(min=1e-9)
            emb = summed / denom
        else:
            emb = model_output
    
        norms = np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
        emb = emb / norms
        
        return emb

    def embed(self, requests: List[EmbeddingRequest], batch_size: int=32) -> List[EmbeddingResult]:
        texts = [r.text for r in requests]
        results: List[EmbeddingResult] = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i: i + batch_size]
            ort_inputs, tokenized = self._prepare_inputs(batch_texts)

            outputs = self.session.run(self.output_names, ort_inputs)

            model_output = outputs[0]

            emb = self._pool_embeddings(model_output, tokenized['attention_mask'])

            for j in range(emb.shape[0]):
                vec = emb[j].astype(float).tolist()
                token_count = int(tokenized['attention_mask'][j].sum())

                results.append(
                    EmbeddingResult(
                        chunk_id=requests[i + j].chunk_id,
                        vector=vec,model_name=f'{self.model_dir}-onnx',
                        token_count=token_count
                    )
                )
        
        return results
