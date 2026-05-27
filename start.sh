#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to start PostgreSQL and Qdrant."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to start the API."
  exit 1
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

if [ ! -f ".env" ]; then
  cat <<'EOF'
Missing .env file.
Create one with:
OPENROUTER_API_KEY=
EOF
  exit 1
fi

set -a
source .env
set +a

docker compose up -d postgres qdrant

if [ ! -f "venv/.deps-installed" ] || [ requirements.txt -nt venv/.deps-installed ]; then
  venv/bin/python -m pip install -r requirements.txt
  touch venv/.deps-installed
fi

cat <<'EOF'
Infrastructure started:
- PostgreSQL: postgresql://postgres:postgres@localhost:5433/ai_decision
- Qdrant: http://localhost:6333

If OPENROUTER_API_KEY is still empty, upload/query endpoints that need embeddings or generation will fail until you add it.
EOF

exec venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
