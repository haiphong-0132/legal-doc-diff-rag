# legal-doc-diff-rag
BT nhóm - Thực tập cơ sở - Nghiên cứu trợ lý so sánh văn bản pháp lý chạy cục bộ dùng RAG + Local LLM

## Prerequisites
- Python 3.13+
- uv

## Directory tree
Cấu trúc dự án dự kiến:
```
TTCS
│
├── .env                           
├── .env.example                    # Template .env
├── .gitignore
├── pyproject.toml                  # uv: khai báo dependencies, python version
├── README.md                       
├── structure.md                  
│
│
├── configs/                        # Toàn bộ cấu hình
│   │
│   ├── components/                 # Cấu hình từng component độc lập để tái sử dụng
│   │   ├── chunking/               # Các cấu hình phân đoạn
│   │   │   ├── fixed_size.yaml     # Chia theo số token cố định + overlap
│   │   │   ├── hierarchical.yaml   # Chia theo cấu trúc phân cấp Chương/Điều/Khoản
│   │   │   └── semantic.yaml       # Chia theo ngưỡng cosine similarity giữa câu...
│   │   │
│   │   ├── rag/                    # Chiến lược retrieval
│   │   │   ├── simple.yaml         # Vector search thuần (baseline)
│   │   │   ├── metadata_first.yaml # Ghép cặp theo số Điều trước, fallback semantic
│   │   │   ├── hybrid.yaml         # Kết hợp dense (vector) + sparse (BM25) + RRF
│   │   │   └── rerank.yaml         # Lấy top-20 rồi rerank bằng cross-encoder
│   │   │
│   │   └── llm/                    # Cấu hình từng LLM
│   │       └── qwen3_8b.yaml       # Qwen3-8B qua llama-cpp-python
│   │
│   └── experiments/                # Mỗi file = 1 lần chạy cụ thể
│       ├── exp_001.yaml            # structural + metadata_first + qwen3:8b
│       └── exp_002.yaml            # ...
│
│
├── data/                           # Dữ liệu đầu vào
│   └── pairs/                      # Các cặp tài liệu A/B để so sánh
│       ├── pair_001/
│       │   ├── version_a.docx
│       │   └── version_b.docx
│       └── samples/                # 10-20 cặp mẫu có chỉnh sửa biết trước (dùng để eval)
│
│
├── models/                         # File model
│   └── .gitkeep
│
│
├── results/                        # Output của từng thử nghiệm
│   ├── exp_001/
│   │   ├── config_snapshot.yaml    # Bản sao config tại thời điểm chạy để reproducibility
│   │   ├── metrics.json            # Precision, recall, faithfulness, latency,...
│   │   └── report.md               # Báo cáo so sánh dạng markdown
│   └── exp_002/
│
│
├── docs/
│   └── setup.md                    # Hướng dẫn cài đặt
│
│
├── notebooks/                      # Thử nghiệm trên ipynb tùy ý
│   ├── ...ipynb
│
│
├── src/                            # Toàn bộ source code
│   ├── __init__.py
│   ├── schemas.py                  # Pydantic models dùng chung toàn project:
│   │                               #   ChunkDocument, MatchedPair,
│   │                               #   ComparisonResult, Report
│   │
│   ├── core/                       # Logic code không phụ thuộc framework
│   │   ├── reader.py               # Đọc file: DOCX (python-docx) + PDF (PyMuPDF)
│   │   ├── normalizer.py           # Chuẩn hóa văn bản
│   │   ├── embedding.py            # Load model embedding
│   │   ├── vectorstore.py          # ChromaDB wrapper
│   │   ├── retrieval.py            # Điều phối retrieval: nhận RAGStrategy,
│   │   │                           # gọi vectorstore, trả list[MatchedPair]
│   │   ├── matcher.py              # Ghép cặp chunk_A ↔ chunk_B:
│   │   │                           #   metadata match (số Điều) → semantic fallback
│   │   │                           #   chunk không có cặp → ADDED / DELETED
│   │   ├── comparator.py           # Gọi LLM so sánh từng MatchedPair → ComparisonResult
│   │   ├── reporter.py             # Gom list[ComparisonResult] → Report
│   │   │                           # Xuất: Markdown / JSON
│   │   │
│   │   ├── chunker/
│   │   │   ├── base.py             # Abstract class ChunkingStrategy: chunk(text) → list[ChunkDocument]
│   │   │   ├── fixed_size.py       # Implement: chia token cố định + overlap
│   │   │   ├── hierarchical.py     # Implement: nhận diện Chương/Điều/Khoản bằng
│   │   │   │                       #   heading style (DOCX) hoặc regex (PDF)
│   │   │   ├── semantic.py         # Implement: cắt khi cosine similarity giảm đột ngột
│   │   │   └── factory.py          # ChunkerFactory.create(config)
│   │   │
│   │   └── llm/
│   │       ├── base.py             # Abstract class LLMBackend: invoke(prompt) / stream(prompt)
│   │       ├── llamacpp.py         # gọi llama-cpp-python trực tiếp
│   │       └── factory.py          # LLMFactory.create(config)
│   │
│   │
│   ├── rag/                        # Các chiến lược RAG - RAGStrategy
│   │   ├── base.py                 # Abstract class RAGStrategy: retrieve(query, vectorstore)
│   │   ├── simple.py               # Vector search thuần, top-k theo cosine similarity
│   │   ├── metadata_first.py       # Ghép theo số Điều trước → semantic fallback
│   │   ├── hybrid.py               # Dense + BM25 → Reciprocal Rank Fusion
│   │   ├── rerank.py               # Vector search top-20 → cross-encoder rerank → top-5
│   │   └── factory.py              # RAGFactory.create(config) → đúng strategy
│   │
│   │
│   ├── experiment/                 # Quản lý experiment
│   │   ├── config_loader.py        # Load experiment.yaml → merge component configs
│   │   │                           # → validate → ExperimentConfig object
│   │   ├── factory.py              # build_pipeline(config):
│   │   │                           #   ChunkerFactory + RAGFactory + LLMFactory
│   │   │                           #   → Runner hoàn chỉnh, sẵn sàng chạy
│   │   └── tracker.py              # Lưu kết quả: copy config snapshot,
│   │                               # ghi metrics.json, report.md vào results/exp_xxx/
│   │
│   │
│   ├── pipeline/
│   │   └── runner.py               # Điều phối pipeline tuyến tính:
│   │                               #   ingest → chunk → index → retrieve
│   │                               #   → compare → verify → report
│   │                               # Nhận chunker, rag_strategy, llm làm tham số
│   │
│   │
│   ├── evaluation/
│   │   ├── dataset.py              # Load data/pairs/samples/, đọc ground truth
│   │   │                           # (danh sách thay đổi biết trước)
│   │   ├── metrics.py              # Tính: precision/recall (phát hiện thay đổi),
│   │   │                           # faithfulness (trích dẫn đúng), latency
│   │   └── runner.py               # Chạy eval trên toàn bộ samples,
│   │                               # so sánh nhiều experiments, xuất bảng kết quả
│   │
│   │
│   └── prompts/                    # Prompt templates — tách khỏi code, dễ chỉnh
│       ├── system.txt              # System prompt: vai trò, nguyên tắc "không bằng chứng → không kết luận"
│       ├── compare.txt             # So sánh 1 cặp điều khoản → JSON output
│       └── summarize.txt           # Tổng hợp toàn bộ thay đổi thành báo cáo ngắn
│
│
├── cli/                            # Giao diện dòng lệnh
│   ├── run_experiment.py           # python cli/run_experiment.py --config exp_001.yaml
│   ├── compare_experiments.py      # python cli/compare_experiments.py --exps exp_001 exp_002
│   └── run_ui.py                   # python cli/run_ui.py → chạy UI
│
│
└── ui/
    └── app.py                      # Streamlit UI/ MERN stack UI/ Static web
```


## Docs
[Setup guide](docs/setup.md)