## Environment example (server-side)

The backend server loads configuration from:
- `.env.local` (preferred)
- `.env` (fallback)

### Minimal example (Moonshot)

```bash
API_PROXY_PORT=3002

# Put real keys as separate env vars (do not commit real keys):
MOONSHOT_API_KEY=YOUR_MOONSHOT_API_KEY

# Model routing (recommended: aliases + roles)
LLM_MODEL_ALIASES_JSON='[
  {
    "id": "ms-kimi-k2-thinking",
    "label": "Kimi K2 Thinking (Moonshot)",
    "provider": "openai-compatible",
    "baseURL": "https://api.moonshot.cn/v1",
    "apiKey": "${MOONSHOT_API_KEY}",
    "modelId": "kimi-k2-thinking"
  },
  {
    "id": "ms-moonshot-v1-8k",
    "label": "moonshot-v1-8k (Moonshot, fast/intent)",
    "provider": "openai-compatible",
    "baseURL": "https://api.moonshot.cn/v1",
    "apiKey": "${MOONSHOT_API_KEY}",
    "modelId": "moonshot-v1-8k"
  }
]'

LLM_ROLE_BINDINGS_JSON='{
  "main": "ms-kimi-k2-thinking",
  "repair": "ms-kimi-k2-thinking",
  "fast": "ms-moonshot-v1-8k",
  "fallback": "ms-moonshot-v1-8k"
}'

# v2 (Python API) model selection (reuse aliases + role bindings above)
V2_LLM_ROLE=main
# Explicit: intent classifier uses the fast role.
V2_LLM_INTENT_ROLE=fast
V2_LLM_TIMEOUT_S=20
V2_LLM_TEMPERATURE=0
```

### Optional: timeouts / fallbacks

```bash
LLM_TIMEOUT_MS=20000
```

### Optional: LangSmith tracing (recommended for RCA)

```bash
# Either set LANGCHAIN_* directly...
LANGCHAIN_TRACING_V2="true"
LANGCHAIN_API_KEY="YOUR_LANGSMITH_API_KEY"
LANGCHAIN_PROJECT="geogebra-ai-drawer-v2"
# LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"  # optional

# ...or use LANGSMITH_* (v2 will map to LANGCHAIN_* automatically)
# LANGSMITH_TRACING="true"
# LANGSMITH_API_KEY="YOUR_LANGSMITH_API_KEY"
# LANGSMITH_PROJECT="geogebra-ai-drawer-v2"
# LANGSMITH_ENDPOINT="https://api.smith.langchain.com"  # optional
```

### Notes
- **Do not commit real keys**.
- `provider` must be one of: `openai` | `google` | `openai-compatible`.
- `baseURL` is required for `openai-compatible` and optional for `openai`/`google`.
- Many OpenAI-compatible gateways expose a model list via `GET /v1/models`.
