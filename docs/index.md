# Project Documentation Index

- **Type:** monorepo with 2 parts
- **Architecture:** Split frontend (React/Vite) + backend (FastAPI/LangGraph) with SSE streaming and interrupt/resume
- **Generated:** 2026-01-05T10:43:49.135924Z

## Quick Reference

### Web UI (`apps/web`)

- **Type:** web
- **Tech Stack:** React + Vite
- **Entry Point:** `apps/web/src/main.tsx`

### API (`apps/api`)

- **Type:** backend
- **Tech Stack:** Python + FastAPI + LangGraph
- **Entry Point:** `apps/api/app/main.py`

## Generated Documentation

- [Project Overview](./project-overview.md)
- [Architecture — Web UI](./architecture-web.md)
- [Architecture — API](./architecture-api.md)
- [Integration Architecture](./integration-architecture.md)
- [API Contracts — API](./api-contracts-api.md)
- [Data Models — API](./data-models-api.md)
- [Component Inventory — Web UI](./component-inventory-web.md)
- [Development Guide — Web UI](./development-guide-web.md)
- [Development Guide — API](./development-guide-api.md)
- [Source Tree Analysis](./source-tree-analysis.md)
- [Deployment / Runtime Guide](./deployment-guide.md)
- [Project Parts Metadata](./project-parts.json)

## Existing Hand-Written Docs

- [Repository README](./../README.md)
- [web README](./../apps/web/README.md)
- [api README](./../apps/api/README.md)
- [docs README](./README.md)

## Getting Started (Dev)

- Start everything: `./scripts/v2_dev.sh`
- Web: `http://127.0.0.1:3000/`
- API health: `http://127.0.0.1:3002/healthz`
