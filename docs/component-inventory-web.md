# Component Inventory — Web UI

This inventory is a quick-scan list of the main React components and their purpose.

## Top-Level

- `App` (`src/App.tsx`) — chat + run orchestration + GeoGebra lifecycle
- `GeoGebraApplet` (`src/GeoGebraApplet.tsx`) — loads and embeds GeoGebra

## UI Components (`src/components/`)

- `ChatBubble` — renders a chat message
- `DebugDrawer` — dev tools (schema + LangGraph mermaid fetch)
- `WelcomeScreen` — first-time/empty state UI

## Utilities

- `streamSse` (`src/sse.ts`) — SSE stream reader
- `runFrontendTool` (`src/frontendTools.ts`) — frontend tool runner for interrupts
