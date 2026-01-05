# API Contracts — v2 API (`apps/api`)

Base URL (dev): `http://127.0.0.1:3002`

## Endpoints

- **GET** `/healthz` — handler `healthz`
- **GET** `/api/schema/v2` — handler `get_schema_v2`
- **GET** `/api/graph/v2/mermaid` — handler `get_langgraph_mermaid`
- **GET** `/api/graph/v2/mermaid.png` — handler `get_langgraph_mermaid_png`
- **POST** `/api/threads` — handler `create_thread`
- **GET** `/api/threads/{thread_id}/state` — handler `get_thread_state`
- **GET** `/api/threads/{thread_id}/state/history` — handler `get_thread_state_history`
- **POST** `/api/threads/{thread_id}/runs/stream` — handler `run_stream`
- **POST** `/api/threads/{thread_id}/runs/{run_id}/resume` — handler `resume_run`

## Streaming (`/runs/stream`)

- The client opens a run via `POST /api/threads/{thread_id}/runs/stream`.
- The response is **SSE** (Server-Sent Events).
- Each SSE message has an `event` name (e.g. `token`, `interrupt`, `final`, `run_end`).

### Interrupt/Resume

- When the backend needs a frontend tool, it emits an `interrupt` event with `tool_name`, `tool_call_id`, and `input`.
- The client executes the tool locally (on the GeoGebra applet) and resumes the run via:
  - `POST /api/threads/{thread_id}/runs/{run_id}/resume`

See `apps/api/app/protocol_v2.py` for the canonical schema.
