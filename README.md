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

- [backend/app/routes.py](/home/vansh/Documents/Dev/RAG%20Project/backend/app/routes.py:1) defines the API surface.
- [backend/app/services/document_service.py](/home/vansh/Documents/Dev/RAG%20Project/backend/app/services/document_service.py:1) handles file persistence, extraction, chunking, embedding, and vector upserts.
- [backend/app/rag/pipeline.py](/home/vansh/Documents/Dev/RAG%20Project/backend/app/rag/pipeline.py:1) handles retrieval planning, retrieval, prompt construction, streaming generation, and query logging.
- [backend/app/repositories.py](/home/vansh/Documents/Dev/RAG%20Project/backend/app/repositories.py:1) provides data access for documents, chunks, and query history.
- [backend/app/observability.py](/home/vansh/Documents/Dev/RAG%20Project/backend/app/observability.py:1) adds structured logging and request-scoped trace IDs.

### Frontend

- [frontend/src/App.tsx](/home/vansh/Documents/Dev/RAG%20Project/frontend/src/App.tsx:1) contains the single-page chat experience.
- [frontend/src/index.css](/home/vansh/Documents/Dev/RAG%20Project/frontend/src/index.css:1) provides the UI styling and responsive layout.
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

- The project favors readability and assignment coverage over deep modularity.
- The retrieval planner improves multi-turn behavior, but it adds an extra model call.
- Keeping relational data in PostgreSQL and vectors in Qdrant makes responsibilities clearer, but increases local setup complexity.
- The frontend is intentionally transparent about retrieval behavior, even if that exposes system internals that a consumer-facing product might hide.

## Testing And Verification

- There is an API-oriented test file in [backend/tests/test_api.py](/home/vansh/Documents/Dev/RAG%20Project/backend/tests/test_api.py:1).
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
