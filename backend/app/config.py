from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Decision Backend"
    app_version: str = "0.2.0"
    storage_dir: Path = Path(
        os.getenv("STORAGE_DIR", "backend/data/uploads")
    ).resolve()
    max_history_limit: int = int(os.getenv("MAX_HISTORY_LIMIT", "100"))
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://postgres:postgres@localhost:5433/ai_decision",
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        os.getenv(
            "POSTGRES_DSN",
            "postgresql://postgres:postgres@localhost:5433/ai_decision",
        ),
    )
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")
    qdrant_collection_name: str = os.getenv(
        "QDRANT_COLLECTION_NAME", "documents"
    )
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "openai/text-embedding-3-small",
    )
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    chat_model: str = os.getenv("CHAT_MODEL", "openai/gpt-5-nano")
    retrieval_fetch_k: int = int(os.getenv("RETRIEVAL_FETCH_K", "20"))
    retrieval_lambda_mult: float = float(os.getenv("RETRIEVAL_LAMBDA_MULT", "0.7"))
    compression_similarity_threshold: float = float(
        os.getenv("COMPRESSION_SIMILARITY_THRESHOLD", "0.20")
    )
    bm25_top_k: int = int(os.getenv("BM25_TOP_K", "8"))
    hybrid_candidate_limit: int = int(os.getenv("HYBRID_CANDIDATE_LIMIT", "12"))
    chunk_size: int = int(
        os.getenv("CHUNK_SIZE", "1800")
    )
    chunk_overlap: int = int(
        os.getenv("CHUNK_OVERLAP", "250")
    )
    chunk_separators: tuple[str, ...] = (
        "\n\n",
        "\n",
        ". ",
        " ",
        "",
    )


settings = Settings()
