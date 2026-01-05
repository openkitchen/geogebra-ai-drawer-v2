# Data Models — API (Quick Scan)

## Protocol Models (Pydantic)

The canonical v2 protocol models live in `apps/api/app/protocol_v2.py`, including:

- Canvas schema: `CanvasObjectSummary`, `GetCanvasStateOutput`, ...
- Run stream events: `RunStartEvent`, `TokenEvent`, `ToolStartEvent`, `InterruptEvent`, `FinalEvent`, ...
- Resume payload: `ToolResumePayload`

## Runtime State

In dev, the API keeps state in memory (no DB detected):

- Threads: `_threads` (keyed by `thread_id`)
- Runs: `_runs` (keyed by `run_id`)

Persistence layer / database migrations were not detected in this repository.
