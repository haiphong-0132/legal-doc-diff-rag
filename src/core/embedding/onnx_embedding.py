import os
import shutil
from glob import glob
from typing import Dict, List, Literal
import numpy as np
import onnxruntime as ort
from tqdm import tqdm
from src.schemas import EmbeddingRequest, EmbeddingResult

os.environ["OMP_NUM_THREADS"] = str(os.cpu_count())
os.environ["MKL_NUM_THREADS"] = str(os.cpu_count())
os.environ["TOKENIZERS_PARALLELISM"] = "true"

_TOKENIZER_CACHE: Dict[str, object] = {}
_ONNX_SESSION_CACHE: Dict[str, object] = {}

class OnnxEmbeddingModel:
    """
    Class này chạy mô hình embedding được export sang ONNX.
    Hỗ trợ các pooling strategy: auto, cls, mean, none.
    Tự động detect CUDA nếu có.
    """

    def __init__(
        self,
        model_dir: str,
        pooling: Literal["auto", "cls", "mean", "none"] = "auto",
        max_length: int = 2048,       # Mỗi model có max_length khác nhau, truyền vào khi khởi tạo
        normalize: bool = False,      # Một số model đã normalize sẵn, set False để tránh normalize 2 lần
        onnx_path: str = None
    ):

        # Check pooling strategy
        if pooling not in ["auto", "cls", "mean", "none"]:
            raise ValueError(f"Pooling strategy '{pooling}' không hợp lệ. Chọn trong ['auto', 'cls', 'mean', 'none'].")

        self.model_dir = model_dir
        self.pooling = pooling
        self.max_length = max_length
        self.normalize = normalize

        try:
            if onnx_path:
                self.onnx_path = onnx_path
            else:
                opt_files = glob(f'{model_dir}/onnx/*opt.onnx')
                if opt_files:
                    self.onnx_path = opt_files[0]
                else:
                    self. onnx_path = glob(f'{model_dir}/onnx/*.onnx')[0]
        except IndexError as e:
            raise ValueError(f"Không tìm thấy file ONNX trong {model_dir}/onnx/") from e

        print(f"Using ONNX model: {self.onnx_path} with pooling={self.pooling}, max_length={self.max_length}, normalize={self.normalize}")

        if model_dir not in _TOKENIZER_CACHE:
            from transformers import AutoTokenizer
            _TOKENIZER_CACHE[model_dir] = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        
        self.tokenizer = _TOKENIZER_CACHE[model_dir]

        session_key = f'{self.onnx_path}_{max_length}'
        if session_key not in _ONNX_SESSION_CACHE:
            available_providers = set(ort.get_available_providers())
            use_cuda = shutil.which('nvidia-smi') and "CUDAExecutionProvider" in available_providers
            self.providers = ["CUDAExecutionProvider"] if use_cuda else ["CPUExecutionProvider"]

            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = os.cpu_count() // 2
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            # CUDA provider options example (tweak per GPU)
            cuda_opts = {"device_id": 0, "arena_extend_strategy": "kNextPowerOfTwo"}

            session = ort.InferenceSession(self.onnx_path, sess_options=options,
                                                providers=self.providers,
                                                provider_options=[cuda_opts] if "CUDAExecutionProvider" in self.providers else None)
            _ONNX_SESSION_CACHE[session_key] = session
        
        self.session = _ONNX_SESSION_CACHE[session_key]

        self.input_names = [inp.name for inp in self.session.get_inputs()]
        self.output_names = [out.name for out in self.session.get_outputs()]

    def _prepare_inputs(self, texts: List[str]):
        tokenized = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
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

        if "token_type_ids" in self.input_names and "token_type_ids" in tokenized:
            ort_inputs['token_type_ids'] = tokenized['token_type_ids'].astype(np.int64)

        return ort_inputs, tokenized

    def _pool_embeddings(self, output_dict: Dict[str, np.ndarray], attention_mask: np.ndarray) -> np.ndarray:
        # Nếu model đã có sentence_embedding sẵn và không yêu cầu pooling cụ thể thì dùng
        if "sentence_embedding" in output_dict and self.pooling in ["auto", "none"]:
            return output_dict["sentence_embedding"]

        # Lấy token-level embeddings
        if "last_hidden_state" in output_dict:
            token_embeddings = output_dict["last_hidden_state"]
        elif "token_embeddings" in output_dict:
            token_embeddings = output_dict["token_embeddings"]
        else:
            raise ValueError(f"Không tìm thấy output hợp lệ trong {list(output_dict.keys())}")

        if self.pooling == "none":
            raise ValueError("Model chỉ trả token embeddings nhưng pooling=none")

        if self.pooling == "cls":
            return token_embeddings[:, 0, :]

        if self.pooling == "mean":
            mask = attention_mask.astype(np.float32)
            summed = (token_embeddings * mask[..., None]).sum(axis=1)
            denom = mask.sum(axis=1, keepdims=True).clip(min=1e-9)
            return summed / denom

        # auto: default dùng CLS (nếu có)
        return token_embeddings[:, 0, :]

    def embed(self, requests: List[EmbeddingRequest], batch_size: int = 32) -> List[EmbeddingResult]:
        texts = [r.text for r in requests]
        results: List[EmbeddingResult] = []
        num_batches = (len(texts) + batch_size - 1) // batch_size

        with tqdm(total=num_batches, desc="Embedding batches", unit="batch", miniters=1, mininterval=0) as pbar:
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i: i + batch_size]
                ort_inputs, tokenized = self._prepare_inputs(batch_texts)

                outputs = self.session.run(self.output_names, ort_inputs)
                output_dict = dict(zip(self.output_names, outputs))

                emb = self._pool_embeddings(output_dict, tokenized['attention_mask'])

                if self.normalize:
                    norms = np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
                    emb = emb / norms
                
                emb = emb.astype(np.float32)

                for j in range(emb.shape[0]):
                    results.append(
                        EmbeddingResult(
                            chunk_id=requests[i + j].chunk_id,
                            text=requests[i + j].text,
                            vector=emb[j].astype(float).tolist(),
                            token_count=int(tokenized['attention_mask'][j].sum())
                        )
                    )
                
                pbar.update(1)

        return results