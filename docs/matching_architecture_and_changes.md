# Hệ thống So sánh Văn bản Pháp luật — Kiến trúc & Tổng hợp Thay đổi

> Tài liệu mô tả kiến trúc hiện tại của pipeline so sánh hai phiên bản văn bản pháp luật (VB1 cũ ↔ VB2 mới), cùng toàn bộ các fix/cải tiến đã thực hiện và kết quả kiểm thử.

---

## 1. Tổng quan

Hệ thống nhận **hai phiên bản** của một văn bản (hợp đồng, nghị định...) và tự động phát hiện, phân loại các thay đổi:

| Nhóm | Ý nghĩa |
|------|---------|
| `giong_nhau_hoan_toan` | Giống hệt (kể cả chỉ khác cách đánh số / paraphrase mà LLM coi là không đổi nghĩa) |
| `sua_doi` | Sửa đổi nội dung (đổi quyền/nghĩa vụ/số liệu...) |
| `them_moi` | Thêm mới ở VB2 |
| `xoa_bo` | Xóa khỏi VB1 |

**Kết quả** đi qua FastAPI → React frontend (tabs + side-by-side PDF + chat).

### Công nghệ
- **Embedding**: ONNX `Vietnamese_Embedding_v2` (local) hoặc API (`localhost:8001`)
- **Reranker**: `Vietnamese_Reranker` (local) hoặc API
- **Vector store**: ChromaDB (in-memory, tạo mới mỗi lần chạy)
- **LLM**: qwen3-next-80b (NVIDIA API) hoặc remote/Ollama — phân tích & tóm tắt thay đổi
- **Matching**: Greedy (vector+rerank) + Hungarian (scipy `linear_sum_assignment`)

---

## 2. Kiến trúc Pipeline (5 Phase)

```mermaid
flowchart TD
    A[VB1.docx + VB2.docx] --> B["extract_file<br/>pandoc + fallback render numbering Word<br/>→ build_json_tree"]
    B --> C[HierarchicalChunker<br/>chunk_by=dieu, max_tokens=2000]
    C --> D[(Chunks VB1 + registry)]
    C --> E[(Chunks VB2 + registry)]

    D & E --> P0

    subgraph P0 [Phase 0 — Exact Match]
        F[So khớp text thô<br/>chuẩn hóa khoảng trắng]
        F --> G[method=raw_exact]
    end

    P0 --> P1

    subgraph P1 [Phase 1 — Embedding + Hungarian]
        H[Embed các chunk còn lại] --> I[Pass 1: Greedy<br/>vector query + rerank]
        I --> J[Pass 2: Hungarian<br/>hybrid score]
        J --> K[high_confidence_greedy<br/>hungarian_hybrid]
    end

    P1 --> P2

    subgraph P2 [Phase 2 — Progressive Zoom + LLM]
        L[Duyệt cặp đã khớp] --> M{node_loai?}
        M -->|dieu có khoản| N[match_sub_nodes khoản]
        M -->|khoan có điểm| O[match_sub_nodes điểm]
        M -->|lá| Q[llm_review_pair]
        N & O --> R[Zoom xuống cấp con]
        R --> Q
        Q --> S{identical?}
        S -->|true| T[type: exact/danh_so/paraphrase]
        S -->|false| U[ChangeItem sua_doi]
    end

    P2 --> P3

    subgraph P3 [Propagation + Phân loại]
        V[Lan truyền thay đổi lên cha] --> W[Đếm + reclassify type]
    end

    P3 --> X[PipelineResult<br/>stats + change_items + report]
    X --> Y[FastAPI /api/jobs/id/results]
    Y --> Z[React UI]
```

### Ngưỡng cấu hình ([configs/config.yaml](../configs/config.yaml))

| Tham số | Giá trị | Vai trò |
|---------|---------|---------|
| `max_tokens` | **2000** | Giới hạn token mỗi chunk (sát giới hạn embedding 2048) |
| `chunk_by` | `dieu` | Cấp chunk gốc |
| `distance_threshold` | 0.185 | Ngưỡng vector cho Greedy |
| `rerank_threshold` | 0.98 | Ngưỡng rerank cho Greedy |
| `hybrid_threshold` | 0.65 | Ngưỡng Hungarian chấp nhận khớp |

