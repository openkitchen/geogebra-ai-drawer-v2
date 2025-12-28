## Refactor-Arch 报告（v1）

日期：2025-12-27  
范围：`App.tsx`、`server/index.mjs`、`server/tools.js`、`prompts/`、`docs/`  
目标：在不引入并发复杂度的前提下，优先稳定性；同时把“通用工具调用（前端 tool runner + 多轮 HTTP）”作为未来可扩展主路径。

---

## 1) 目标方向（Future Requirements）

- **时间窗口**：下一阶段（1–2 个里程碑）
- **非协商项**
  - 默认不发送 `canvasState`（on-demand）
  - 暂不考虑并发（但要避免把未来并发彻底锁死）
  - 以稳定性为第一优先级（失败可恢复、无残留、可观测）
- **架构方向**
  - **Contracts-first**：`/api/chat` 的返回结构、toolCalls/toolResults、prompt contract 必须可验证、可演进
  - **Tool runner as a platform**：后端“提出工具请求”，前端执行并回传 `TOOL_RESULT`，循环至 `final`
  - **LLM-first + deterministic 兜底**：确定性代码只做画布卫生/安全/兜底，不做数学内容决策

---

## 2) 现状架构地图（As-Is）

### 入口
- Client：`index.tsx` / `App.tsx` + `components/*`
- Server：`server/index.mjs`（同时承载：路由、LLM 调度、prompt 拼装、缓存、日志、codex-cli 适配）

### 核心链路（chat 主路径）
1. `App.tsx` 组织 history / preferences / repair loop
2. `POST /api/chat`（`server/index.mjs`）选择 endpoint + strategy（tool vs object）并返回结果
3. 前端执行 GeoGebra commands；失败时 rollback + RUNTIME_FEEDBACK 再试

### 工具链路（tool runner，已实现）
1. 后端返回 `kind="tool_request"`（包含 `toolRequest.toolCalls`）
2. 前端执行工具并回传（`role:"tool"` + `meta.type:"tool_result"`）
3. 后端把 tool result 转为 `TOOL_RESULT:` 文本注入，再让模型继续到 `kind="final"`

### 关键契约
- 输出契约：`docs/spec/prompt-contract.md`
- 运行时修复闭环：`docs/spec/runtime-feedback-repair.md`
- 路由策略：`docs/spec/model-routing.md`
- 关键实现文件：`App.tsx`（≈1476 LOC），`server/index.mjs`（≈1841 LOC）

---

## 3) 发现（Findings）

### 3.1 架构不匹配点（evolution blockers）

1) **后端存在跨请求可变全局状态**
- 证据：`server/index.mjs` 曾使用 `GLOBAL_CANVAS_STATE`
- 风险：即使当前“不考虑并发”，全局可变状态也会让未来的并发/多 tab/多用户测试变得脆弱；也降低“稳定性优先”的可信度。

> 状态：已于 2025-12-28 迁移中移除（不再使用全局画布 state）。

2) **存在两套并行的“画布感知”机制**
- 证据：前端曾同时保留“内部 token/直传 `canvasState`”与“tool runner”两套路径
- 风险：行为分叉导致回归难、难定位；模型可能走到非预期路径（尤其在不同 provider 下）。

> 状态：已于 2025-12-28 迁移中收敛：删除内部 token/直传 `canvasState` 路径，统一 `tool_request` → `TOOL_RESULT`。

3) **通用 tool runner 协议仍偏隐式**
- 证据：后端用 `TOOL_RESULT:` 前缀把 tool result 注入为文本；前端用 `meta.type="tool_result"` 传递，但未形成强类型/版本化 schema
- 风险：协议升级成本高；tool 扩展时容易出现“字段名不一致/解析失败/模型误解”。

4) **`/api/chat` 与旧 `/api/ggb` 并存**
- 证据：`server/index.mjs` 曾同时暴露 `/api/chat`、`/api/ggb`
- 风险：逻辑漂移（例如 tool runner/回滚/观测只在一处），导致维护成本和线上行为差异。

> 状态：已于 2025-12-28 迁移中下线 `/api/ggb`，统一走 `/api/chat`。

