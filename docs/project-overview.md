# GeoGebra AI Drawer v2 — Project Overview

## What This Repo Is

This repository is the **v2 worktree** of GeoGebra AI Drawer. It is split into:

- **Web UI**: `apps/web` (React + Vite)
- **API**: `apps/api` (Python + FastAPI + LangGraph)

The main user journey is: a user chats → the API streams events over **SSE** → the web UI applies **frontend tools** to a GeoGebra applet (interrupt/resume loop).

## Quickstart

- Start web + api: `./scripts/v2_dev.sh`
- Web: `http://127.0.0.1:3000/`
- API: `http://127.0.0.1:3002/healthz`

## Ports

- Web (Vite dev): `3000`
- API (FastAPI): `3002`

The web UI calls `/api/*` and relies on dev-time proxying to the API server.

## High-Level Architecture

- **Frontend** embeds GeoGebra via `https://www.geogebra.org/apps/deployggb.js`, keeps the canvas state, and runs tool calls locally (e.g., execute GeoGebra commands).
- **Backend** manages `thread_id` + `run_id`, runs a LangGraph graph, and streams events via SSE (including `interrupt` for frontend tools and `resume` handling).

## Repository Layout

- `apps/web/`: React UI
- `apps/api/`: FastAPI + LangGraph
- `scripts/`: dev/build/acceptance helpers
- `docs/`: product/spec docs + generated documentation (this folder)