---

## 3. Module `src/core/matching`

```mermaid
flowchart LR
    subgraph matching
        sc[scoring.py<br/>hybrid score 4 chiều]
        cf[chunk_formatter.py<br/>format cho LLM]
        mt[matcher.py<br/>greedy + hungarian + sub_nodes]
        pr[llm_prompts.py<br/>4 cặp prompt]
        rv[llm_review.py<br/>gọi LLM + parse + safeguard]
        rp[reporting.py<br/>render markdown]
    end
    mt --> sc
    rv --> cf
    rv --> pr
    runner[pipeline/runner.py] --> mt
    runner --> rv
    runner --> rp
```

### 3.1. `scoring.py` — Hybrid Score

```
score = 0.35·s_embed + 0.15·s_title + 0.20·s_pos + 0.30·s_lex
        (nếu thiếu title: 0.50·s_embed + 0.20·s_pos + 0.30·s_lex)
```
- `s_embed`: cosine similarity vector
- `s_title`: fuzzy token-sort tên tiêu đề
- `s_pos`: tương đồng vị trí trong văn bản
- `s_lex`: Jaccard từ khóa (số, ngày, tên riêng)

### 3.2. `matcher.py`

```mermaid
flowchart TD
    A[build_global_matches] --> B{vector_store?}
    B -->|có| C[Pass 1 Greedy<br/>song song query+rerank]
    B --> D[Pass 2 Hungarian<br/>cost = -hybrid_score]
    C --> D
    D --> E[Lọc theo hybrid_threshold]

    F[match_sub_nodes] --> G[Embed on-the-fly]
    G --> H[build_global_matches<br/>vector_store=None]
    H --> I[matched + unmatched]
    I --> J{leftover cả 2 phía?}
    J -->|có| K["Fix B: ghép leftover<br/>threshold=0 → để LLM phán"]
    J -->|không| L[trả về]
    K --> L
```

### 3.3. `llm_review.py` — luồng `llm_review_pair`

```mermaid
flowchart TD
    A[llm_review_pair] --> B[Chuẩn hóa text<br/>collapse ws + lowercase]
    B --> C{text trùng khớp<br/>chính xác?}
    C -->|có| D[return None, type=exact<br/>SKIP LLM]
    C -->|không| E[format_chunk for_llm<br/>gửi NỘI DUNG đầy đủ]
    E --> F[Gọi LLM]
    F --> G[parse_json_response<br/>3 fallback]
    G --> H{identical?}
    H -->|true| I[lấy type:<br/>exact/danh_so/paraphrase]
    H -->|false| J[Lọc hallucination old==new]
    J --> K[ChangeItem sua_doi<br/>changes + summary]
```

### 3.4. Bốn cặp prompt ([llm_prompts.py](../src/core/matching/llm_prompts.py))
- `PAIR_REVIEW_*`: so sánh cặp đã khớp → `identical` + `type` + `changes`
- `SINGLE_REVIEW_*`: tóm tắt chunk thêm/xóa đơn lẻ
- `KHOAN_WITH_DIEM_*`: phân tích Khoản kèm các Điểm con

---

## 4. Phân loại thay đổi (Taxonomy)

```mermaid
flowchart TD
    A[Cặp chunk] --> B{Phase 0:<br/>text trùng khớp?}
    B -->|có| C[raw_exact]
    B -->|không| D[Matched Phase 1]
    D --> E[llm_review_pair]
    E --> F{identical?}
    F -->|true bất kể type:<br/>exact/danh_so/paraphrase| G[return None → coi như giống]
    F -->|false| I[ChangeItem sua_doi]
    C --> J[giong_nhau_hoan_toan]
    G --> J
    I --> L[sua_doi]
    M[Chunk không khớp VB2] --> N[them_moi]
    O[Chunk không khớp VB1] --> P[xoa_bo]
```

