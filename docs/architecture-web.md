# Architecture — Web UI (`apps/web`)

## Responsibilities

- Render chat UI and canvas UI
- Embed and control GeoGebra applet (GeoGebra Apps API)
- Call API endpoints (`/api/threads`, `/api/threads/:id/runs/stream`, `/resume`)
- Consume SSE stream and update UI incrementally
- Execute **frontend tools** on behalf of the backend (interrupt/resume)

## Key Modules

- `src/App.tsx`
  - Creates/keeps `threadId`
  - Sends user input
  - Consumes SSE events and updates chat timeline
  - Handles `interrupt` events by running `runFrontendTool(...)` then calling `/resume`

- `src/sse.ts`
  - SSE streaming helper + event parsing
  - Ensures the UI unblocks on `run_end` even if server keeps connection open

- `src/frontendTools.ts`
  - Implements the frontend-only tools (GeoGebra canvas operations)

- `src/GeoGebraApplet.tsx`
  - Loads `deployggb.js`
  - Injects `GGBApplet` into the DOM and exposes `GeoGebraAppletApi`
  - Uses `ResizeObserver` to keep the applet sized to its container

- `src/components/DebugDrawer.tsx`
  - Fetches `/api/schema/v2` and `/api/graph/v2/mermaid` for debugging

## Runtime Data Flow

1. User types a message
2. Web POSTs `/api/threads` (if needed)
3. Web POSTs `/api/threads/{thread_id}/runs/stream`
4. Web consumes SSE events (`token`, `tool_start`, `interrupt`, `final`, `run_end`, ...)
5. On `interrupt`:
   - Web runs the requested frontend tool
   - Web POSTs `/api/threads/{thread_id}/runs/{run_id}/resume` with tool result

## API Calls Observed (from code)

- `/api/threads/${effectiveThreadId}/runs/${runId}/resume`
- `/api/threads/${tid}/runs/stream`
