import logging

VB1_PATH = "vb1.docx"
VB2_PATH = "vb2.docx"
EMBEDDING_MODEL_DIR = "./models/Vietnamese_Embedding_v2"
RERANKER_MODEL_DIR = "./models/bge-reranker-v2-m3"
OLLAMA_MODEL = "qwen2.5:0.5b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

TOP_K = 8
DISTANCE_THRESHOLD = 0.185
RERANK_THRESHOLD = 0.985
HYBRID_THRESHOLD = 0.75

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pair_match_pipeline")