> **Thống nhất 3 nơi**: cả `runner.py` (report + stats) và `web/app.py` (UI) đều dùng `{llm_semantic_identical}` cho `giong_nhau_ngu_nghia` (trước đây lệch nhau).

---

## 5. Tổng hợp các Fix & Cải tiến (phiên này)

```mermaid
timeline
    title Hành trình fix
    Đơn giản hóa LLM review : Bỏ Jaccard safeguard, sentence diff : Để LLM tự quyết identical
    Thống nhất prompt : Chuyển prompt inline vào llm_prompts.py
    Thống nhất phân loại : 3 nơi cùng dùng llm_semantic_identical
    Trường type : exact / danh_so / paraphrase do LLM phân định
    Fix chunking VB4 : max_tokens 512 → 2000 (chống lệch cấp)
    Fix bug dư-1 : Sửa thụt lề tasks.append
    Fix format_chunk VB5 : Gửi noi_dung thay vì chỉ tiêu đề
    Fix B paraphrase VB1 : Ghép leftover + so cặp điểm bằng nội dung
    Tinh chỉnh prompt VB10 : Chú ý số liệu + paraphrase
    Fix extractor VB3 : Render numbering Word từ numbering.xml
    Surface paraphrase : Paraphrase → tab Giống ngữ nghĩa
    Bôi đậm thay đổi : LLM bọc **...** + frontend render bold
```

### 5.1. Bảng tổng hợp

| # | Fix | File | Vấn đề giải quyết |
|---|-----|------|-------------------|
| 1 | Đơn giản hóa `llm_review_pair` | [llm_review.py](../src/core/matching/llm_review.py) | Bỏ `get_critical_tokens`, `check_lexical_safeguard_jaccard`, `split_into_sentences_or_bullets`; để LLM quyết `identical` |
| 2 | Gom prompt | [llm_prompts.py](../src/core/matching/llm_prompts.py) | Prompt inline của `khoan_with_diem` chuyển vào file prompt |
| 3 | Thống nhất `giong_nhau_ngu_nghia` | [runner.py](../src/pipeline/runner.py), [web/app.py](../web/app.py) | 3 định nghĩa lệch nhau → cùng `{llm_semantic_identical}` |
| 4 | Trường `type` | [llm_prompts.py](../src/core/matching/llm_prompts.py), [llm_review.py](../src/core/matching/llm_review.py), [runner.py](../src/pipeline/runner.py) | LLM phân định exact / danh_so / paraphrase → tách "chỉ khác đánh số" khỏi paraphrase |
| 5 | **Chunking max_tokens 512→2000** | [config.yaml](../configs/config.yaml) | Cùng một Điều bị tách khoản ở bản này, giữ nguyên ở bản kia → matcher lệch cấp |
| 6 | **Fix bug "dư-1"** | [runner.py](../src/pipeline/runner.py) | `tasks.append` nằm NGOÀI vòng `for` → `chunk_d1` rò rỉ giữa các vòng → xóa_bo ma |
| 7 | **Fix `format_chunk`** | [chunk_formatter.py](../src/core/matching/chunk_formatter.py) | `for_llm=True` chỉ gửi `tieu_de` (tiêu đề) → mất thân → LLM tưởng giống nhau |
| 8 | **Fix B — paraphrase recall** | [matcher.py](../src/core/matching/matcher.py), [runner.py](../src/pipeline/runner.py) | Cặp điểm paraphrase bị ngưỡng loại → tách thành xóa+thêm |
| 9 | Tinh chỉnh prompt | [llm_prompts.py](../src/core/matching/llm_prompts.py) | Chú ý thay đổi nhỏ (phủ định/số/tình thái) + trích số liệu chính xác |
| 10 | **Fix extractor — render numbering Word** | [docx_extractor.py](../src/core/ingestion/docx_extractor.py) | Văn bản dùng numbered-list tự động của Word → pandoc làm mất số "Điều N" → parser không tách được Điều |
| 11 | ~~Surface paraphrase → ngu_nghia~~ **(ĐÃ GỠ)** | llm_review.py, runner.py, FE | Thử tách paraphrase ra tab riêng, nhưng LLM (qwen) phán nhầm thay đổi thật (vd xóa 1 câu) là "giống nghĩa" → GIẤU thay đổi. Đã gỡ tab "Giống ngữ nghĩa": mọi cặp LLM coi là giống đều bỏ qua, không tách riêng |
| 12 | **Bôi đậm từ thay đổi** | [llm_prompts.py](../src/core/matching/llm_prompts.py), [ResultsPage.jsx](../web/frontend/src/components/ResultsPage.jsx) | LLM bọc từ thay đổi bằng `**...**`; frontend `renderRich` render `<strong>` tô nổi bật |

