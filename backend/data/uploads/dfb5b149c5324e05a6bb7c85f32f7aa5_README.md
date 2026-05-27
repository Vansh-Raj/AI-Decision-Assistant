# AI Decision Backend

Backend scaffold for an AI decision system with:

- recursive chunking via LangChain
- embeddings via OpenRouter using `openai/text-embedding-3-small`
- generation via OpenRouter using `openai/gpt-5-nano`
- chunk metadata in PostgreSQL
- vectors in Qdrant
- streaming RAG retrieval and answer generation with citations

## Endpoints

- `POST /api/upload`
- `POST /api/query` (`text/event-stream`)
- `GET /api/history`

## Environment

Create a local `.env` with your OpenRouter key:

```env
OPENROUTER_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=ai_decision_backend
```

The app defaults to:

- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `EMBEDDING_MODEL=openai/text-embedding-3-small`
- `CHAT_MODEL=openai/gpt-5-nano`
- `CHUNK_SIZE=1800`
- `CHUNK_OVERLAP=250`

Optional infrastructure variables:

```env
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5433/ai_decision
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/ai_decision
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=documents
```

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

## Start Everything

Use the project start script:

```bash
./start.sh
```

This will:

- start PostgreSQL with Docker Compose
- start Qdrant with Docker Compose
- create `venv` if needed
- install Python dependencies if needed
- launch the FastAPI app on `http://localhost:8000`

You can also start just the infrastructure with:

```bash
docker compose up -d postgres qdrant
```

## Storage model

`documents` stores file-level metadata.

`document_chunks` stores chunk metadata:

- `filename`
- `chunk_index`
- `page_number`
- `upload_timestamp`
- `doc_id`

Qdrant stores the embedding vector for each chunk, keyed by the Postgres chunk id, with mirrored payload metadata for retrieval.

## Retrieval behavior

`/api/query` uses:

- LLM-routed retrieval selection: `semantic`, `bm25`, or `hybrid`
- retrieval-query rewriting for typo correction and cleaner search intent
- MMR retrieval from Qdrant
- BM25 retrieval over chunk text stored in Postgres
- optional `doc_id` filtering
- contextual compression with `EmbeddingsFilter`
- XML-structured model output for reasoning, answer, and citations
- async query logging into Postgres for observability

## Good Starter Test Files

Use these first in Postman so uploads stay quick and easy to debug:

- a `1-2` page plain text project note around `300-800` words
- a short markdown meeting summary with headings and bullet points
- a compact CSV with `20-100` rows plus a few descriptive columns

Avoid testing first with:

- long research PDFs
- scanned PDFs
- image-heavy files
- complex academic templates with lots of formatting noise

## Notes

Current extraction supports UTF-8 text-like documents directly. For binary PDFs or DOCX files, the next step is to add dedicated parsers before chunking.

PDF uploads now use `pypdf` text extraction. Scanned PDFs or image-only PDFs still need OCR and may not extract usable text.
