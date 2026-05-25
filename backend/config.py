import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str   = os.getenv("GROQ_API_KEY", "")
JIRA_URL: str       = os.getenv("JIRA_URL", "")
JIRA_USERNAME: str  = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
CHAT_MODEL: str     = os.getenv("CHAT_MODEL", "gpt-4o")
OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
GOOGLE_CHAT_MODEL: str = os.getenv("GOOGLE_CHAT_MODEL", "gemini-1.5-flash")
GROQ_CHAT_MODEL: str = os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
CONFLUENCE_URL: str       = os.getenv("CONFLUENCE_URL", "")
CONFLUENCE_USERNAME: str  = os.getenv("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN", "")

CORS_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# Example: postgresql://user:password@localhost:5432/ai_ticket_analyzer
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── RAG / Embeddings ──────────────────────────────────────────────────────────
EMBEDDING_MODEL: str      = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

# Chunking
CHUNK_MAX_TOKENS: int     = int(os.getenv("CHUNK_MAX_TOKENS", "512"))
CHUNK_MIN_TOKENS: int     = int(os.getenv("CHUNK_MIN_TOKENS", "50"))
CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "64"))

# Retrieval
RETRIEVAL_TOP_K: int  = int(os.getenv("RETRIEVAL_TOP_K", "50"))
RERANK_TOP_N: int     = int(os.getenv("RERANK_TOP_N", "8"))
DENSE_WEIGHT: float   = float(os.getenv("DENSE_WEIGHT", "0.6"))
BM25_WEIGHT: float    = float(os.getenv("BM25_WEIGHT", "0.4"))
RRF_K: int            = 60  # reciprocal rank fusion constant

# Context window budget reserved for RAG snippets (in tokens)
CONTEXT_TOKEN_BUDGET: int = int(os.getenv("CONTEXT_TOKEN_BUDGET", "3000"))

# Cross-encoder model for reranking (ONNX-based via flashrank)
CROSS_ENCODER_MODEL: str = os.getenv("CROSS_ENCODER_MODEL", "ms-marco-MiniLM-L-12-v2")