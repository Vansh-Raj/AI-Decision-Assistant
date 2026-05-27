from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row

from .config import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_directories() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    ensure_directories()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id BIGSERIAL PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    storage_path TEXT NOT NULL,
                    uploaded_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    page_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    upload_timestamp TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_document_chunks_doc_chunk
                ON document_chunks (document_id, chunk_index)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
                ON document_chunks (document_id)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    id BIGSERIAL PRIMARY KEY,
                    query TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    reasoning TEXT NOT NULL DEFAULT '',
                    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                    retrieval_latency_ms INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    matched_document_ids BIGINT[] NOT NULL,
                    matched_chunk_ids BIGINT[] NOT NULL,
                    raw_response TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'query_history' AND column_name = 'question'
                    ) THEN
                        ALTER TABLE query_history RENAME COLUMN question TO query;
                    END IF;
                END
                $$;
                """
            )
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'query_history' AND column_name = 'reasoning_summary'
                    ) THEN
                        ALTER TABLE query_history RENAME COLUMN reasoning_summary TO reasoning;
                    END IF;
                END
                $$;
                """
            )
            cursor.execute(
                """
                ALTER TABLE query_history
                ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb
                """
            )
            cursor.execute(
                """
                ALTER TABLE query_history
                ADD COLUMN IF NOT EXISTS retrieval_latency_ms INTEGER NOT NULL DEFAULT 0
                """
            )
            cursor.execute(
                """
                ALTER TABLE query_history
                ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0
                """
            )
            cursor.execute(
                """
                ALTER TABLE query_history
                ADD COLUMN IF NOT EXISTS raw_response TEXT NOT NULL DEFAULT ''
                """
            )
            cursor.execute(
                """
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed'
                """
            )
        connection.commit()


@contextmanager
def get_connection() -> Iterator[Connection]:
    connection = Connection.connect(
        conninfo=settings.postgres_dsn,
        row_factory=dict_row,
    )
    try:
        yield connection
    finally:
        connection.close()
