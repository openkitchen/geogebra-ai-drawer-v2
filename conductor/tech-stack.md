# Technology Stack: GeoGebra AI Drawer v2

## Frontend (Web)
- **Core:** React 19 (Functional Components, Hooks)
- **Language:** TypeScript (Strict mode)
- **Build Tool:** Vite
- **Key Libraries:**
  - GeoGebra Web API (for rendering and geometric logic)
  - Vercel AI SDK (for streaming responses)

## Backend (API)
- **Framework:** FastAPI (Asynchronous Python)
- **Language:** Python >= 3.11
- **Orchestration:** LangGraph (for complex AI agent workflows)
- **AI Integration:** LangChain, OpenAI, Google AI
- **Package Management:** UV

## Infrastructure & Testing
- **Monorepo Structure:** `apps/web` (UI) and `apps/api` (Server)
- **Testing:** Playwright for E2E and acceptance testing
- **Communication:** Vite proxying requests to FastAPI (default port 3002)
- **Environment Management:** Dotenv (.env files)
