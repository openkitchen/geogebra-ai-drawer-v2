## Environment example (server-side)

The backend server loads configuration from:
- `.env.local` (preferred)
- `.env` (fallback)

### Minimal example

```bash
API_PROXY_PORT=3002

LLM_ENDPOINTS_JSON='[
  {
    "id": "kimi",
    "label": "Kimi",
    "provider": "openai-compatible",
    "baseURL": "https://api.moonshot.cn/v1",
    "apiKey": "${KIMI_API_KEY}",
    "models": {
      "main": "kimi-k2-thinking",
      "intent": "moonshot-v1-8k",
      "fallback": "moonshot-v1-8k"
    }
  },
  {
    "id": "gemini",
    "label": "Gemini",
    "provider": "google",
    "apiKey": "${GEMINI_API_KEY}",
    "models": {
      "main": "gemini-2.5-flash",
      "intent": "gemini-2.5-flash"
    }
  }
]'

# Put real keys as separate env vars:
KIMI_API_KEY=YOUR_KIMI_KEY
GEMINI_API_KEY=YOUR_GEMINI_KEY
```

### Optional: intent classifier (cheap/fast)

The server also exposes `/api/intent` for intent routing (to decide whether to attach canvas state/objects).
You can point it to a **small, fast, low-cost model** (selected by endpoint id):

```bash
INTENT_ENDPOINT_ID=kimi
INTENT_TIMEOUT_MS=2500
```

### Optional: timeouts / fallbacks

```bash
LLM_TIMEOUT_MS=20000
```

### Notes
- **Do not commit real keys**.
- `provider` must be one of: `openai` | `google` | `openai-compatible`.
- `baseURL` is required for `openai-compatible` and optional for `openai`/`google`.
