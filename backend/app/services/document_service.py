from __future__ import annotations

from io import BytesIO
from pathlib import Path
import time
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader

from ..config import settings
from ..db import utc_now
from ..observability import get_logger, log_event
from ..repositories import ChunkRepository, DocumentRecord, DocumentRepository
from .chunking_service import ChunkingService
from .embedding_service import EmbeddingService
from .vector_store_service import VectorStoreService

logger = get_logger("document_service")


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository | None = None,
        chunk_repository: ChunkRepository | None = None,
        chunking_service: ChunkingService | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store_service: VectorStoreService | None = None,
    ) -> None:
        self.repository = repository or DocumentRepository()
        self.chunk_repository = chunk_repository or ChunkRepository()
        self.chunking_service = chunking_service or ChunkingService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store_service = vector_store_service or VectorStoreService()

    async def save_upload_initial(self, file: UploadFile) -> DocumentRecord:
        start = time.perf_counter()
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        filename = file.filename or "uploaded_document"
        content_type = file.content_type or "application/octet-stream"
        
        stored_filename = f"{uuid4().hex}_{Path(filename).name}"
        storage_path = settings.storage_dir / stored_filename
        storage_path.write_bytes(raw_bytes)

        document = self.repository.create(
            filename=filename,
            content_type=content_type,
            size_bytes=len(raw_bytes),
            storage_path=str(storage_path),
        )
        self.repository.update_status(document.id, "processing")
        document.status = "processing"
        log_event(
            logger,
            "document_saved",
            document_id=document.id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(raw_bytes),
            storage_path=str(storage_path),
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
        return document

    def process_upload_background(self, document_id: int, storage_path: str, filename: str) -> None:
        start = time.perf_counter()
        try:
            log_event(
                logger,
                "document_processing_started",
                document_id=document_id,
                filename=filename,
                storage_path=storage_path,
            )
            raw_bytes = Path(storage_path).read_bytes()
            extracted_text = self._extract_text(raw_bytes, filename)

            document = self.repository.get(document_id)
            if not document:
                log_event(logger, "document_processing_skipped", document_id=document_id, reason="missing_document")
                return

            uploaded_at = document.uploaded_at or utc_now()
            chunks = self.chunking_service.create_chunks(extracted_text, uploaded_at)
            if not chunks:
                self.repository.update_status(document_id, "failed")
                log_event(logger, "document_processing_failed", document_id=document_id, reason="no_chunks_created")
                return

            chunk_records = self.chunk_repository.bulk_create(
                document_id=document_id,
                chunks=chunks,
            )
            vectors = self.embedding_service.embed_documents(
                [chunk.content for chunk in chunk_records]
            )
            payloads = [
                {
                    "doc_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "page_content": chunk.content,
                    "metadata": {
                        "doc_id": chunk.document_id,
                        "chunk_id": chunk.id,
                        "filename": filename,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "upload_timestamp": chunk.upload_timestamp.isoformat(),
                    },
                }
                for chunk in chunk_records
            ]
            self.vector_store_service.upsert_chunks(
                chunk_ids=[chunk.id for chunk in chunk_records],
                vectors=vectors,
                payloads=payloads,
            )
            self.repository.update_status(document_id, "completed")
            log_event(
                logger,
                "document_processing_completed",
                document_id=document_id,
                filename=filename,
                chunk_count=len(chunk_records),
                extracted_chars=len(extracted_text),
                latency_ms=round((time.perf_counter() - start) * 1000),
            )
        except Exception:
            self.repository.update_status(document_id, "failed")
            log_event(
                logger,
                "document_processing_failed",
                level=logger.exception,
                document_id=document_id,
                filename=filename,
                latency_ms=round((time.perf_counter() - start) * 1000),
            )

    def _extract_text(self, raw_bytes: bytes, filename: str) -> str:
        lowered_name = filename.lower()
        if lowered_name.endswith(".pdf"):
            text = self._extract_pdf_text(raw_bytes)
        else:
            text = raw_bytes.decode("utf-8", errors="ignore")

        text = text.replace("\x00", "").strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Could not extract usable text from '{filename}'. "
                    "Use UTF-8 text, CSV, JSON, markdown, or a text-based PDF."
                ),
            )
        return text

    def _extract_pdf_text(self, raw_bytes: bytes) -> str:
        reader = PdfReader(BytesIO(raw_bytes))
        pages: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            page_text = page_text.replace("\x00", "").strip()
            if page_text:
                pages.append(page_text)
        return "\f".join(pages)
