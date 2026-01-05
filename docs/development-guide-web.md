# Development Guide — Web UI (`apps/web`)

## Start

From repo root (recommended):

- `./scripts/v2_dev.sh`

Or directly:

- `cd apps/web && npm install && WEB_PORT=3000 API_PORT=3002 npm run dev`

Open: `http://127.0.0.1:3000/`

## Key Workflow

- Chat input triggers `send()` in `src/App.tsx`.
- The API run uses SSE and may request a frontend tool via `interrupt`.
- Tool execution happens in `src/frontendTools.ts` and is resumed via `/resume`.

## Build

- `cd apps/web && npm run build`
