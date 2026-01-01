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

## Run Locally

**Prerequisites:**  Node.js


1. One-time setup (installs deps if needed + creates `.env.local` if missing):
   `npm run setup`
2. Configure endpoints in `.env.local` (server-side only):
   - Start from `.env.example` (or see `docs/env.example.md`)
3. Sanity-check your config (optional):
   `npm run doctor`
4. Run the app (client + server proxy):
   `npm run dev`

### Ports

- Client (Vite): `http://localhost:3000`
- Server (API proxy): `http://localhost:3002` (default)

The client calls `/api/*` which is proxied to the server in development.

You can override the server/proxy port with:

- `.env.local`: `API_PROXY_PORT=3002`
