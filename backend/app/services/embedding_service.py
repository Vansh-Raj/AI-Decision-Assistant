from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from ..config import settings


class EmbeddingService:
    def __init__(self, embeddings: OpenAIEmbeddings | None = None) -> None:
        self.embeddings = embeddings or OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            max_retries=3,
            timeout=60.0,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embeddings.embed_query(text)
