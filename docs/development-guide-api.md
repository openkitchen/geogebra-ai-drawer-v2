# Development Guide — API (`apps/api`)

## Start

From repo root (recommended):

- `./scripts/v2_dev.sh`

Or directly:

- `cd apps/api && uv run uvicorn app.main:app --reload --port 3002`

## Smoke / Acceptance

- `./scripts/v2_acceptance_api.sh`

## LLM Modes

- Default: stub path
- Enable real model via env vars (see `apps/api/README.md`)
