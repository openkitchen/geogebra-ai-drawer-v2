# Web UI (v2)

React/Vite UI for v2 (Python API + LangGraph).

## Dev

1) Start the v2 API (in another terminal):

```bash
cd apps/api
API_PORT=3002 uv run uvicorn app.main:app --reload --port "$API_PORT"
```

2) Start the web UI:

```bash
cd apps/web
npm install
WEB_PORT=3000 API_PORT=3002 npm run dev
```

Notes:
- Default ports: Web `3000`, API `3002`.
- Override per instance via `WEB_PORT` / `API_PORT` (proxy follows `API_PORT`).

Open: `http://127.0.0.1:3000/`
