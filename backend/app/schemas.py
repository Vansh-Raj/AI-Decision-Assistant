from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: int
    filename: str
    content_type: str
    size_bytes: int
    chunk_count: int
    uploaded_at: datetime
    status: str = "completed"


class DocumentStatusResponse(BaseModel):
    status: str
    chunk_count: int


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)
    doc_id: int | None = None
    chat_history: list[ChatMessage] | None = None


class HistoryItem(BaseModel):
    id: int
    query: str
    answer: str
    reasoning: str
    sources: list[dict[str, Any]]
    retrieval_latency_ms: int
    chunk_count: int
    matched_document_ids: list[int]
    matched_chunk_ids: list[int]
    raw_response: str
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    count: int


class ErrorResponse(BaseModel):
    detail: str
    meta: dict[str, Any] | None = None
