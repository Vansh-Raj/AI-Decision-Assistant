from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models

from ..config import settings


class VectorStoreService:
    def __init__(self, client: QdrantClient | None = None) -> None:
        self.client = client or QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self.collection_name = settings.qdrant_collection_name

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_chunks(
        self,
        *,
        chunk_ids: list[int],
        vectors: list[list[float]],
        payloads: list[dict[str, object]],
    ) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(id=chunk_id, vector=vector, payload=payload)
                for chunk_id, vector, payload in zip(chunk_ids, vectors, payloads, strict=True)
            ],
        )

    def search(self, *, vector: list[float], limit: int) -> list[models.ScoredPoint]:
        return self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
