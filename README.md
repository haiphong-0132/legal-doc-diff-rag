# Legal Doc Diff RAG

> **Hệ thống so sánh văn bản pháp luật Việt Nam tự động** — Phát hiện, phân loại và phân tích tác động thay đổi giữa hai phiên bản văn bản pháp lý sử dụng RAG (Retrieval-Augmented Generation) kết hợp LLM.

Bài tập nhóm — Thực tập cơ sở — PTIT

---

## Mục lục

- [Tính năng chính](#tính-năng-chính)
- [Pipeline hệ thống](#pipeline-hệ-thống)
- [Tech Stack](#tech-stack)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt](#cài-đặt)
- [Cấu hình Environment Variables](#cấu-hình-environment-variables)
- [Chạy Development](#chạy-development)
- [Chạy Pipeline qua CLI](#chạy-pipeline-qua-cli)
- [API Reference](#api-reference)
- [Architecture Overview](#architecture-overview)
- [Deployment Guide](#deployment-guide)
- [Troubleshooting](#troubleshooting)

---

## Tính năng chính

- **Trích xuất văn bản**: Hỗ trợ đầu vào `.docx` (Pandoc) và `.pdf` (any2md → Pandoc), tự động làm sạch HTML entities, chuẩn hóa dấu câu tiếng Việt.
- **Phân tích cú pháp phân cấp**: Dựng cây JSON cấu trúc pháp luật Việt Nam (`Điều → Khoản → Điểm`) bằng regex, kèm bóc tách tham chiếu chéo thông minh (xử lý được "Điều này").
- **So khớp 4 Phase**:
  - **Phase 0** — So khớp text thô tuyệt đối (hash-based, instant).
  - **Phase 1** — Embedding ngữ nghĩa + Greedy Rerank + Hungarian Hybrid Matching toàn cục.
  - **Phase 2** — Progressive Zoom-In xuống Khoản/Điểm + Unified LLM Review.
  - **Phase 3** — Kết xuất báo cáo Markdown
- **Đa chế độ LLM**: Hỗ trợ `remote` (LLM tự host)
- **Web UI**: React + Vite + TailwindCSS v4, gồm Upload → Progress tracking → Kết quả phân tích + Chat hỏi đáp về báo cáo.
- **Session Persistence**: Trạng thái UI được lưu vào `sessionStorage`, reload trang không mất dữ liệu.

---

## Pipeline hệ thống

<img src="docs/images/PipelineTTCS.png" alt="Pipeline hệ thống so sánh văn bản pháp lý" width="800"/>

---

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| **Ngôn ngữ** | Python 3.13+, JavaScript (ES Module) |
| **Backend** | FastAPI, Uvicorn |
| **Frontend** | React 19, Vite 8, TailwindCSS v4 |
| **Embedding** | SentenceTransformer (`Vietnamese_Embedding_v2`), hỗ trợ ONNX Runtime GPU |
| **Reranker** | FlagEmbedding (`Vietnamese_Reranker`) |
| **Vector DB** | ChromaDB (Ephemeral / Persistent) |
| **LLM** | LLM (remote) |
| **Matching** | Hungarian Algorithm (`scipy.optimize.linear_sum_assignment`), Hybrid Scoring (Cosine + Jaccard + Positional Bias + Title Fuzzy) |
| **Document Parsing** | Pandoc (`pypandoc`), `any2md`, `python-docx` |
| **PDF Export** | WeasyPrint (ưu tiên), fallback `xhtml2pdf` |
| **Package Manager** | `uv` (Python), `npm` (Frontend) |

---

## Cấu trúc thư mục

```
TTCS/
├── .env                          # Biến môi trường (git-ignored)
├── .env.example                  # Template biến môi trường
├── pyproject.toml                # uv: dependencies, Python version
├── requirements.txt              # pip: pinned dependencies (CUDA 13.0)
├── main.py                       # Entry point placeholder
│
├── configs/
│   └── config.yaml               # Cấu hình trung tâm (paths, thresholds, LLM, embedding, web)
│
├── src/                          # Source code chính
│   ├── config.py                 # Load .env + config.yaml → hằng số toàn cục
│   ├── schemas.py                # Pydantic/Dataclass models dùng chung
│   │
│   ├── core/
│   │   ├── ingestion/            # Trích xuất & làm sạch văn bản
│   │   │   ├── extractor.py      # Dispatcher: detect .docx/.pdf → gọi extractor tương ứng
│   │   │   ├── docx_extractor.py # DOCX → Pandoc HTML → plain text
│   │   │   ├── pdf_extractor.py  # PDF → any2md → Markdown → Pandoc HTML → plain text
│   │   │   └── text_cleaner.py   # Loại bỏ HTML tags, chuẩn hóa Unicode/dấu câu tiếng Việt
│   │   │
│   │   ├── chunker/              # Phân tích cú pháp & chunking
│   │   │   ├── legal_parser.py   # build_json_tree: Regex → cây JSON (Điều/Khoản/Điểm)
│   │   │   ├── hierarchical.py   # HierarchicalChunker + build_node_registry (O(N) bottom-up)
│   │   │   ├── fixed_size.py     # Chunker theo token cố định + overlap
│   │   │   └── factory.py        # ChunkerFactory
│   │   │
│   │   ├── embedding/            # Module nhúng vector
│   │   │   ├── __init__.py       # decode_section_id utility
│   │   │   ├── embedding.py      # EmbeddingPipeline: chunk → EmbeddingRequest
│   │   │   ├── embedding_model.py  # SentenceTransformer wrapper (CPU/GPU auto)
│   │   │   └── onnx_embedding.py # ONNX Runtime embedding (legacy)
│   │   │
│   │   ├── vector_store/         # Lưu trữ vector
│   │   │   ├── chroma_store.py   # ChromaDB wrapper (upsert, query, batch)
│   │   │   └── vectorstore.py    # VectorStorePipeline: EmbeddingResult → ChromaDB
│   │   │
│   │   ├── retrieval/            # Truy vấn & rerank
│   │   │   └── retrieval.py      # RetrievalService: embed → query → rerank
│   │   │
│   │   ├── matching/             # So khớp & phân tích LLM
│   │   │   ├── matcher.py        # build_global_matches (Pass 1 Greedy + Pass 2 Hungarian)
│   │   │   │                     # match_sub_nodes (On-The-Fly embedding cho Khoản/Điểm)
│   │   │   ├── scoring.py        # calculate_hybrid_score, Jaccard, title similarity
│   │   │   ├── llm_review.py     # call_local_llm (remote), llm_review_pair/single/khoan_with_diem
│   │   │   ├── llm_prompts.py    # System/User prompt templates cho LLM
│   │   │   ├── chunk_formatter.py  # format_chunk cho LLM và exact match
│   │   │   └── reporting.py      # render_change_report → Markdown báo cáo
│   │   │
│   │   └── api/                  # Client gọi API external
│   │       └── call_api.py       # call_embed_api, call_rerank_api, call_generate_api
│   │
│   └── pipeline/
│       └── runner.py             # run_pipeline: điều phối 4 Phase đầu-cuối + CLI
│
├── web/                          # Web application
│   ├── app.py                    # FastAPI backend (REST API)
│   ├── chat.py                   # Chat hỏi đáp về báo cáo qua LLM
│   └── frontend/                 # React SPA
│       ├── package.json          # React 19 + Vite 8 + TailwindCSS v4
│       ├── vite.config.js        # Dev proxy → backend :8001
│       └── src/
│           ├── App.jsx           # Router: Upload → Progress → Results
│           ├── api.js            # API client (fetch)
│           └── components/
│               ├── UploadPage.jsx     # Upload 2 file .docx/.pdf
│               ├── ProgressView.jsx   # Theo dõi tiến trình pipeline
│               ├── ResultsPage.jsx    # Hiển thị kết quả phân tích
│               ├── StatsCards.jsx     # Thẻ thống kê tổng quan
│               ├── ChangeList.jsx     # Danh sách thay đổi chi tiết
│               ├── SideBySideView.jsx # Xem song song 2 văn bản
│               └── ChatPanel.jsx      # Chat hỏi đáp về kết quả
│
├── models/                       # Trọng số mô hình (git-ignored)
│   ├── Vietnamese_Embedding_v2/  # SentenceTransformer embedding model
│   └── Vietnamese_Reranker/      # FlagEmbedding reranker model (tùy chọn)
│
├── data/                         # Dữ liệu ChromaDB (git-ignored)
├── docs/
│   ├── setup.md                  # Hướng dẫn cài đặt chi tiết
│   └── images/
│       └── PipelineTTCS.png      # Sơ đồ pipeline
│
├── notebooks/                    # Jupyter notebooks thử nghiệm
└── system_pipeline_walkthrough.md  # Tài liệu kiến trúc chi tiết
```

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.13+ |
| Node.js | 20+ |
| RAM | 8GB+ |
| GPU | NVIDIA GPU với CUDA 13.0 (khuyến nghị, không bắt buộc — chạy được trên CPU) |
| Pandoc | Cài đặt hệ thống (`pandoc`) |
| Hệ điều hành | Windows / Linux |

---

## Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/<your-org>/legal-doc-diff-rag.git
cd legal-doc-diff-rag
```

### 2. Cài thư viện hệ thống

**Linux:**
```bash
sudo apt update && sudo apt install -y pandoc libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

**Windows:**
- Cài [Pandoc](https://pandoc.org/installing.html) và thêm vào PATH.

### 3. Cài Python dependencies

**Dùng `uv` (khuyến nghị):**
```bash
uv sync
```

**Hoặc dùng `pip`:**
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux:
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Cài Frontend dependencies

```bash
cd web/frontend
npm install
cd ../..
```

### 5. Tải mô hình AI

Đặt các mô hình vào thư mục `models/`:

| Mô hình | Đường dẫn | Mô tả |
|---|---|---|
| Vietnamese Embedding v2 | `models/Vietnamese_Embedding_v2/` | SentenceTransformer embedding cho tiếng Việt |
| Vietnamese Reranker | `models/Vietnamese_Reranker/` | Cross-encoder reranker (tùy chọn, có DummyReranker fallback) |

### 6. Cấu hình môi trường

**Linux / macOS:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

Sau đó chỉnh sửa file `.env` theo hướng dẫn bên dưới.

---

## Cấu hình Environment Variables

File `.env` (hoặc ghi đè qua biến môi trường hệ thống):

```env
## ENDPOINT — Chạy gộp 1 máy chủ:
API_BASE_URL=http://localhost:8080

## Hoặc tách riêng từng server:
# EMBED_API_URL=http://localhost:8000
# RERANK_API_URL=http://localhost:8001
# LLM_API_URL=http://localhost:8002

## CHẾ ĐỘ LLM
# "remote" — Gọi qua LLM tự host (mặc định)
LLM_MODE=remote
```

Tất cả cấu hình còn có thể đặt trong `configs/config.yaml` với các nhóm: `paths`, `pipeline_thresholds`, `llm`, `embedding`, `web`. Biến `.env` sẽ **ghi đè** giá trị trong YAML.

**Các threshold quan trọng** (trong `config.yaml` hoặc `.env`):

| Biến | Mặc định | Mô tả |
|---|---|---|
| `TOP_K` | `8` | Số ứng viên tối đa lấy từ ChromaDB |
| `DISTANCE_THRESHOLD` | `0.185` | Ngưỡng khoảng cách tối đa (Greedy Match) |
| `RERANK_THRESHOLD` | `0.985` | Ngưỡng reranker khớp nhanh |
| `HYBRID_THRESHOLD` | `0.75` | Ngưỡng Hungarian Hybrid tối thiểu |

---

## Chạy Development

Cần **3 terminal** chạy song song:

### Terminal 1 — LLM Server

Chạy LLM phía hosting — bất kỳ server nào expose `/embed`, `/rerank`, `/generate` endpoints.

### Terminal 2 — Backend (FastAPI)

**Linux / macOS:**
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8001 --reload --reload-dir src --reload-exclude "web/frontend/*"
```

**Windows (PowerShell):**
```powershell
uvicorn web.app:app --host 0.0.0.0 --port 8001 --reload --reload-dir src --reload-exclude "web/frontend/*"
```

### Terminal 3 — Frontend (Vite)

**Linux / macOS:**
```bash
cd web/frontend
npm run dev
```

**Windows (PowerShell):**
```powershell
cd web\frontend
npm run dev
```

Mở trình duyệt tại `http://localhost:5173`.

> **Lưu ý**: Vite proxy tự động chuyển tiếp `/api/*` tới backend tại `http://127.0.0.1:8001` (cấu hình trong `vite.config.js`).

---

## Chạy Pipeline qua CLI

```bash
python -m src.pipeline.runner --vb1 path/to/old.docx --vb2 path/to/new.docx
```

Nếu không truyền tham số, pipeline sẽ đọc đường dẫn mặc định từ `config.yaml` (`vb1.docx`, `vb2.docx`).

---

## API Reference

Backend chạy tại `http://localhost:8001`. Swagger UI: `http://localhost:8001/docs`.

### `POST /api/compare`

Upload 2 file để bắt đầu so sánh. Trả về `job_id` ngay lập tức, pipeline chạy nền (async thread).

```
Content-Type: multipart/form-data
Fields: vb1 (file), vb2 (file)
Accepted: .docx, .pdf (tối đa 20MB)
```

**Response:**
```json
{ "job_id": "a1b2c3d4e5f6" }
```

### `GET /api/jobs/{job_id}/status`

Theo dõi tiến trình pipeline.

**Response:**
```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "running",       // "pending" | "running" | "done" | "error"
  "phase": "phase_2",        // "loading" | "phase_0" | "phase_1" | "phase_2" | "done"
  "message": "Phase 2: LLM phân tích các cặp thay đổi...",
  "error": ""
}
```

### `GET /api/jobs/{job_id}/results`

Lấy kết quả phân tích (chỉ khi `status=done`).

**Response chứa:**
- `stats` — Thống kê: số chunk VB1/VB2, giống hoàn toàn, giống ngữ nghĩa, sửa đổi, thêm mới, xóa bỏ.
- `matched_pairs` — Danh sách các cặp chunk đã ghép.
- `changes` — Thay đổi phân nhóm (`sua_doi`, `them_moi`, `xoa_bo`, `giong_nhau_ngu_nghia`).
- `report_text` — Báo cáo Markdown đầy đủ.

### `GET /api/jobs/{job_id}/pdf/{doc}`

Trả file dưới dạng PDF (`doc` = `vb1` hoặc `vb2`). Tự động convert DOCX → PDF.

### `GET /api/jobs/{job_id}/view/{doc}`

Trả file dưới dạng HTML để nhúng iframe.

### `GET /api/jobs/{job_id}/file/{doc}`

Tải file gốc.

### `POST /api/jobs/{job_id}/chat`

Chat hỏi đáp về kết quả phân tích.

```json
{ "question": "Điều nào có thay đổi lớn nhất?" }
```

**Response:**
```json
{ "answer": "Điều 5 có thay đổi lớn nhất với việc..." }
```

---

## Architecture Overview

```mermaid
graph TD
    subgraph Frontend["Web Frontend — React + Vite"]
        UP["UploadPage"]
        PV["ProgressView"]
        RP["ResultsPage + ChatPanel"]
        UP -->|upload 2 files| PV
        PV -->|pipeline done| RP
    end

    subgraph Backend["FastAPI Backend — web/app.py"]
        COMPARE["POST /api/compare"]
        STATUS["GET /api/jobs/status"]
        RESULTS["GET /api/results, /pdf, /view, /chat"]
    end

    subgraph Pipeline["Pipeline Runner — src/pipeline/runner.py"]
        P0["Phase 0: Exact Match"]
        P1["Phase 1: Embedding → ChromaDB → Greedy Rerank → Hungarian"]
        P2["Phase 2: Zoom-In Khoản/Điểm → Text Diff → LLM Review"]
        P3["Phase 3: render_change_report → Markdown"]
        P0 -->|remaining chunks| P1
        P1 -->|matched pairs| P2
        P2 -->|change items| P3
    end

    subgraph Services["External Services"]
        EMB["Embedding Model\n(local hoặc API)"]
        CHROMA["ChromaDB\n(Ephemeral)"]
        LLM["LLM Server\n(remote)"]
    end

    Frontend -->|/api/*| Backend
    COMPARE -->|spawn Thread| P0
    P1 --- EMB
    P1 --- CHROMA
    P2 --- LLM
    P3 -->|PipelineResult| RESULTS
```

### Luồng xử lý chi tiết

1. **Ingestion**: `extract_file()` → detect `.docx`/`.pdf` → Pandoc HTML → `extract_text_from_html()` → plain text.
2. **Parsing**: `build_json_tree()` → cây JSON phân cấp (Điều/Khoản/Điểm) với tham chiếu chéo.
3. **Registry**: `build_node_registry()` — duyệt hậu thứ tự O(N), cache `cached_merged_text` và `cached_keywords` cho mỗi node.
4. **Chunking**: `HierarchicalChunker(chunk_by="dieu")` — trích xuất chunk cấp Điều (fallback xuống Khoản/Điểm nếu vượt `max_tokens`).
5. **Phase 0**: So sánh chuỗi text thô → loại bỏ các Điều giống 100%.
6. **Phase 1**: Embedding → ChromaDB index → Pass 1 (Greedy top-K + Rerank) → Pass 2 (Hungarian Hybrid Matrix).
7. **Phase 2**: Zoom-In phân cấp → On-The-Fly Embedding cho Khoản/Điểm → so sánh text chuẩn hóa → LLM Review gộp.
8. **Reporting**: Gom `ChangeItem` → `render_change_report()` → Markdown.

> 📖 Xem chi tiết tại [system_pipeline_walkthrough.md](system_pipeline_walkthrough.md)

---

## Deployment Guide

### Deploy trên server (GPU)

**Linux:**
```bash
# 1. Cài đặt theo phần "Cài đặt" ở trên

# 2. Chạy LLM server phía hosting

# 3. Chạy backend
uvicorn web.app:app --host 0.0.0.0 --port 8001 &

# 4. Build frontend production
cd web/frontend
npm run build
# Serve static files bằng nginx hoặc tương tự
```

**Windows (PowerShell):**
```powershell
# 1. Cài đặt theo phần "Cài đặt" ở trên

# 2. Chạy LLM server phía hosting

# 3. Chạy backend
Start-Process uvicorn -ArgumentList "web.app:app", "--host", "0.0.0.0", "--port", "8001"

# 4. Build frontend production
cd web\frontend
npm run build
```

### Expose qua Cloudflare Tunnel

Backend và Frontend đã hỗ trợ sẵn CORS cho domain `*.trycloudflare.com`. Cập nhật:
- `web/app.py` → `allow_origins` — thêm domain tunnel.
- `web/frontend/vite.config.js` → `allowedHosts` — thêm domain tunnel FE.

### Tách riêng máy chủ AI

Cấu hình `.env` để trỏ Embedding, Reranker, LLM đến các máy chủ khác nhau:

```env
EMBED_API_URL=http://gpu-server-1:8000
RERANK_API_URL=http://gpu-server-1:8001
LLM_API_URL=http://gpu-server-2:11434
```

API external cần expose 3 endpoint: `POST /embed`, `POST /rerank`, `POST /generate`.

---

## Troubleshooting

### Lỗi Pandoc không tìm thấy

```
OSError: No pandoc was found
```

**Giải pháp**: Cài Pandoc hệ thống — `sudo apt install pandoc` (Linux) hoặc tải từ [pandoc.org](https://pandoc.org/installing.html) (Windows).

### Lỗi WeasyPrint khi convert PDF

```
Weasyprint conversion failed or library not found
```

**Giải pháp**: Hệ thống sẽ tự động fallback sang `xhtml2pdf`. Nếu muốn dùng WeasyPrint:

- **Linux:** `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`
- **Windows:** Cài [GTK3 Runtime](https://github.com/nickvdyck/weasyprint-win/releases) hoặc sử dụng fallback `xhtml2pdf` (không cần cài thêm gì).

### Reranker model không tìm thấy

```
RERANKER WARNING: Local reranker weights not found... Falling back to DummyReranker
```

**Giải pháp**: Tải model reranker vào `models/Vietnamese_Reranker/` hoặc sử dụng API reranker thay thế. `DummyReranker` (scores = 1.0) sẽ được dùng tạm nếu không có model local.

### Lỗi kết nối API

```
API Check failed / Cannot call API
```

**Giải pháp**: Pipeline tự động phát hiện API có sẵn hay không. Nếu API không trả lời, hệ thống chuyển sang dùng model local. Kiểm tra `API_BASE_URL` trong `.env` và đảm bảo server AI đang chạy.

### Frontend không kết nối được backend

**Giải pháp**: Kiểm tra port trong `vite.config.js` → `proxy.target` khớp với port backend đang chạy (mặc định `8001`).


## Tài liệu bổ sung

- [System Pipeline Walkthrough](docs/system_pipeline_walkthrough.md) — Tài liệu kiến trúc & luồng xử lý 4 Phase
