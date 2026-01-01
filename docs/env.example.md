## Environment example (server-side)

The backend server loads configuration from:
- `.env.local` (preferred)
- `.env` (fallback)

### Minimal example (VectorEngine)

```bash
API_PROXY_PORT=3002

# Put real keys as separate env vars (do not commit real keys):
VECTORENGINE_API_KEY=YOUR_VECTOR_ENGINE_KEY

# v1-style model routing (recommended: aliases + roles)
LLM_MODEL_ALIASES_JSON='[
  {
    "id": "ve-gpt-4.1-mini",
    "label": "GPT-4.1 Mini (VectorEngine)",
    "provider": "openai-compatible",
    "baseURL": "https://api.vectorengine.ai/v1",
    "apiKey": "${VECTORENGINE_API_KEY}",
    "modelId": "gpt-4.1-mini-2025-04-14"
  },
  {
    "id": "ve-o4-mini",
    "label": "o4-mini (VectorEngine)",
    "provider": "openai-compatible",
    "baseURL": "https://api.vectorengine.ai/v1",
    "apiKey": "${VECTORENGINE_API_KEY}",
    "modelId": "o4-mini-2025-04-16"
  },
  {
    "id": "ve-gemini-2.5-pro",
    "label": "Gemini 2.5 Pro (VectorEngine, OpenAI-compatible)",
    "provider": "openai-compatible",
    "baseURL": "https://api.vectorengine.ai/v1",
    "apiKey": "${VECTORENGINE_API_KEY}",
    "modelId": "gemini-2.5-pro"
  },
  {
    "id": "ve-gemini-3-pro-preview",
    "label": "Gemini 3 Pro Preview (VectorEngine, OpenAI-compatible)",
    "provider": "openai-compatible",
    "baseURL": "https://api.vectorengine.ai/v1",
    "apiKey": "${VECTORENGINE_API_KEY}",
    "modelId": "gemini-3-pro-preview"
  },
  {
    "id": "ve-gemini-flash",
    "label": "Gemini Flash (VectorEngine, OpenAI-compatible)",
    "provider": "openai-compatible",
    "baseURL": "https://api.vectorengine.ai/v1",
    "apiKey": "${VECTORENGINE_API_KEY}",
    "modelId": "gemini-flash-latest"
  }
]'

LLM_ROLE_BINDINGS_JSON='{
  "main": "ve-gpt-4.1-mini",
  "repair": "ve-gemini-2.5-pro",
  "fast": "ve-o4-mini",
  "gemini_main": "ve-gemini-3-pro-preview",
  "gemini_fast": "ve-gemini-flash"
}'

# v2 (Python API) model selection (reuse aliases + role bindings above)
V2_LLM_ROLE=main
V2_LLM_TIMEOUT_S=20
V2_LLM_TEMPERATURE=0
```

### Optional: timeouts / fallbacks

```bash
LLM_TIMEOUT_MS=20000
```

### Notes
- **Do not commit real keys**.
- `provider` must be one of: `openai` | `google` | `openai-compatible`.
- `baseURL` is required for `openai-compatible` and optional for `openai`/`google`.
- VectorEngine `modelId` list can be discovered via `GET /v1/models` (OpenAI-compatible).
