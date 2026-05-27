from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass

from langsmith import traceable
from typing import AsyncGenerator

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import EmbeddingsFilter
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from psycopg import AsyncConnection
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from rank_bm25 import BM25Okapi

from ..config import settings
from ..repositories import (
    ChunkRepository,
    ChunkSearchRecord,
    QueryHistoryRecord,
    QueryHistoryRepository,
)
from ..schemas import ChatMessage


SYSTEM_PROMPT = """You are a decision-support assistant. Answer the user's question
using ONLY the provided context chunks and the previous conversation history. Do not use prior external knowledge.

Rules:
- If the answer is not in the context or conversation history, say "I could not find this in the uploaded documents."
- Always cite your sources using the chunk IDs provided when referencing context chunks.
- Include risks, uncertainties, and conclusions when the context supports them.
- Be concise but complete.

Respond in this exact XML structure:
<reasoning>
Your step-by-step reasoning about what the context says, including risks and conclusions.
</reasoning>
<answer>
Your final answer in plain language.
</answer>
<sources>
[{"chunk_id": "...", "page": 1, "filename": "...", "excerpt": "...first 80 chars of chunk..."}]
</sources>"""


RETRIEVAL_PLANNER_PROMPT = """You are a retrieval planner for a RAG system.
Given a user query and the chat history, decide the best retrieval strategy and rewrite the query
for retrieval. Resolve any pronouns or references to the previous conversation (e.g. "the last reference", "it", "this") so the search query is self-contained.

CRITICAL: The `search_query` MUST NOT be an instruction or command (e.g. do not say "List all..." or "Find the..."). Instead, it MUST be the raw semantic concepts, statements, or keywords you expect to find verbatim in the target document (e.g. "references bibliography citations").

Valid retrieval modes:
- "semantic": concept-heavy, fuzzy, paraphrased, or intent-based questions
- "bm25": exact keyword, field name, heading, acronym, lookup, or citation-style questions
- "hybrid": mixed or uncertain cases; use both

Return ONLY valid JSON:
{"mode":"semantic|bm25|hybrid","search_query":"...","reason":"..."}"""


@dataclass
class RetrievalPlan:
    mode: str
    search_query: str
    reason: str


