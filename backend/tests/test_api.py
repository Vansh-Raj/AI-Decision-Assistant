from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routes import get_document_service, get_rag_pipeline


@dataclass
class FakeDocumentRecord:
    id: int
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


@dataclass
class FakeHistoryRecord:
    id: int
    query: str
    answer: str
    reasoning: str
    sources: list[dict[str, object]]
    retrieval_latency_ms: int
    chunk_count: int
    matched_document_ids: list[int]
    matched_chunk_ids: list[int]
    raw_response: str
    created_at: datetime


class FakeDocumentService:
    async def save_upload(self, _file):
        return (
            FakeDocumentRecord(
                id=1,
                filename="metrics.txt",
                content_type="text/plain",
                size_bytes=32,
                uploaded_at=datetime.now(timezone.utc),
            ),
            2,
        )


class FakeRagPipeline:
    async def stream_rag_response(
        self, query: str, doc_id: int | None = None, top_k: int = 5
    ) -> AsyncGenerator[str, None]:
        yield (
            'data: {"type": "retrieval_done", "chunk_count": 1, '
            '"latency_ms": 24, "chunks": [{"chunk_id": 11, "doc_id": 1, '
            '"filename": "metrics.txt", "page_number": 1, "chunk_index": 0}]}\n\n'
        )
        yield 'data: {"type": "token", "text": "<answer>Revenue improved.</answer>"}\n\n'
        yield (
            'data: {"type": "citations", "data": [{"chunk_id": "chunk_1", '
            '"page": 1, "filename": "metrics.txt", '
            '"excerpt": "Revenue grew 18 percent in Q4."}]}\n\n'
        )
        yield (
            'data: {"type": "final", "answer": "Revenue improved.", '
            '"reasoning": "The retrieved chunk states that revenue grew 18 percent.", '
            '"sources": [{"chunk_id": "chunk_1", "page": 1, '
            '"filename": "metrics.txt", "excerpt": "Revenue grew 18 percent in Q4."}]}\n\n'
        )
        yield "data: [DONE]\n\n"

    def list_history(self, _limit: int) -> list[FakeHistoryRecord]:
        now = datetime.now(timezone.utc)
        return [
            FakeHistoryRecord(
                id=1,
                query="What happened to revenue in Q4?",
                answer="Revenue improved.",
                reasoning="The retrieved chunk states that revenue grew 18 percent.",
                sources=[
                    {
                        "chunk_id": "chunk_1",
                        "page": 1,
                        "filename": "metrics.txt",
                        "excerpt": "Revenue grew 18 percent in Q4.",
                    }
                ],
                retrieval_latency_ms=24,
                chunk_count=1,
                matched_document_ids=[1],
                matched_chunk_ids=[11],
                raw_response="<answer>Revenue improved.</answer>",
                created_at=now,
            )
        ]


def test_upload_query_and_history_flow() -> None:
    app.dependency_overrides[get_document_service] = FakeDocumentService
    app.dependency_overrides[get_rag_pipeline] = FakeRagPipeline
    try:
        with patch("backend.app.main.init_db"), patch(
            "backend.app.main.VectorStoreService"
        ) as vector_store_cls:
            vector_store_cls.return_value.ensure_collection.return_value = None
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/upload",
                    files={
                        "file": (
                            "metrics.txt",
                            b"Revenue grew 18 percent in Q4.",
                            "text/plain",
                        )
                    },
                )
                assert upload_response.status_code == 200
                uploaded = upload_response.json()
                assert uploaded["filename"] == "metrics.txt"
                assert uploaded["chunk_count"] == 2

                query_response = client.post(
                    "/api/query",
                    json={
                        "question": "What happened to revenue in Q4?",
                        "top_k": 1,
                        "doc_id": 1,
                    },
                )
                assert query_response.status_code == 200
                assert query_response.headers["content-type"].startswith(
                    "text/event-stream"
                )
                body = query_response.text
                assert '"type": "retrieval_done"' in body
                assert '"type": "citations"' in body
                assert "data: [DONE]" in body

                history_response = client.get("/api/history?limit=5")
                assert history_response.status_code == 200
                history = history_response.json()
                assert history["count"] == 1
                assert history["items"][0]["query"] == "What happened to revenue in Q4?"
                assert history["items"][0]["matched_chunk_ids"] == [11]
    finally:
        app.dependency_overrides.clear()
