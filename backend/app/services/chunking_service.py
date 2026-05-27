from __future__ import annotations

from datetime import datetime

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import settings


class ChunkingService:
    def __init__(self) -> None:
        self.chunker = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=list(settings.chunk_separators),
            length_function=len,
        )

    def create_chunks(
        self, text: str, uploaded_at: datetime
    ) -> list[dict[str, int | str | datetime]]:
        pages = self._split_pages(text)
        chunks: list[dict[str, int | str | datetime]] = []
        next_chunk_index = 0

        for page_number, page_text in pages:
            page_chunks = self.chunker.split_text(page_text)
            for content in page_chunks:
                content = content.strip()
                if not content:
                    continue
                chunks.append(
                    {
                        "chunk_index": next_chunk_index,
                        "page_number": page_number,
                        "content": content,
                        "upload_timestamp": uploaded_at,
                    }
                )
                next_chunk_index += 1

        return chunks

    def _split_pages(self, text: str) -> list[tuple[int, str]]:
        raw_pages = [page.strip() for page in text.split("\f")]
        non_empty_pages = [page for page in raw_pages if page]
        if not non_empty_pages:
            return [(1, text.strip())]
        return [(index + 1, page) for index, page in enumerate(non_empty_pages)]
