# Architecture — API (`apps/api`)

## Responsibilities

- Provide a FastAPI HTTP surface for the web UI
- Manage **threads** and **runs** in memory (dev-friendly)
- Execute LangGraph graph steps
- Stream progress via **SSE**
- Support `interrupt` → `resume` for frontend tool execution

## Major Components

- `app/main.py`
  - FastAPI app + routes
  - In-memory stores: `_threads`, `_runs`
  - SSE stream implementation for runs
  - Resume endpoint to continue execution after a frontend tool completes

- `app/graph/`
  - Graph construction, nodes, and state

- `app/protocol_v2.py`
  - Pydantic models for the v2 protocol (events, tool payloads, canvas schema)

- `app/llm/`
  - LLM config + client
  - Defaults to **stub mode** (no real model calls) unless env enables it

## SSE Events

- `budget`
- `final`
- `interrupt`
- `node_end`
- `node_start`
- `run_end`
- `run_start`
- `token`
- `tool_end`
- `tool_start`
