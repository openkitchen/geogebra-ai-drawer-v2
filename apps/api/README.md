# API (v2)

Python FastAPI + LangGraph/LangChain runtime (v2).

## Dev

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
uvicorn app.main:app --reload --port 3002
```

## LLM (optional)

By default the v2 graph runs in **stub** mode (no real model calls).
To enable a real model (OpenAI / OpenAI-compatible), set:

```bash
export V2_LLM_API_KEY="..."
# Optional (OpenAI-compatible gateways):
export V2_LLM_BASE_URL="https://api.openai.com/v1"
export V2_LLM_MODEL="gpt-4o-mini"
export V2_LLM_TIMEOUT_S="20"
```

If `V2_LLM_API_KEY` is not set, the server will fall back to the stub path automatically.

Recommended for local dev: reuse v1 model routing config via `LLM_MODEL_ALIASES_JSON` + `LLM_ROLE_BINDINGS_JSON`
and optionally set `V2_LLM_ROLE` (default: `main`). Note: v2 currently supports only `provider=openai/openai-compatible`.

Alternatively, if you already have v1-style env config (`LLM_ENDPOINTS_JSON`), v2 will try to reuse it
when `V2_LLM_API_KEY/OPENAI_API_KEY` are not set (only `provider: openai` / `openai-compatible` are supported for now).
You can pick an endpoint via `V2_LLM_ENDPOINT_ID` (or `LLM_AUTO_PREFERRED_ENDPOINT_ID`).

Local dev convenience: v2 will also try to load `.env.local` from this worktree, and then a sibling v1 worktree
(`../geogebra-ai-drawer/.env.local`) if present. You can override the env file path via:

```bash
export V2_ENV_FILE="/absolute/path/to/.env.local"
```

## Smoke test

```bash
curl -sS http://127.0.0.1:3002/healthz
curl -sS -X POST http://127.0.0.1:3002/api/threads
```
