# Web UI (v2)

React/Vite UI for v2 (Python API + LangGraph).

## Dev

1) Start the v2 API (in another terminal):

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 3002
```

2) Start the web UI:

```bash
cd apps/web
npm install
npm run dev
```

Open: `http://127.0.0.1:3000/`
