#!/usr/bin/env bash
set -euo pipefail

# Run v2 API (FastAPI + LangGraph) only.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${API_PORT:-3002}"

cd "$ROOT_DIR/apps/api"
exec uv run uvicorn app.main:app --reload --port "$API_PORT"

