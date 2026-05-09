# Hướng dẫn Setup dự án Legal Doc Diff RAG

> **Yêu cầu**: Python 3.10+, NVIDIA GPU (CUDA 13.0), Node.js 20+, 8GB+ RAM

---

## 1. Cài thư viện hệ thống

```bash
sudo apt update && sudo apt install -y pandoc libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

## 2. Tạo virtual environment & cài Python dependencies

```bash
cd legal-doc-diff-rag
python3 -m venv myenv
source myenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Cài Node.js & Frontend

```bash
# Cài Node.js 20+ (nếu chưa có)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Cài frontend dependencies
cd web/frontend
npm install
cd ../..
```

## 5. Cấu hình

### `src/config.py` — URL Ollama

```python
# Chạy local:
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Qua Cloudflare Tunnel:
OLLAMA_URL = "https://<ollama-tunnel>.trycloudflare.com/api/generate"
```

### `web/app.py` — CORS origins

```python
allow_origins=[
    "http://localhost:5173",
    # Thêm domain tunnel FE nếu cần:
    # "https://<fe-tunnel>.trycloudflare.com",
]
```

### `web/frontend/vite.config.js` — API proxy

```js
server: {
    // Thêm allowedHosts nếu dùng tunnel:
    // allowedHosts: ['<fe-tunnel>.trycloudflare.com'],
    proxy: {
        '/api': {
            target: 'http://127.0.0.1:8080',
            changeOrigin: true,
        },
    },
}
```

## 6. Chạy dự án (3 terminal)

```bash
# Terminal 1 — Ollama
ollama serve

# Terminal 2 — Backend
cd legal-doc-diff-rag
source myenv/bin/activate
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload --reload-dir src --reload-exclude "web/frontend/*"

# Terminal 3 — Frontend
cd legal-doc-diff-rag/web/frontend
npm run dev
```


