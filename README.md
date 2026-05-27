# AI Decision Assistant

An AI-assisted document Q&A application built for a take-home assignment. Users can upload PDFs or text files, ask questions against the uploaded content, and inspect streamed answers with citations and retrieval details.

## What This Repo Implements

- FastAPI backend for upload, query, history, document status, and answer evaluation APIs
- Document ingestion for text-based PDFs and UTF-8 text files
- Chunking with `RecursiveCharacterTextSplitter`
- Embeddings via OpenRouter-compatible `OpenAIEmbeddings`
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

## Demo Automation

This repo includes a small runner script for a repeatable demo:

```bash
python3 scripts/run_demo_scenarios.py
```

By default it uploads:

`/home/vansh/Documents/avoidingarmageddon_chapter.pdf`

It then:

1. Uploads the PDF to the local backend
2. Polls until ingestion is complete
3. Runs the test scenarios below in order
4. Writes a Markdown summary to `scratch/demo_scenarios_report.md`

This is useful for preparing a demo video or validating behavior after changes.

The runner supports multiple scenario sets. For the GAO report example:

```bash
python3 scripts/run_demo_scenarios.py --scenario-set gao_ai_risk
```

or explicitly:

```bash
python3 scripts/run_demo_scenarios.py --file /home/vansh/Documents/gao-25-107435.pdf
```

For browser-driven demo playback through the actual frontend UI, use:

```bash
cd frontend
npm run demo:browser
```

This browser runner:

1. Opens the Vite frontend in Chromium
2. Uploads `/home/vansh/Documents/avoidingarmageddon_chapter.pdf`
3. Waits for ingestion to finish
4. Types and submits the test scenarios through the chat UI
5. Optionally records a browser video to `frontend/demo-videos/`

It assumes the backend and frontend are already running locally.

Optional environment variables:

- `DEMO_SCENARIO_SET` to choose a scenario set such as `avoidingarmageddon` or `gao_ai_risk`
- `DEMO_FRONTEND_URL` to target a non-default frontend URL
- `DEMO_UPLOAD_FILE` to change the uploaded file
- `DEMO_PAUSE_MS` to slow down or speed up the pacing between steps
- `DEMO_TYPE_DELAY_MS` to change how quickly text is typed
- `DEMO_HEADLESS=1` to run without a visible browser
- `DEMO_RECORD_VIDEO=0` to disable Playwright's recorded video output

## Test Scenarios

These are the recommended demo and evaluation prompts for the uploaded `avoidingarmageddon_chapter.pdf` document.

### Group 1: Factual Retrieval

**Q1 - Direct fact**

Question:
`How many people died and were injured in the 26/11 Mumbai attacks?`

Expected:
164 dead and 300+ injured, ideally citing page 2. This is the baseline retrieval check.

**Q2 - Named entity detail**

Question:
`Who was David Coleman Headley and what was his role in the Mumbai attack?`

Expected:
A multi-chunk answer covering surveillance trips, name change, guilty plea, and ISI meetings across pages 6-7.

### Group 2: Reasoning & Inference

**Q3 - Motive inference**

Question:
`Why did Lashkar-e-Tayyiba choose Mumbai specifically as the target, rather than any other Indian city?`

Expected:
The answer should synthesize Mumbai as a financial capital, media center, Bollywood symbol, and high-value Western/Israeli target. This tests reasoning across pages 2-4 rather than direct extraction.

**Q4 - Strategic intent**

Question:
`What was al Qaeda's ultimate goal in the Mumbai operation, and how did it differ from LeT's goal?`

Expected:
The answer should distinguish LeT's peace-process disruption goal from al Qaeda's broader nuclear-war and counterterrorism-disruption objective.

### Group 3: Multi-Turn / Pronoun Resolution

**Q5 - Follow-up with pronoun**

Turn 1:
`What was the back channel between India and Pakistan?`

Turn 2:
`Why did it stall?`

Expected:
The second turn should resolve `it` to the India-Pakistan back channel peace process before retrieval.

**Q6 - Chained reasoning**

Turn 1:
`Who was Zaki Rehman Lakhvi?`

Turn 2:
`What was his relationship to the training of the attackers?`

Expected:
The follow-up should remain grounded on Lakhvi and connect him correctly to attacker training.

### Group 4: Grounding / Faithfulness

**Q7 - Not in context trap**

Question:
`What sentence did Zaki Rehman Lakhvi receive for his role in the Mumbai attacks?`

Expected:
The system should say it could not find sentencing information in the uploaded documents. This is the key hallucination-resistance check.

**Q8 - Partial context trap**

Question:
`What did Headley find when he visited the Chabad house?`

Expected:
The system should mention only what the document actually states and avoid inventing details about what he found inside.

### Group 5: Decision Support

**Q9 - Risk analysis**

Question:
`Based on this document, what are the key risks that a future Mumbai-style attack would pose to U.S. strategic interests?`

Expected:
The answer should synthesize NATO supply-line risk, nuclear escalation, economic disruption, and Afghanistan-related implications.

**Q10 - Comparative judgment**

Question:
`The document argues India showed restraint after 26/11. What evidence supports this, and what might have happened if India had responded militarily?`

Expected:
The answer should combine evidence of restraint with a grounded counterfactual about escalation, nuclear risk, and broader geopolitical fallout.

## Alternate Scenario Set: GAO AI Risk Assessments

The repo also includes a second scenario set for:

`/home/vansh/Documents/gao-25-107435.pdf`

To run it through the browser automation:

```bash
cd frontend
DEMO_SCENARIO_SET=gao_ai_risk DEMO_UPLOAD_FILE=/home/vansh/Documents/gao-25-107435.pdf npm run demo:browser
```

This set focuses on:

- factual retrieval from the GAO report
- understanding the six foundational risk-assessment activities
- diagnosing why the agency assessments were incomplete
- multi-turn follow-ups about Executive Order 14110 and CISA guidance
- grounding checks where the report intentionally withholds sector-specific detail
- decision-support style synthesis of what DHS should prioritize next
