# Integration Architecture — Web ↔ API ↔ GeoGebra

## Main Integration Loop

1. Web UI creates a thread: `POST /api/threads`
2. Web UI starts a run: `POST /api/threads/{thread_id}/runs/stream`
3. API streams SSE events
4. When API needs a tool that must run in the browser, API emits `interrupt`
5. Web executes the tool against GeoGebra (Apps API) and calls `POST /resume`

## Transport

- Web ↔ API: HTTP + SSE
- Web ↔ GeoGebra: GeoGebra Apps API (loaded via `deployggb.js`)

## Ports (dev)

- Web: 3000
- API: 3002