### 3.2 代码结构问题（maintenance blockers）

1) **God files：`App.tsx`、`server/index.mjs`**
- 症状：单文件承担 UI + 编排 + 执行 + 观测（或路由 + prompt + provider 适配 + 缓存 + 日志 + schema）
- 影响：难以局部修改；任何需求都容易引入回归。

2) **契约与实现未收敛到单一“事实源”**
- 现状：前端 TS types、服务端 zod schema、prompt contract 文档三者可能不同步
- 影响：当扩展 `kind/tool_request/tool_result`、新增工具时，容易“写一处忘两处”。

---

## 4) 重构提案（Prioritized）

| ID | Priority | Title | Problem | Evidence | Recommendation | Options | Effort | Risk | DependsOn | Validation |
|---:|:--:|---|---|---|---|---|:--:|:--:|---|---|
| 015 | P0 | 版本化 `/api/chat` 协议与共享类型 | tool runner 协议隐式、前后端类型不一致 | `App.tsx`, `server/index.mjs`, `types.ts` | 引入 `ChatApiResponseV1`（kind/toolRequest/toolCalls/response），并在 server 端用 zod 校验输出 | A: 仅 TS type；B: TS+zod 双保险（推荐） | M | M | - | `npm run build` + 浏览器跑 4.1→4.4 自测 |
| 009 | P0 | 移除 `GLOBAL_CANVAS_STATE`（request-scoped） | 后端跨请求全局可变状态 | `server/index.mjs` | 把 tool context 变为 per-request（闭包/上下文对象），禁止 module-global state | A: 保留全局（不推荐）；B: request scope（推荐） | M | M | 015 | 并行打开两 tab 快速交替请求，确认无串线；build |
| 016 | P0 | 收敛并下线 `/api/ggb` | 两套 API 并存导致漂移 | `server/index.mjs` | 标记 `/api/ggb` deprecated → 迁移调用方 → 删除或转发到 `/api/chat` | A: 保留（不推荐）；B: 转发；C: 删除（最终） | S/M | L/M | 015 | 搜索调用点为 0；手动回归主路径 |
| 017 | P1 | 服务端模块化：LLM 路由/Prompt/Tool runner 解耦 | `server/index.mjs` 过载 | `server/index.mjs` | 拆分为 `server/llm/*`, `server/routes/*`, `server/prompts/*` 等 | A: 不拆；B: 小步拆（推荐） | L | M | 015,016 | build + 路由自测（/api/providers,/api/chat） |
| 018 | P1 | 前端分层：Chat 编排/Tool runner/GeoGebra 执行解耦 | `App.tsx` 过载 | `App.tsx` | 抽 `services/chatRunner.ts`, `services/toolRunner.ts`, `services/ggbExecutor.ts` | A: 不拆；B: 小步拆（推荐） | L | M | 015 | build + 浏览器主路径/自测用例 |
| 019 | P2 | 统一 overlay：`overlayText` vs `set_corner_text` | 两种方式做同一件事，模型行为不稳定 | `prompts/packs/base.md`, `server/tools.js` | 选定单一路径并文档化（建议保留 `overlayText` 为主，tool 作为可选） | A: 双路并存；B: 单路（推荐） | S | L | 015 | 手动验证角落文案更新 |

---

## 5) 需要你拍板的决策

1) **协议优先级**：是否把 `kind/tool_request/tool_result` 作为 `/api/chat` 的唯一主路径（并逐步移除旧 token/旧 API）？
2) **/api/ggb 去留**：是否接受“下线 /api/ggb，仅保留 /api/chat”？
3) **overlay 单一路径**：保留 `overlayText` 还是强制 `set_corner_text`（或两者都留但明确主次）？

---

## 6) 通过后执行计划（建议）

1) 先做 015（协议+类型收敛）→ 让后续重构可回归  
2) 同步做 009（去全局 state）→ 为未来并发/多 tab 铺路  
3) 做 016（收敛 API）→ 减少漂移与维护面  
4) 再做 017/018（模块化拆分）→ 降低变更风险、提高可维护性  