### 5.2. Chi tiết 3 fix quan trọng nhất

#### Fix #5 — Chunking lệch cấp (phát hiện ở VB4)
```mermaid
flowchart LR
    subgraph "Trước (max_tokens=512)"
        A1["VB1 Điều 7 = 565 token<br/>→ TÁCH khoan_1/2/3"]
        A2["VB2 Điều 7 = 429 token<br/>→ GIỮ NGUYÊN dieu_7"]
        A1 -.lệch cấp.- A2
        A2 --> A3["❌ Thêm mới Điều 7<br/>+ Xóa 3 khoản"]
    end
    subgraph "Sau (max_tokens=2000)"
        B1["VB1 Điều 7 → dieu_7"]
        B2["VB2 Điều 7 → dieu_7"]
        B1 --> B3["✅ Khớp Điều↔Điều<br/>+ zoom xuống khoản"]
        B2 --> B3
    end
```
Điều > 2000 token (vd Điều 2: 2124/2253) vẫn tách khoản ở **cả hai** → đối xứng. Phase 2 vẫn zoom xuống khoản/điểm qua registry nên không mất độ chi tiết.

#### Fix #6 — Bug "dư-1" (thụt lề)
```python
# TRƯỚC (sai): tasks.append NGOÀI vòng for
for d1 in unmatched_diem_1:
    chunk_d1 = ChunkDocumentForHierarchical(...)   # ← bị overwrite/rò rỉ
tasks.append({"args": (chunk_d1, "xoa_bo"), ...})  # ← chạy 1 lần với chunk_d1 còn sót

# SAU (đúng): tasks.append TRONG vòng for
for d1 in unmatched_diem_1:
    chunk_d1 = ChunkDocumentForHierarchical(...)
    tasks.append({"args": (chunk_d1, "xoa_bo"), ...})
```
Khi `unmatched_diem_1` rỗng, dòng `tasks.append` cũ vẫn chạy với `chunk_d1` của vòng lặp trước → sinh `xoa_bo` ma (vd "Xóa điểm d Điều 2" với `VB2=dieu_5`).

#### Fix #7 — `format_chunk` nuốt nội dung (phát hiện ở VB5)
```python
# TRƯỚC: ưu tiên tieu_de (chỉ là "Điều 3. PHÍ DỊCH VỤ...") → mất bảng phí
noi_dung = chunk.tieu_de or chunk.noi_dung or "(trống)"
# SAU: ưu tiên noi_dung (thân đầy đủ)
noi_dung = chunk.noi_dung or chunk.tieu_de or "(trống)"
```
LLM trước đây chỉ nhận tiêu đề (giống nhau ở 2 bản) → phán "identical" → bỏ sót mọi thay đổi trong thân Điều phẳng.

#### Fix #8 — Fix B (paraphrase, phát hiện ở VB1)
```mermaid
flowchart TD
    A["match_sub_nodes: [a,b,c,d] vs [a,b,c,d]"] --> B[Hungarian ghép a↔a,b↔b,c↔c,d↔d]
    B --> C{d↔d paraphrase<br/>hybrid < 0.65?}
    C -->|TRƯỚC| D["❌ Loại → d unmatched cả 2<br/>→ xóa d + thêm d"]
    C -->|SAU Fix B| E["✅ Ghép lại threshold=0<br/>→ llm_review_pair"]
    E --> F["LLM phán sua_doi/paraphrase"]
```
Đồng thời sửa runner: so cặp điểm đã khớp bằng **nội dung** (`cached_merged_text`), không phải `tieu_de` (với điểm chỉ là nhãn "Điểm a").

