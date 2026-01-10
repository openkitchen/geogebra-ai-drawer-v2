<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1Ah3mjPlO2Hm1FqbbGHbzx2cuhZKDB4Wr

## v2 Quickstart (recommended)

This directory is the **v2 worktree**. The v2 app is split into:

- Web UI (React/Vite): `apps/web`
- API (Python/FastAPI + LangGraph): `apps/api`

### Start (web + api)

```bash
./scripts/v2_dev.sh
```

### Start API

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 3002
```

### Start Web UI

```bash
cd apps/web
npm install
npm run dev
```

Open: `http://127.0.0.1:3000/`

### Build (web + api)

```bash
./scripts/v2_build.sh
```

## Prerequisites

- **Node.js**: v16 or higher (for web UI and scripts)
- **Python**: v3.11+ (for API)
- **uv**: Package manager for Python (recommended) – install via `pip install uv` or `brew install uv`
- **npm**: Comes with Node.js

## Environment Setup

1. Copy `.env.example` to `.env.local`:
   ```bash
   cp .env.example .env.local
   ```

2. Edit `.env.local` with your API endpoints and configuration:
   - See `docs/env.example.md` for detailed variable descriptions

3. Optional: Verify configuration with:
   ```bash
   npm run doctor
   ```

### Ports

- **Client (Web UI)**: `http://localhost:3000` (Vite dev server)
- **API Server**: `http://localhost:3002` (FastAPI/LangGraph backend)

In development, the client proxy automatically forwards `/api/*` requests to the API server. You can override ports:

```bash
WEB_PORT=3001 API_PORT=3003 npm run dev
```

Or set in `.env.local`:
- `API_PROXY_PORT=3002` (only affects the proxy)

## Project Structure

```
.
├── apps/
│   ├── api/          # Python/FastAPI backend (LangGraph orchestration)
│   └── web/          # React/Vite frontend
├── docs/             # Documentation (design, spec, tasks, collaboration)
├── components/       # Shared UI components
├── prompts/          # LLM prompts and system instructions
├── scripts/          # Development and deployment scripts
├── server/           # Node.js development proxy server
└── skills/           # Agent skills and extensions
```

## Documentation

For more detailed information, see:

- **Getting Started**: `docs/README.md` (documentation index)
- **Architecture**: `docs/design/architecture.md`
- **Project Overview**: `docs/project-overview.md`
- **Development Guides**:
  - API: `apps/api/README.md`
  - Web UI: `apps/web/README.md`
- **Environment Variables**: `docs/env.example.md`

## Development Workflow

### Build the Project

```bash
./scripts/v2_build.sh
```

### Run Tests

```bash
# API tests
cd apps/api
python -m pytest

# Web UI tests (if configured)
cd apps/web
npm test
```

### Debugging

- API debug logs: Set `DEBUG=app.*` environment variable
- Web UI: Use browser DevTools or React DevTools extension

## Troubleshooting

**Port already in use:**
- Change ports via environment variables: `WEB_PORT=3001 API_PORT=3003 npm run dev`
- Or kill the existing process: `lsof -ti :3000 | xargs kill -9`

**API connection failed:**
- Verify API is running: `curl http://127.0.0.1:3002/healthz`
- Check `.env.local` API endpoint configuration
- Review API logs for errors

**Module import errors:**
- Clear cache: `rm -rf node_modules package-lock.json && npm install`
- For API: `rm -rf .venv && python -m venv .venv && source .venv/bin/activate && pip install -e .`

## Contributing

Please see `AGENTS.md` for contribution guidelines, commit conventions, and collaboration workflow.

## License

See LICENSE file for details.
