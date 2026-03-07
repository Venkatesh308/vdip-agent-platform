import os
from dotenv import load_dotenv
load_dotenv()
LLM_HOST       = os.getenv("LLM_HOST", "localhost")
LLM_PORT       = int(os.getenv("LLM_PORT", "8080"))
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "data/models/phi-3-mini-q4.gguf")
EMBED_MODEL    = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
CHROMA_PATH    = os.getenv("CHROMA_PERSIST_PATH", "knowledge/chroma_db")
CAN_CHANNEL    = os.getenv("CAN_CHANNEL", "can0")
CAN_BITRATE    = int(os.getenv("CAN_BITRATE", "500000"))
API_HOST       = os.getenv("API_HOST", "0.0.0.0")
API_PORT       = int(os.getenv("API_PORT", "8000"))
WEB_PORT       = int(os.getenv("WEB_PORT", "7860"))