#### Fix #10 — Render numbering Word (phát hiện ở VB3)
Một số .docx đánh số "Điều 1, 2..." bằng **numbered-list tự động của Word** — số không nằm trong text mà do Word sinh khi hiển thị. Khi `docx → pandoc HTML → text`, số bị mất; parser không thấy "Điều N" → gom cả văn bản thành `modau_* + dieu_kho`.

```mermaid
flowchart TD
    A[VB3.docx] --> B[pypandoc → HTML]
    B --> C[extract_text_from_html]
    C --> D{Text có 'Điều N'?}
    D -->|Có VB1/4/5/10| E[Dùng luôn — không đụng]
    D -->|Không VB3| F[_render_docx_with_numbering]
    F --> G["Đọc numbering.xml:<br/>numId → lvlText template"]
    G --> H["Render counter theo template:<br/>'Điều %1.' → 'Điều 1.'<br/>'%1.' → '1.'<br/>'%1)' lowerLetter → 'a)'"]
    H --> I[Text có cấu trúc Điều/Khoản/Điểm]
    I --> J[parse_heading tách đúng]
```

Cơ chế **fallback** (chỉ chạy khi text pandoc thiếu "Điều N") nên không ảnh hưởng các văn bản đang chạy tốt. Kết quả: VB3 từ 4 chunk dị thường (`dieu_kho`) → đúng `dieu_1..9`, phát hiện **9/9** thay đổi.

#### Fix #11 — Surface paraphrase vào tab "Giống ngữ nghĩa" — ⚠️ ĐÃ GỠ
> **Đã gỡ bỏ** theo quyết định của người dùng: qwen phán nhầm thay đổi thật (vd xóa 1 câu thông báo điện thoại ở VB2) là "giống nghĩa" → giấu mất thay đổi. Tab "Giống ngữ nghĩa" bị bỏ hoàn toàn; mọi cặp LLM coi là giống → bỏ qua. Mô tả dưới đây giữ lại để tham khảo thiết kế.

Trước đây cặp con (khoản/điểm) được LLM phán `identical + type=paraphrase` → `llm_review_pair` trả `None` → callback **vứt bỏ** → biến mất khỏi mọi tab.

```mermaid
flowchart TD
    A[llm_review_pair: identical=true] --> B{type?}
    B -->|exact / danh_so| C[return None → giống hệt]
    B -->|paraphrase| D["return ChangeItem<br/>kind=giong_nhau_ngu_nghia"]
    D --> E[Callback append vào change_items]
    E --> F[Gom theo kind → tab Giống ngữ nghĩa]
    E --> G[Propagation BỎ QUA item ngu_nghia<br/>không giáng cấp cha]
```

