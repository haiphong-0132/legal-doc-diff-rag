import os
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Tìm thư mục gốc của project chứa file .env và load nó
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=root_dir / ".env", override=True)

# -------------------------------------------------------------------------
# ĐỌC CẤU HÌNH TỪ FILE YAML TRUNG TÂM
# -------------------------------------------------------------------------
yaml_path = root_dir / "configs" / "config.yaml"
if yaml_path.exists():
    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_config = yaml.safe_load(f) or {}
else:
    yaml_config = {}

# Trích xuất các phân nhóm cấu hình (có phòng hờ nếu file trống)
paths_cfg = yaml_config.get("paths", {})
thresholds_cfg = yaml_config.get("pipeline_thresholds", {})
llm_cfg = yaml_config.get("llm", {})
embed_cfg = yaml_config.get("embedding", {})
web_cfg = yaml_config.get("web", {})

# -------------------------------------------------------------------------
# 1. CẤU HÌNH ĐƯỜNG DẪN (PATHS)
# -------------------------------------------------------------------------
VB1_PATH = os.getenv("VB1_PATH", paths_cfg.get("vb1_path", "vb1.docx"))
VB2_PATH = os.getenv("VB2_PATH", paths_cfg.get("vb2_path", "vb2.docx"))

EMBEDDING_MODEL_DIR = os.getenv("EMBEDDING_MODEL_DIR", paths_cfg.get("embedding_model_dir", "./models/Vietnamese_Embedding_v2"))
RERANKER_MODEL_DIR = os.getenv("RERANKER_MODEL_DIR", paths_cfg.get("reranker_model_dir", "./models/bge-reranker-v2-m3"))

# -------------------------------------------------------------------------
# 2. CẤU HÌNH ENDPOINTS (API HOSTS)
# -------------------------------------------------------------------------
DEFAULT_API_BASE = os.getenv("API_BASE_URL", "http://localhost:8080")

EMBED_API_URL = os.getenv("EMBED_API_URL") or DEFAULT_API_BASE
RERANK_API_URL = os.getenv("RERANK_API_URL") or DEFAULT_API_BASE
LLM_API_URL = os.getenv("LLM_API_URL") or DEFAULT_API_BASE

# -------------------------------------------------------------------------
# 3. CẤU HÌNH PIPELINE THRESHOLDS
# -------------------------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", thresholds_cfg.get("top_k", 8)))
DISTANCE_THRESHOLD = float(os.getenv("DISTANCE_THRESHOLD", thresholds_cfg.get("distance_threshold", 0.185)))
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", thresholds_cfg.get("rerank_threshold", 0.985)))
HYBRID_THRESHOLD = float(os.getenv("HYBRID_THRESHOLD", thresholds_cfg.get("hybrid_threshold", 0.75)))

# -------------------------------------------------------------------------
# 4. CẤU HÌNH CHO LLM (MODE, KEYS, PARAMETERS)
# -------------------------------------------------------------------------
LLM_MODE = os.getenv("LLM_MODE", llm_cfg.get("mode", "remote")).lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", llm_cfg.get("api_key", ""))
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", llm_cfg.get("model_name", "qwen/qwen3-next-80b-a3b-instruct"))

# Tham số tạo sinh (Nvidia / Remote)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", llm_cfg.get("temperature", 0.6)))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", llm_cfg.get("top_p", 0.7)))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", llm_cfg.get("max_tokens", 4096)))

LLM_REMOTE_TEMPERATURE = float(os.getenv("LLM_REMOTE_TEMPERATURE", llm_cfg.get("remote_temperature", 0.0)))
LLM_REMOTE_MAX_LENGTH = int(os.getenv("LLM_REMOTE_MAX_LENGTH", llm_cfg.get("remote_max_length", 2000)))
LLM_REMOTE_TIMEOUT = int(os.getenv("LLM_REMOTE_TIMEOUT", llm_cfg.get("remote_timeout", 180)))

# -------------------------------------------------------------------------
# 5. CẤU HÌNH EMBEDDING CỤC BỘ
# -------------------------------------------------------------------------
EMBEDDING_MAX_LENGTH = int(embed_cfg.get("max_length", 2048))
EMBEDDING_NORMALIZE = bool(embed_cfg.get("normalize", True))
EMBEDDING_BATCH_SIZE = int(embed_cfg.get("batch_size", 32))

# -------------------------------------------------------------------------
# 6. CẤU HÌNH WEB
# -------------------------------------------------------------------------
WEB_MAX_FILE_SIZE = int(web_cfg.get("max_file_size", 20 * 1024 * 1024))
WEB_ALLOWED_EXTENSIONS = set(web_cfg.get("allowed_extensions", [".docx", ".pdf"]))

# -------------------------------------------------------------------------
# THIẾT LẬP LOGGER CHUNG
# -------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pair_match_pipeline")
