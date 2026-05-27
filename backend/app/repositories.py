from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .db import get_connection, utc_now


@dataclass
class DocumentRecord:
    id: int
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    uploaded_at: datetime
    status: str = "completed"


@dataclass
class ChunkRecord:
    id: int
    document_id: int
    chunk_index: int
    page_number: int
    content: str
    upload_timestamp: datetime
    created_at: datetime


@dataclass
class ChunkSearchRecord:
    id: int
    document_id: int
    filename: str
    chunk_index: int
    page_number: int
    content: str
    upload_timestamp: datetime


@dataclass
class QueryHistoryRecord:
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


class DocumentRepository:
    def create(
        self,
        *,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> DocumentRecord:
        uploaded_at = utc_now()
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO documents (
                        filename,
                        content_type,
                        size_bytes,
                        storage_path,
                        uploaded_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, filename, content_type, size_bytes, storage_path, uploaded_at
                    """,
                    (
                        filename,
                        content_type,
                        size_bytes,
                        storage_path,
                        uploaded_at,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return DocumentRecord(**row)

    def get(self, document_id: int) -> DocumentRecord | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, filename, content_type, size_bytes, storage_path, uploaded_at, status
                    FROM documents
                    WHERE id = %s
                    """,
                    (document_id,)
                )
                row = cursor.fetchone()
        if row:
            return DocumentRecord(**row)
        return None

    def update_status(self, document_id: int, status: str) -> None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE documents SET status = %s WHERE id = %s
                    """,
                    (status, document_id)
                )
            connection.commit()


class ChunkRepository:
    def bulk_create(
        self,
        *,
        document_id: int,
        chunks: list[dict[str, int | str | datetime]],
    ) -> list[ChunkRecord]:
        records: list[ChunkRecord] = []
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for chunk in chunks:
                    cursor.execute(
                        """
                        INSERT INTO document_chunks (
                            document_id,
                            chunk_index,
                            page_number,
                            content,
                            upload_timestamp
                        ) VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, document_id, chunk_index, page_number,
                                  content, upload_timestamp, created_at
                        """,
                        (
                            document_id,
                            chunk["chunk_index"],
                            chunk["page_number"],
                            chunk["content"],
                            chunk["upload_timestamp"],
                        ),
                    )
                    records.append(ChunkRecord(**cursor.fetchone()))
            connection.commit()
        return records

    def get_by_ids(self, chunk_ids: list[int]) -> list[ChunkRecord]:
        if not chunk_ids:
            return []
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, document_id, chunk_index, page_number,
                           content, upload_timestamp, created_at
                    FROM document_chunks
                    WHERE id = ANY(%s)
                    """,
                    (chunk_ids,),
                )
                rows = cursor.fetchall()
        order = {chunk_id: idx for idx, chunk_id in enumerate(chunk_ids)}
        rows.sort(key=lambda row: order.get(row["id"], len(order)))
        return [ChunkRecord(**row) for row in rows]

    def list_for_retrieval(self, doc_id: int | None = None) -> list[ChunkSearchRecord]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if doc_id is None:
                    cursor.execute(
                        """
                        SELECT dc.id, dc.document_id, d.filename, dc.chunk_index,
                               dc.page_number, dc.content, dc.upload_timestamp
                        FROM document_chunks dc
                        JOIN documents d ON d.id = dc.document_id
                        ORDER BY dc.document_id, dc.chunk_index
                        """
                    )
                else:
                    cursor.execute(
                        """
                        SELECT dc.id, dc.document_id, d.filename, dc.chunk_index,
                               dc.page_number, dc.content, dc.upload_timestamp
                        FROM document_chunks dc
                        JOIN documents d ON d.id = dc.document_id
                        WHERE dc.document_id = %s
                        ORDER BY dc.chunk_index
                        """,
                        (doc_id,),
                    )
                rows = cursor.fetchall()
        return [ChunkSearchRecord(**row) for row in rows]


class QueryHistoryRepository:
    def get_cached_query(self, query: str, doc_id: int | None = None) -> QueryHistoryRecord | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, query, answer, reasoning, sources,
                           retrieval_latency_ms, chunk_count,
                           matched_document_ids, matched_chunk_ids,
                           raw_response, created_at
                    FROM query_history
                    WHERE query = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (query,)
                )
                row = cursor.fetchone()
        if row:
            if doc_id is not None and doc_id not in row["matched_document_ids"]:
                return None
            if isinstance(row["sources"], str):
                row["sources"] = json.loads(row["sources"])
            return QueryHistoryRecord(**row)
        return None

    def list_recent(self, limit: int) -> list[QueryHistoryRecord]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, query, answer, reasoning, sources,
                           retrieval_latency_ms, chunk_count,
                           matched_document_ids, matched_chunk_ids,
                           raw_response, created_at
                    FROM query_history
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()

        normalized: list[QueryHistoryRecord] = []
        for row in rows:
            if isinstance(row["sources"], str):
                row["sources"] = json.loads(row["sources"])
            normalized.append(QueryHistoryRecord(**row))
        return normalized
