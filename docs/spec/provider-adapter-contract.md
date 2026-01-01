## Spec — Provider Adapter Contract（业务层一致性）

> 目的：让上层业务（UI / tool runner / prompt 系统）**完全不需要知道**“底层是 Gemini / Kimi / OpenAI / …”，也不需要写 provider-specific 的 if/else；所有差异都在 adapter 层被吸收，并且对外行为保持一致。

> 范围说明：本文件描述 **v1 `/api/chat` + ai-sdk** 的 provider adapter 统一契约。  
> v2（thread/run + SSE + interrupts）目标态见：`docs/spec/langgraph-orchestration.md`。

### 术语
- **业务层（Business layer）**：只关心 `/api/chat` 协议与 tool runner 闭环；不做任何 provider 分支。
- **适配层（Adapter layer）**：服务端 LLM Router（`server/index.mjs`）+ ai-sdk provider 实现；负责把不同 provider 的差异变成“统一契约 + 可解释的降级策略”。
- **Frontend tools**：需要前端执行的工具（`get_canvas_state` / `exec_geogebra_commands` / `eval_expression` 等），单一来源为 `toolRegistry.js`。

### 统一对外能力（必须）
适配层对业务层只暴露以下统一能力：
1) **统一协议**：无论使用哪家模型，`/api/chat` 只返回两种形态：`kind="tool_request"` 或 `kind="final"`（见 `chatProtocol.js`）。
2) **统一工具名单**：所有可暴露给模型的工具来自 `toolRegistry.js` 的 `getExposedToolNames()`；新增工具后，无需改 provider 分支即可被纳入 tools roster。
3) **统一工具闭环**：当模型需要前端能力时，必须通过 `kind="tool_request" → TOOL_RESULT → ... → kind="final"` 完成；业务层只按协议跑 tool runner。

### Adapter 层行为契约（必须）

#### A. Tool Policy（工具策略）
适配层必须为每次请求计算一个 `toolPolicy`：
- `optional`：允许 tool-calling；若 tool-calling 不可用/失败，可回退到 object/JSON 路径（用于提升可用性）。
- `required`：本次请求**必须**能调用 frontend tools（例如用户明确要求使用某个工具，或需要先探查画板）。

当前实现（`server/index.mjs`）：
- 若用户文本显式包含某个 tool 名（来自 `getExposedToolNames()`），则 `toolPolicy=required`。
- 若用户引用“已有画板”且尚未获得画板上下文，则 `toolPolicy=required`，并由 server-preflight 直接发起 `get_canvas_state`。

#### B. “工具必需品时禁止 fallback”（强约束）
当 `toolPolicy=required` 时：
1) **禁止 object fallback**：同一 provider 内不得从 `strategy=tool` 回退到 `strategy=object`（因为 object 路径不会把 tools 传给模型）。
2) **禁止跨 provider/模型 fallback**：无论是“换 provider”还是“换 modelId”，都不允许在同一次请求中静默切换；必须 fail fast 并把失败可观测地暴露出来（便于定位 provider/tool-calling 问题）。
3) **不得用 cache/local fallback 冒充成功**：cache 与本地兜底只允许在 `toolPolicy=optional` 时使用。
4) **失败也要保持协议一致**：当所有 provider 都失败时，仍返回 `kind="final"` + `commands: []` 的错误说明（而不是返回非协议 JSON），便于 UI 保持一致渲染/记录。

#### C. 可观测性（必须）
- 每次 `/api/chat` 响应必须包含 `reqId`；若请求带 `clientRunId`，必须回写到响应与 session log（见 `docs/spec/tool-runner.md`）。
- `debugTrace` 必须记录每个尝试（alias/endpoint + strategy）的 ok/fail、耗时与错误，供 DebugPanel 排障。
- 推荐额外记录 `role`（main/repair/intent）与“是否 UI 覆盖了默认模型”，避免排障时反复猜测“这次到底用的是哪一个 alias”。
- Legacy 兼容：若 `phase="repair"` 仍使用 endpoint registry 的小模型变体（如 `models.repair`），`debugTrace.modelId` / `usedModelId` 必须反映真实使用的 modelId。

### Provider 差异清单（允许存在，但必须被 adapter 吸收）
以下差异属于 provider/模型本身，允许存在；adapter 层必须把它们变成“可观测的失败 + 可解释的降级”，而不是让业务层分叉：
- **工具调用支持差异**：tool calling / toolChoice 支持度不同；有的只支持 `auto`。
- **结构化输出支持差异**：某些 OpenAI-compatible 网关不支持 responseFormat/structured outputs。
- **schema 严格度差异**：部分 provider 对 tool schema 更严格（避免 union/过度宽松 schema）。
- **限流/配额/超时**：如 Gemini quota/rate-limit、网络抖动等。

### 自测（建议最小集合）
1) `toolPolicy=required`：输入显式包含 `get_canvas_state`，期望 server 先走 `kind=tool_request(get_canvas_state)`，且不会走 object fallback。
2) `toolPolicy=required`：输入显式包含 `exec_geogebra_commands`，期望服务端只尝试 tool-calling；若 provider 不可用，应 fail fast，并在 DebugTrace/错误说明里可见失败原因。
3) `toolPolicy=optional`：普通“画一个圆”，允许 object fallback（可用性优先）。

> 相关文档：`docs/design/architecture.md`（结构图/时序图）、`docs/spec/model-routing.md`（路由/降级）、`docs/spec/tool-runner.md`（tool runner 协议）。
