## Spec — Model Routing (Configurable order; Kimi-first by default)

### 目标
提升可用性与稳定性：Auto 模式内部优先 Kimi，失败时自动降级，关键教学场景有本地兜底/缓存。

### 路由策略
- 前端默认选项：`auto`。
- 服务端 Auto 顺序：默认 `kimi` 优先，其次其他已配置模型；可通过环境变量调整优先级与顺序：
  - `LLM_AUTO_PREFERRED_ENDPOINT_ID`：Auto 模式首选 endpoint（默认 `kimi`）。
  - `LLM_AUTO_ORDER`：Auto 模式完整顺序（逗号分隔），例如 `packy-minimax,packy-glm47,kimi,gemini`。
- 显式选定模型时：默认仅在该模型失败后回落到 `kimi`；可通过环境变量调整：
  - `LLM_EXPLICIT_FALLBACK_ORDER`：显式选择某 endpoint 后的 fallback 链（逗号分隔，默认 `kimi`）。
  - `LLM_ALLOW_ALL_FALLBACK=true`：在 fallback 链后继续尝试其它剩余 endpoint（全量 fallback）。

### 失败与兜底
- 多 provider 尝试失败后：
  - 先查内存缓存（同一用户 prompt 的最近成功结果）。
  - 再用场景化本地兜底（如 triangle-angle-sum）。
  - 最后向用户报错。

### 结构化输出兼容（重要）
我们的 `/api/chat` 需要模型稳定返回可解析的 `{explanation, commands}` JSON。部分 OpenAI-compatible 网关/模型（例如 GLM/Kimi）可能不支持 AI SDK 的 `responseFormat/structured outputs`，导致 “could not parse the response”。

- 默认策略：对 `provider: "openai-compatible"` 优先尝试 **tool-calling**（`LLM_COMPAT_PREFER_TOOL_CALLING=true`）。
- 若该 provider 不支持强制 `toolChoice`（例如仅允许 `tool_choice="auto"`），服务端会自动重试一次。
- 若 tool-calling 仍失败，再回退到普通 JSON 解析路径；只有在同一 endpoint 的策略都失败后才会进入 fallback chain（下一 endpoint）。

### 可观测性
- 每次响应带上 `usedEndpointId` 供前端/Debug 展示。
- 每次响应带上 `debugTrace`（每个 endpoint 的 ok/fail、耗时、错误、tokens），用于 Debug 展示与排障。
- 可选：`LLM_LOG_CONNECTION_INFO=true` 打印每次尝试的连接信息（不含密钥）。

### Codex CLI-only Provider（本地开发）
某些网关会限制“只能通过官方 Codex CLI 访问”。这类 endpoint 可以配置为 `provider: "codex-cli"`：

- 服务端会在本机 spawn `codex exec` 来发起请求（而不是直接 HTTP 调用网关）。
- 为避免不同浏览器 tab 串线，客户端会发送 `codexTabId`，服务端按 tab 隔离 `CODEX_HOME`，并优先使用 `codex exec resume --last` 续写上下文。
- 为加速启动，服务端会通过 `-c mcp_servers={}` 关闭 MCP。仅建议用于本机开发/调试环境。

### Kimi 小模型的使用边界
- 主对话 `/api/chat` 默认不会把小模型当作真实回答模型；如需允许 Kimi 在 chat 内部做“快 fallback”，必须显式设置：`KIMI_ALLOW_CHAT_FALLBACK_MODEL=true`。