Kèm example paraphrase trong prompt để qwen chịu phát `type=paraphrase`. Kết quả: VB1 `dieu_21.khoan_3.diem_a` (gt #9) vào đúng tab (trước bị drop); không mất detection, không regress VB3/4/10.

#### Fix #12 — Bôi đậm từ/cụm từ thay đổi
Prompt yêu cầu LLM bọc phần thay đổi trong `old_content`/`new_content` bằng `**...**`. Frontend [ResultsPage.jsx](../web/frontend/src/components/ResultsPage.jsx) có helper `renderRich` tách `**...**` → `<strong>` tô xanh.

```
Cũ: ...mỗi ngày chậm thanh toán phải chịu **1%** giá trị...
Mới: ...mỗi ngày chậm thanh toán phải chịu **0,05%** giá trị...
```
Giúp người đọc thấy ngay chỗ khác biệt (số liệu, phủ định, động từ tình thái).

---

## 6. Kết quả Kiểm thử (4 bộ văn bản, qwen3-80b)

| Bộ | Loại | Trước fix | Sau fix | Groundtruth |
|----|------|-----------|---------|-------------|
| **VB4** | Hợp đồng mua bán điện | Điều 7/8 sai hoàn toàn | **9/9** ✓ | 3 sửa / 2 thêm / 4 xóa |
| **VB1** | Hợp đồng tư vấn | 1 sửa, paraphrase tách xóa+thêm | **5 sửa / 1 thêm / 1 xóa** | nhiều paraphrase |
| **VB5** | Hợp đồng SEO | 0–1 (chỉ tiêu đề) | **3 sửa đúng** | cấu trúc phẳng |
| **VB10** | Hợp đồng xây dựng | 5/9 (eval cũ) | **9/9 phát hiện** ✓ | 6 sửa / 1 thêm / 1 xóa / 1 paraphrase |
| **VB3** | Hợp đồng thế chấp | 6/9, chunking sai (`dieu_kho`) | **9/9** ✓ | 5 sửa / 2 thêm / 2 xóa |

```mermaid
xychart-beta
    title "Độ phủ phát hiện thay đổi (số ca đúng)"
    x-axis ["VB4", "VB1", "VB5", "VB10", "VB3"]
    y-axis "Số ca" 0 --> 9
    bar [3, 1, 1, 5, 6]
    bar [9, 6, 3, 9, 9]
```
> Cột trái: trước fix — Cột phải: sau fix.

---

## 7. Hạn chế còn lại

| Hạn chế | Bản chất | Hướng xử lý |
|---------|----------|-------------|
| Summary sai số lẻ (vd "04 năm" → "0 năm") | Model qwen sinh nhầm chữ; phân loại vẫn đúng | UI hiển thị excerpt thật cạnh nhau; có thể thêm hậu kiểm số liệu |
| LLM phán nhầm "giống" cho thay đổi thật | qwen đôi khi coi việc xóa/thêm 1 câu là "giống nghĩa" → cặp đó bị bỏ qua (không hiện thành sửa đổi) | Đã gỡ tab paraphrase (tránh hiển thị sai); nhưng cặp bị LLM phán nhầm vẫn có thể bị bỏ sót — guard difflib là phương án nếu cần tăng recall |
| **Hiển thị bảng thật trên UI** (Feature 1) | Bảng hiện được flatten thành text để so sánh; UI chưa render `<table>` gốc | Đang lên kế hoạch — cần giữ HTML bảng theo section xuyên pipeline → API → frontend |
| Điều phẳng (không Khoản/Điểm) | Thêm/xóa trong Điều bị gộp thành 1 `sua_doi` cấp Điều | Tách Điều phẳng theo bullet/câu (chưa làm) |
| Điều > 2048 token | Vượt giới hạn embedding | Tách khoản (đã có); cân nhắc đồng bộ granularity 2 bản |
| Fallback numbering chưa xử lý bảng | `_render_docx_with_numbering` chỉ render text + numbering, chưa flatten bảng như pandoc | Văn bản vừa dùng Word-numbering vừa có bảng có thể mất bảng (hiếm) |

---

## 8. Luồng dữ liệu Backend → Frontend

```mermaid
sequenceDiagram
    participant U as User
    participant FE as React
    participant API as FastAPI
    participant P as run_pipeline
    U->>FE: Upload VB1 + VB2
    FE->>API: POST /api/compare
    API->>P: spawn thread
    API-->>FE: job_id
    loop mỗi 2s
        FE->>API: GET /jobs/id/status
    end
    P-->>API: PipelineResult (done)
    FE->>API: GET /jobs/id/results
    API-->>FE: stats + changes{sua_doi,them_moi,xoa_bo,giong_nhau_ngu_nghia} + report_text
    FE->>U: StatsCards + ChangeList (tabs) + SideBySide PDF
    U->>API: POST /jobs/id/chat (hỏi về báo cáo)
```

---

*Cập nhật: 2026-06-17*
