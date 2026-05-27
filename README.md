# AI Decision Assistant

[![Watch the Demo Video](https://img.shields.io/badge/Video-Watch%20Demo-blue?style=for-the-badge)](https://www.youtube.com/watch?v=pxBIAaNvD50)

An AI-assisted document Q&A application built for a take-home assignment. Users can upload PDFs or text files, ask questions against the uploaded content, and inspect streamed answers with citations and retrieval details.

## What This Repo Implements

- FastAPI backend for upload, query, history, document status, and answer evaluation APIs
- Document ingestion for text-based PDFs and UTF-8 text files
- Chunking with `RecursiveCharacterTextSplitter`
- Embeddings via `openai/text-embedding-3-small`
- LLM Generation via `openai/gpt-5-nano`
- Vector storage in Qdrant
- Query history and document metadata in PostgreSQL
- RAG answering with semantic, BM25, and hybrid retrieval modes
- Streaming responses over Server-Sent Events
- React frontend with chat UI, document picker, reasoning panel, and citations
- Structured JSON logs for request, ingestion, retrieval, prompt, and generation events
- Optional LangSmith tracing if the relevant environment variables are configured

## Current Scope And Limits

This project is a working prototype, not a finished production deployment.

- Document processing uses FastAPI background tasks, not a separate worker queue.
- PDF extraction works for text-based PDFs. Scanned PDFs and OCR are not handled.
- BM25 retrieval is computed in application memory over stored chunks, not via PostgreSQL full-text search.
- Evaluation uses LLM-based scoring and depends on external model access.
- The system stores query history, but it does not yet include authentication, multi-tenant isolation, or admin tooling.

## Architecture

Conceptually the system looks like this:

`User -> React frontend -> FastAPI API -> RAG pipeline -> PostgreSQL + Qdrant -> LLM -> streamed response`

```mermaid
flowchart LR
    U[User]
    F[React Frontend<br/>Vite chat UI]
    API[FastAPI API<br/>upload query history evaluate]
    DS[Document Service<br/>extract chunk embed]
    RAG[RAG Pipeline<br/>plan retrieve generate]
    PG[(PostgreSQL<br/>documents chunks history)]
    QD[(Qdrant<br/>embeddings)]
    LLM[OpenRouter-compatible LLMs<br/>chat + embeddings]
    OBS[Structured Logs<br/>request retrieval generation]

    U --> F
    F -->|HTTP + SSE| API
    API --> DS
    API --> RAG
    DS --> PG
    DS --> QD
    DS --> LLM
    RAG --> PG
    RAG --> QD
    RAG --> LLM
    API -.-> OBS
    DS -.-> OBS
    RAG -.-> OBS
```

### Backend

- [backend/app/routes.py](backend/app/routes.py) defines the API surface.
- [backend/app/services/document_service.py](backend/app/services/document_service.py) handles file persistence, extraction, chunking, embedding, and vector upserts.
- [backend/app/rag/pipeline.py](backend/app/rag/pipeline.py) handles retrieval planning, retrieval, prompt construction, streaming generation, and query logging.
- [backend/app/repositories.py](backend/app/repositories.py) provides data access for documents, chunks, and query history.
- [backend/app/observability.py](backend/app/observability.py) adds structured logging and request-scoped trace IDs.

### Frontend

- [frontend/src/App.tsx](frontend/src/App.tsx) contains the single-page chat experience.
- [frontend/src/index.css](frontend/src/index.css) provides the UI styling and responsive layout.
- The frontend consumes `/api/query` as an SSE stream and updates the last assistant message incrementally.

## API Summary

- `POST /api/upload`
  Upload a PDF or text file. Returns a document id and initial status.

- `GET /api/documents/{doc_id}/status`
  Returns the ingestion status and current chunk count for one document.

- `POST /api/query`
  Starts a streamed RAG response. The response uses `text/event-stream`.

- `GET /api/history`
  Returns recent query history from PostgreSQL.

- `POST /api/evaluate`
  Runs an LLM-based grading pass over an answer using relevance, faithfulness, and groundedness criteria.

## Retrieval And Answering Flow

1. A file is uploaded and stored on disk.
2. The backend extracts text, splits it into chunks, stores chunk rows in PostgreSQL, embeds the chunks, and upserts vectors into Qdrant.
3. When a question arrives, the pipeline asks the model to choose a retrieval mode and rewrite the query when helpful.
4. The system runs semantic retrieval, BM25 retrieval, or both depending on that plan.
5. Retrieved chunks are assembled into a constrained prompt.
6. The model streams back XML-like output containing reasoning, answer text, and sources.
7. The backend parses that output, emits citations to the UI, and saves the interaction to query history.

## Observability

The repo now includes code-level observability rather than only documentation claims.

- HTTP middleware logs request start, completion, failure, status code, latency, and `request_id`
- Upload logs capture file metadata and ingestion lifecycle events
- RAG logs capture retrieval mode selection, chunk counts, latency, prompt previews, cache hits, and generation timing
- Evaluation logs capture scoring latency and outputs
- Query history persists retrieved chunk ids, matched documents, latency, and raw model output

If LangSmith environment variables are configured, the `@traceable` decorators in the RAG pipeline add extra tracing on top of the structured app logs.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker and Docker Compose

### Environment

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_key_here
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5433/ai_decision
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/ai_decision
QDRANT_URL=http://localhost:6333
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here
LANGCHAIN_PROJECT=ai_decision_backend
```

Only `OPENROUTER_API_KEY` is strictly required for model calls. LangSmith settings are optional.

### Run The Backend

```bash
./start.sh
```

This script starts PostgreSQL and Qdrant through Docker, creates a virtual environment if needed, installs Python dependencies, and launches the FastAPI app.

### Run The Frontend

```bash
cd frontend
./start.sh
```

## Tradeoffs

### 1. Chunking: RecursiveCharacterTextSplitter over SemanticChunker

**Decision:** Fixed-size chunking with `RecursiveCharacterTextSplitter` (500 tokens, 50-token overlap).

**Why:** Semantic chunking produces more meaningful boundaries by splitting on embedding similarity drops, but it requires an embedding call per sentence during ingestion — adding 2–4 seconds of overhead per document and significantly increasing API cost. For a prototype handling moderately structured documents like government reports and PDFs, paragraph-aware fixed chunking produces retrieval quality close enough to semantic chunking to justify the simpler, faster approach.

**The cost:** Chunks occasionally split mid-paragraph or mid-table, which degrades retrieval precision on highly structured documents. The 50-token overlap partially mitigates boundary cuts.

**What a production system would do:** Semantic chunking for general documents, with a document-type router that switches to layout-aware parsing (e.g. `unstructured.io`) for PDFs with tables and headers, and a hard 400-token max to prevent runaway chunk sizes.

---

### 2. Retrieval Planner: Extra LLM Call vs. Naive Vector Search

**Decision:** A lightweight LLM call rewrites the user's query and selects a retrieval mode (semantic, BM25, or hybrid) before searching.

**Why:** Naive vector search fails silently on follow-up questions. A query like "Why did that fail?" has no dense semantic signal without its context. The planner resolves pronouns, adds missing subject terms, and routes keyword-heavy queries (legislation names, IDs, dates) to BM25 where cosine similarity performs poorly. This directly improves AI Correctness, which carries the most weight in the evaluation criteria.

**The cost:** An extra model call adds approximately 300–500ms of latency per query. With the current model configuration this contributes to total pipeline times of 40–57 seconds (measured via LangSmith traces), which is above acceptable production thresholds of under 8 seconds.

**Known latency issue:** The current p95 total pipeline latency is ~50 seconds. The primary driver is oversized context windows — prompt token counts average 8,000–12,000 tokens, which delays time-to-first-token significantly. The fix is reducing `k` from its current value to 4–5 chunks and capping chunk size at 400 tokens. A secondary optimization is routing the planner call to `gpt-4o-mini` while reserving the larger model only for final answer generation. These changes are expected to bring total latency to under 10 seconds and TTFT under 1.5 seconds.

---

### 3. BM25 in Application Memory vs. PostgreSQL Full-Text Search

**Decision:** BM25 is computed in-process over stored chunk text at query time.

**Why:** PostgreSQL full-text search with `tsvector` and `GIN` indexes requires schema migration, index maintenance, and a more complex query layer. For a prototype with documents in the hundreds, in-memory BM25 via `rank_bm25` is accurate, zero-infrastructure, and keeps the retrieval logic co-located with the rest of the pipeline.

**The cost:** In-memory BM25 does not scale. At several thousand chunks the index rebuild per query becomes measurable, and the entire chunk corpus must be loaded into memory on startup. There is also no persistence — the BM25 index is rebuilt from PostgreSQL rows each time the service restarts.

**What a production system would do:** Move to PostgreSQL full-text search for the BM25 leg of hybrid retrieval. This keeps retrieval in the database layer, removes the in-memory overhead, and gives persistent indexes that survive restarts. Alternatively, Qdrant's sparse vector support (via SPLADE or BM25 sparse embeddings) enables true hybrid search within a single vector query.

---

### 4. Dual Database: PostgreSQL + Qdrant vs. Single Store

**Decision:** Chunk text, document metadata, and query history live in PostgreSQL. Dense embeddings live in Qdrant.

**Why:** Qdrant is optimized for approximate nearest-neighbor search on high-dimensional vectors. Storing embeddings there and relational data in PostgreSQL keeps each system doing what it is best at. PostgreSQL provides ACID guarantees for history and metadata. Qdrant provides fast ANN search with filtering. Mixing concerns — for example, storing embeddings as `pgvector` columns in PostgreSQL — trades query performance for reduced operational complexity.

**The cost:** Running two databases locally increases setup friction. The `docker-compose.yml` handles this, but it is more moving parts than a single-store solution. Keeping chunk text in both PostgreSQL (for BM25 and history) and implicitly available via Qdrant metadata also creates a mild duplication.

**What a production system would do:** The same dual-store approach, but with connection pooling (PgBouncer for PostgreSQL, persistent Qdrant client with retry logic) and a caching layer (Redis) in front of repeated identical queries.

---

### 5. Asynchronous Ingestion: Background Tasks vs. Synchronous Upload

**Decision:** File parsing, chunking, embedding, and vector upserts happen in a FastAPI `BackgroundTask` after the upload endpoint returns.

**Why:** Embedding a 20-page PDF involves 30–60 API calls to the embeddings endpoint and takes 3–8 seconds. Blocking the upload HTTP response for that duration produces a poor user experience and risks client-side timeouts. Returning immediately with a `doc_id` and a status of `processing` lets the UI poll `/api/documents/{doc_id}/status` and show progress without blocking.

**The cost:** Background tasks in FastAPI share the same process and event loop as the API. A slow ingestion job under load can starve request handlers. There is also no retry mechanism — if the embedding API call fails mid-ingestion, the document is left in a `processing` state with no automatic recovery.

**What a production system would do:** Move ingestion to a proper task queue (Celery with Redis, or Dramatiq) running in a separate worker process. This gives independent scaling, retries with exponential backoff, dead-letter queues for failed jobs, and zero interference with API latency.

---

### 6. Structured XML Output vs. JSON Function Calling

**Decision:** The LLM is prompted to return structured XML tags (`<reasoning>`, `<answer>`, `<sources>`) which are parsed with regex on the backend.

**Why:** OpenAI function calling and structured output modes constrain the model's response format reliably, but they prevent the model from streaming token-by-token in a way that allows the UI to display partial reasoning as it arrives. XML tags in a streamed response allow the frontend to detect when the `<answer>` block begins and start rendering it immediately, while the `<reasoning>` block streams into a collapsible panel separately.

**The cost:** Regex-based XML parsing is fragile. If the model omits a closing tag or wraps the output in markdown fences, the parser falls back to returning the raw response with no citations. This happens occasionally with shorter or ambiguous queries.

**What a production system would do:** Use OpenAI's structured output mode for non-streaming evaluation and history storage, and keep the XML streaming approach only for the live chat path. A more robust parser using `lxml` or a state machine over the token stream would replace the regex fallback.

---

### Summary Table

| Decision | Chosen Approach | Main Tradeoff |
|---|---|---|
| Chunking | Fixed-size (500 tokens) | Simpler and faster ingestion; occasional boundary cuts hurt precision |
| Query rewriting | LLM planner call | Better multi-turn accuracy; adds ~400ms latency per query |
| BM25 | In-memory at query time | Zero infrastructure; does not scale past ~5,000 chunks |
| Storage | PostgreSQL + Qdrant | Clear separation of concerns; two databases to run locally |
| Ingestion | FastAPI BackgroundTask | Non-blocking uploads; no retry or isolated worker scaling |
| Output format | Streaming XML tags | Enables partial rendering; fragile regex parsing as fallback |

## Testing And Verification

- There is an API-oriented test file in [backend/tests/test_api.py](backend/tests/test_api.py).
- In this workspace, test execution still depends on resolving existing dependency/import issues outside the README changes.
- Frontend validation can be done with `npm run build` inside `frontend`.

## Test Scenarios

These are the recommended demo and evaluation prompts for the uploaded `gao-25-107435.pdf` document.

### Group 1: Factual Retrieval

**Q1 - Report identification**

Question:
`What is the main conclusion of GAO-25-107435?`

Expected:
DHS needs to improve AI risk assessment guidance for critical infrastructure sectors because the initial assessments did not fully address key risk activities.

**Q2 - Deadline detail**

Question:
`By when were the sector risk management agencies required to submit their initial AI risk assessments to DHS?`

Expected:
By January 29, 2024, within 90 days of Executive Order 14110.

### Group 2: Framework Comprehension

**Q3 - Six activities**

Question:
`What six activities does GAO say are foundational for effective AI risk assessment and mitigation in critical infrastructure sectors?`

Expected:
Should list the six activities: methodology, AI uses, potential risks, level of risk, mitigation strategies, and mapping mitigations to risks.

**Q4 - Assessment gaps**

Question:
`Which two risk assessment activities did none of the 17 sector assessments fully address?`

Expected:
Evaluating the level of risk and fully identifying potential risks including likelihood of occurrence.

### Group 3: Reasoning & Diagnosis

**Q5 - Why mapping failed**

Question:
`Why did many agencies fail to map mitigation strategies to risks in their AI sector assessments?`

Expected:
Because they had not fully evaluated the level of risk, which made it difficult to map mitigations to specific risks.

**Q6 - Root causes**

Question:
`What reasons does the report give for the agencies' mixed progress on the AI risk assessments?`

Expected:
Should synthesize the short 90-day timeline, the evolving nature of AI, and incomplete DHS guidance.

### Group 4: Multi-Turn / Pronoun Resolution

**Q7 - Follow-up on executive order**

Turn 1:
`What did Executive Order 14110 require the sector risk management agencies to do?`

Turn 2:
`Why was that deadline difficult for them to meet?`

Expected:
The follow-up should resolve the deadline reference and explain the 90-day challenge.

**Q8 - Follow-up on guidance**

Turn 1:
`What improvements did CISA make to the AI risk assessment template in 2024?`

Turn 2:
`What key gap still remained in it?`

Expected:
The second turn should stay grounded on the updated template and note that likelihood of occurrence and full level-of-risk evaluation still were not fully addressed.

### Group 5: Grounding / Faithfulness

**Q9 - Not in context trap**

Question:
`Which specific critical infrastructure sector had the strongest AI risk assessment according to GAO?`

Expected:
The report explicitly avoids identifying specific sectors for sensitive reasons, so the answer should say it cannot determine that from the uploaded document.

### Group 6: Decision Support

**Q10 - Recommendation synthesis**

Question:
`If you were advising DHS based only on this report, what should it prioritize before the January 2025 assessment cycle and why?`

Expected:
Should synthesize GAO's recommendation to quickly update and share guidance and templates, especially around likelihood of occurrence and evaluating level of risk.