class RagPipeline:
    def __init__(
        self,
        embeddings: OpenAIEmbeddings | None = None,
        qdrant_client: QdrantClient | None = None,
        llm: ChatOpenAI | None = None,
        history_repository: QueryHistoryRepository | None = None,
        chunk_repository: ChunkRepository | None = None,
    ) -> None:
        self.embeddings = embeddings or OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            max_retries=3,
            timeout=30.0,
        )
        self.qdrant_client = qdrant_client or QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=10.0,
        )
        self.vectorstore = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=settings.qdrant_collection_name,
            embedding=self.embeddings,
        )
        self.llm = llm or ChatOpenAI(
            model=settings.chat_model,
            temperature=0,
            streaming=True,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            max_retries=3,
            timeout=30.0,
        )
        self.history_repository = history_repository or QueryHistoryRepository()
        self.chunk_repository = chunk_repository or ChunkRepository()

    @traceable(name="choose_retrieval_plan")
    def choose_retrieval_plan(self, query: str, chat_history: list[ChatMessage] | None = None) -> RetrievalPlan:
        messages = [
            SystemMessage(content=RETRIEVAL_PLANNER_PROMPT)
        ]
        if chat_history:
            history_str = "\n".join([f"{msg.role}: {msg.content}" for msg in chat_history])
            messages.append(SystemMessage(content=f"Chat History:\n{history_str}"))
        messages.append(HumanMessage(content=f"Current Query: {query}"))
        
        try:
            response = self.llm.invoke(messages)
            content = response.content if isinstance(response.content, str) else ""
            parsed = json.loads(content)
            mode = str(parsed.get("mode", "hybrid")).lower()
            if mode not in {"semantic", "bm25", "hybrid"}:
                mode = "hybrid"
            search_query = str(parsed.get("search_query") or query).strip() or query
            reason = str(parsed.get("reason") or "LLM selected retrieval strategy.")
            return RetrievalPlan(mode=mode, search_query=search_query, reason=reason)
        except Exception:
            return RetrievalPlan(
                mode="hybrid",
                search_query=query,
                reason="Fell back to hybrid retrieval after planner parse failure.",
            )

    @traceable(name="retrieve_chunks")
    def retrieve_chunks(
        self, query: str, doc_id: int | None = None, k: int = 5, chat_history: list[ChatMessage] | None = None
    ) -> tuple[list[Document], float, RetrievalPlan]:
        plan = self.choose_retrieval_plan(query, chat_history)
        start = time.perf_counter()

        semantic_chunks: list[Document] = []
        bm25_chunks: list[Document] = []

        if plan.mode in {"semantic", "hybrid"}:
            semantic_chunks = self._semantic_retrieve(plan.search_query, doc_id, k)
        if plan.mode in {"bm25", "hybrid"}:
            bm25_chunks = self._bm25_retrieve(
                plan.search_query,
                doc_id,
                settings.bm25_top_k,
            )

        if plan.mode == "semantic":
            chunks = semantic_chunks
        elif plan.mode == "bm25":
            chunks = bm25_chunks[:k]
        else:
            chunks = self._merge_results(semantic_chunks, bm25_chunks, k)

        retrieval_latency = time.perf_counter() - start
        return chunks, retrieval_latency, plan

    def _semantic_retrieve(
        self, query: str, doc_id: int | None, k: int
    ) -> list[Document]:
        search_kwargs: dict[str, object] = {
            "k": k,
            "fetch_k": settings.retrieval_fetch_k,
            "lambda_mult": settings.retrieval_lambda_mult,
        }
        if doc_id is not None:
            search_kwargs["filter"] = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="doc_id",
                        match=qdrant_models.MatchValue(value=doc_id),
                    )
                ]
            )

        base_retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs=search_kwargs,
        )
        compression_retriever = ContextualCompressionRetriever(
            base_retriever=base_retriever,
            base_compressor=EmbeddingsFilter(
                embeddings=self.embeddings,
                similarity_threshold=settings.compression_similarity_threshold,
            ),
        )
        return compression_retriever.invoke(query)

    def _bm25_retrieve(
        self, query: str, doc_id: int | None, k: int
    ) -> list[Document]:
        records = self.chunk_repository.list_for_retrieval(doc_id)
        if not records:
            return []

        tokenized_corpus = [self._tokenize(record.content) for record in records]
        if not any(tokenized_corpus):
            return []

        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = self._tokenize(query)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(records, scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )

        documents: list[Document] = []
        for record, score in ranked[:k]:
            if score <= 0:
                continue
            documents.append(self._record_to_document(record, score, "bm25"))
        return documents

    def _record_to_document(
        self, record: ChunkSearchRecord, score: float, source: str
    ) -> Document:
        return Document(
            page_content=record.content,
            metadata={
                "doc_id": record.document_id,
                "chunk_id": record.id,
                "filename": record.filename,
                "chunk_index": record.chunk_index,
                "page_number": record.page_number,
                "upload_timestamp": record.upload_timestamp.isoformat(),
                "score": score,
                "retrieval_source": source,
            },
        )

    def _merge_results(
        self, semantic_chunks: list[Document], bm25_chunks: list[Document], k: int
    ) -> list[Document]:
        merged: list[Document] = []
        seen_chunk_ids: set[int] = set()
        for chunk in semantic_chunks + bm25_chunks:
            chunk_id = chunk.metadata.get("chunk_id")
            if not isinstance(chunk_id, int) or chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            merged.append(chunk)
            if len(merged) >= k:
                break
        return merged

    def build_prompt(self, query: str, chunks: list[Document], chat_history: list[ChatMessage] | None = None) -> list:
        context_blocks: list[str] = []
        for index, chunk in enumerate(chunks):
            chunk_id = f"chunk_{index + 1}"
            metadata = chunk.metadata
            context_blocks.append(
                "\n".join(
                    [
                        (
                            f"[{chunk_id}] File: {metadata.get('filename', 'unknown')} | "
                            f"Page: {metadata.get('page_number', metadata.get('page', '?'))} | "
                            f"Doc ID: {metadata.get('doc_id', 'unknown')} | "
                            f"Stored Chunk ID: {metadata.get('chunk_id', 'unknown')} | "
                            f"Retrieved By: {metadata.get('retrieval_source', 'semantic')}"
                        ),
                        chunk.page_content,
                        "---",
                    ]
                )
            )

        context_block = "\n".join(context_blocks)
        user_message = f"Context:\n{context_block}\n\nQuestion: {query}"
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        if chat_history:
            for msg in chat_history:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))
        messages.append(HumanMessage(content=user_message))
        return messages

    @traceable(name="stream_rag_response")
    async def stream_rag_response(
        self, query: str, doc_id: int | None = None, top_k: int = 5, chat_history: list[ChatMessage] | None = None
    ) -> AsyncGenerator[str, None]:
        if not chat_history:
            cached = self.history_repository.get_cached_query(query, doc_id)
            if cached:
                yield self._format_sse({
                    "type": "retrieval_done",
                    "retrieval_mode": "cache",
                    "search_query": query,
                    "planner_reason": "Exact match found in cache.",
                    "chunk_count": cached.chunk_count,
                    "latency_ms": 0,
                    "chunks": cached.sources,
                })
                words = cached.answer.split(" ")
                for i, word in enumerate(words):
                    yield self._format_sse({"type": "token", "text": word + (" " if i < len(words) - 1 else "")})
                    await asyncio.sleep(0.02)
                yield self._format_sse({"type": "citations", "data": cached.sources})
                yield self._format_sse({
                    "type": "final",
                    "answer": cached.answer,
                    "reasoning": cached.reasoning,
                    "sources": cached.sources,
                })
                yield "data: [DONE]\n\n"
                return

        chunks, retrieval_latency, plan = self.retrieve_chunks(
            query,
            doc_id=doc_id,
            k=top_k,
            chat_history=chat_history,
        )

        yield self._format_sse(
            {
                "type": "retrieval_done",
                "retrieval_mode": plan.mode,
                "search_query": plan.search_query,
                "planner_reason": plan.reason,
                "chunk_count": len(chunks),
                "latency_ms": round(retrieval_latency * 1000),
                "chunks": [
                    {
                        "chunk_id": chunk.metadata.get("chunk_id"),
                        "doc_id": chunk.metadata.get("doc_id"),
                        "filename": chunk.metadata.get("filename"),
                        "page_number": chunk.metadata.get(
                            "page_number", chunk.metadata.get("page")
                        ),
                        "chunk_index": chunk.metadata.get("chunk_index"),
                        "retrieval_source": chunk.metadata.get("retrieval_source"),
                    }
                    for chunk in chunks
                ],
            }
        )

        messages = self.build_prompt(query, chunks, chat_history)
        full_response = ""
        async for token in self.llm.astream(messages):
            text = token.content if isinstance(token.content, str) else ""
            if not text:
                continue
            full_response += text
            
            if len(text) > 30:
                words = text.split(" ")
                for i, word in enumerate(words):
                    yield self._format_sse({"type": "token", "text": word + (" " if i < len(words) - 1 else "")})
                    await asyncio.sleep(0.02)
            else:
                yield self._format_sse({"type": "token", "text": text})
                await asyncio.sleep(0.01)

        citations = self.parse_citations(full_response)
        parsed = self.parse_answer(full_response)
        yield self._format_sse({"type": "citations", "data": citations})
        yield self._format_sse(
            {
                "type": "final",
                "answer": parsed["answer"],
                "reasoning": parsed["reasoning"],
                "sources": citations,
            }
        )
        yield "data: [DONE]\n\n"

        matched_document_ids = list(
            dict.fromkeys(
                int(chunk.metadata["doc_id"])
                for chunk in chunks
                if chunk.metadata.get("doc_id") is not None
            )
        )
        matched_chunk_ids = [
            int(chunk.metadata["chunk_id"])
            for chunk in chunks
            if chunk.metadata.get("chunk_id") is not None
        ]
        asyncio.create_task(
            self.log_query(
                query=query,
                response=full_response,
                retrieval_latency=retrieval_latency,
                chunk_count=len(chunks),
                matched_document_ids=matched_document_ids,
                matched_chunk_ids=matched_chunk_ids,
            )
        )

    def parse_citations(self, response: str) -> list[dict[str, object]]:
        try:
            sources_match = re.search(
                r"<sources>(.*?)</sources>", response, re.DOTALL
            )
            if not sources_match:
                return []
            parsed = json.loads(sources_match.group(1).strip())
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, AttributeError):
            return []

    def parse_answer(self, response: str) -> dict[str, object]:
        def extract(tag: str) -> str:
            match = re.search(rf"<{tag}>(.*?)</{tag}>", response, re.DOTALL)
            return match.group(1).strip() if match else ""

        reasoning = extract("reasoning")
        answer = extract("answer")
        
        if not answer and "</reasoning>" in response:
            answer = response.split("</reasoning>")[-1].strip()
            answer = re.sub(r"<sources>.*?</sources>", "", answer, flags=re.DOTALL).strip()
        elif not answer and not reasoning:
            answer = response.strip()
            
        # If still no answer, maybe it's all in reasoning
        if not answer and reasoning:
            answer = reasoning
            reasoning = ""

        return {
            "reasoning": reasoning,
            "answer": answer,
            "sources": self.parse_citations(response),
            "raw": response,
        }

    async def log_query(
        self,
        *,
        query: str,
        response: str,
        retrieval_latency: float,
        chunk_count: int,
        matched_document_ids: list[int],
        matched_chunk_ids: list[int],
    ) -> None:
        parsed = self.parse_answer(response)
        connection = await AsyncConnection.connect(settings.database_url)
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO query_history (
                        query,
                        answer,
                        reasoning,
                        sources,
                        retrieval_latency_ms,
                        chunk_count,
                        matched_document_ids,
                        matched_chunk_ids,
                        raw_response,
                        created_at
                    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        query,
                        parsed["answer"],
                        parsed["reasoning"],
                        json.dumps(parsed["sources"]),
                        round(retrieval_latency * 1000),
                        chunk_count,
                        matched_document_ids,
                        matched_chunk_ids,
                        parsed["raw"],
                    ),
                )
            await connection.commit()
        finally:
            await connection.close()

    def list_history(self, limit: int) -> list[QueryHistoryRecord]:
        return self.history_repository.list_recent(limit)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9]+", text.lower())

    def _format_sse(self, payload: dict[str, object]) -> str:
        return f"data: {json.dumps(payload)}\n\n"
