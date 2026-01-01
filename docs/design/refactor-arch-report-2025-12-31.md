## Refactor-Arch 报告（v2）

日期：2025-12-31  
范围：`apps/api/app/*`、`apps/web/src/*`、`docs/spec/langgraph-orchestration.md`、`docs/collaboration/*`（并记录 v1 代码遗留对 v2 的影响）  
目标：以 **Contracts-first + Tool-first + Child-first UX** 为硬约束，识别阻塞演进/维护的点，产出可直接进入看板的重构任务（本次不改代码）。

---

## 1) Future Requirements（非协商项）

> 来源：`docs/design/overview.md`、`docs/design/decisions.md`、`docs/spec/langgraph-orchestration.md`、`docs/spec/runtime-feedback-repair.md`、`docs/collaboration/decision-log.md`。

- **教学可读性优先**：图要像教材；关键点/关系清晰，解释短句分步，避免噪音（Child-first UX）。  
- **稳定性/可恢复**：失败必须无残留（Rollback-first），同输入在不同时间/模型下结果“足够相似、可回归”。  
- **LLM-first + deterministic 兜底边界**：确定性代码只做画布卫生/安全兜底，不替 LLM 做数学内容决策。  
- **Tool-first / Canvas-aware**：模型不能“猜”画布，获取画布状态/测量必须经工具闭环。  
- **v2 技术骨架**：LangGraph threads/checkpoints + interrupts/resume + streaming（SSE）；POC 阶段不引入并发复杂度，但协议/状态不要把未来并发彻底锁死。  
- **Contracts-first**：协议与 schema 可验证、可演进，并能作为前后端对齐的事实源（例如 `protocol_version` + schema endpoint）。

---

## 2) As-Is 架构地图（v2）

### 2.1 入口与组件
- **Web UI（v2）**：`apps/web/src/main.tsx` → `apps/web/src/App.tsx`  
  - 负责 SSE 消费（`apps/web/src/sse.ts`）、interrupt→执行前端工具（`apps/web/src/frontendTools.ts`）→ `/resume` 回填。  
  - GeoGebra 嵌入：`apps/web/src/GeoGebraApplet.tsx`；画布只读检查：`apps/web/src/CanvasInspector.tsx`。
- **API（v2 / Python）**：`apps/api/app/main.py`  
  - 端点：`POST /api/threads`、`POST /runs/stream`（SSE）、`POST /resume`（SSE）、`GET /api/schema/v2`、`GET /state`、`GET /state/history`、`GET /healthz`。  
  - 运行时：LangGraph graph（`apps/api/app/runtime_graph.py`）+ 简化的 LLM 决策器（`apps/api/app/llm_decider.py`）。  
  - 协议 schema：`apps/api/app/protocol_v2.py`；调试 trace：`apps/api/app/debug_trace.py`（`logs/v2/run-<run_id>.jsonl`）。
- **v1 遗留面**：repo root 仍保留 v1 前端/Node server（如 `App.tsx`、`server/index.mjs`、root `package.json`），并且 `docs/design/architecture.md`/`docs/tasks/*` 仍以 v1 为主（与 v2 目标态存在偏差）。

### 2.2 主链路（thread/run + SSE + interrupts/resume）
1. UI 创建 thread：`POST /api/threads`（`apps/web/src/App.tsx` → `apps/api/app/main.py`）。  
2. UI 发起一次 run：`POST /api/threads/{thread_id}/runs/stream`，消费 SSE `RunStreamEvent`（`apps/web/src/sse.ts`）。  
3. 后端运行 LangGraph：`graph.stream(...)`（`apps/api/app/runtime_graph.py`）；需要浏览器能力时 `interrupt({tool_name, tool_call_id, input})`。  
4. UI 收到 `interrupt`：执行对应前端工具（`runFrontendTool` / `apps/web/src/frontendTools.ts`），并缓存 `tool_call_id` 以去重执行。  
5. UI 回填：`POST /api/threads/{thread_id}/runs/{run_id}/resume`，后端严格校验 `tool_call_id/tool_name`（409 expected/got）并继续 `graph.stream(Command(resume=...))`。  
6. 直到后端输出 `final` + `run_end`。

### 2.3 关键契约与事实源
- 协议版本与 schema：`apps/api/app/protocol_v2.py` + `GET /api/schema/v2`（v2 的对齐锚点）。  
- v2 目标态规格：`docs/spec/langgraph-orchestration.md`（包含事件流、interrupt 语义、幂等约束等）。  

---

## 3) 发现（Findings）

### 3.1 Evolution blockers（与未来需求不匹配）

1) **v1/v2 并存但“默认入口/文档事实源”不一致**
- 证据：root `README.md`/root `package.json` 仍指向 v1 Node；`docs/design/architecture.md`、`docs/tasks/*` 仍主要描述 v1；同时 v2 已在 `apps/api`/`apps/web` 落地。  
- 风险：新需求容易误落在 v1；同名概念（tool runner/repair loop/协议）出现两套实现与两套文档，回归与协作成本陡增。  
- 方向：明确 v2 为默认（入口、README、Docs Index、Tasks），v1 只作为 legacy 参考（显式标注/迁移计划），避免“默默漂移”。

2) **协议/类型在 Python 与 TS 之间手写双份，漂移风险高**
- 证据：`apps/api/app/protocol_v2.py`（Pydantic schema）与 `apps/web/src/sse.ts`（手写 `RunStreamEvent` union）需要人工同步。  
- 风险：新增事件字段或改名时，UI 可能“静默丢事件/渲染异常”；而这正是 v2 的核心价值（Streaming + Observability）。  
- 方向：把 `GET /api/schema/v2` 作为事实源，生成/校验 TS types（或做 schema→type snapshot + CI diff），减少人为同步点。

3) **工具名单与工具 schema 没有单一“可执行事实源”**
- 证据：后端允许工具列表在多处出现：`apps/api/app/llm_decider.py` 的 `ALLOWED_TOOL_NAMES`、`apps/api/app/runtime_graph.py` 的分支逻辑、`apps/api/app/protocol_v2.py` 的工具 input/output schema；前端则在 `apps/web/src/frontendTools.ts` 内自行维护实现。  
- 风险：新增工具或调整输入字段时，容易出现“后端会请求但前端没实现/前端实现了但后端永远不会请求/Schema 与实际输出不一致”。  
- 方向：以协议 schema 输出“supported_tools + per-tool schema”，前端在收到 `interrupt` 时做严格校验并 fail fast；后端 LLM 决策器也只从同一 registry 读取可用工具名单。

4) **运行态状态与计数存在“双写”，长期会变成排障负担**
- 证据：`apps/api/app/main.py` 的 `RunState(tool_calls_used/model_calls_used/pending_tool)` 与 LangGraph state（`apps/api/app/runtime_graph.py` 的 `GraphState.tool_calls_used/tool_results/...`）同时维护。  
- 风险：未来加入更多事件/预算/策略时，“UI 看到的 budget/plan”与“Graph 真正决策用的 state”可能不一致，导致 RCA 困难。  
- 方向：明确 source-of-truth：优先以 GraphState 为准；API 层尽量只读 snapshot 并负责映射成 SSE 事件（而不是再维护一套平行状态机）。

### 3.2 Maintenance blockers（结构与可维护性）

1) **God files / 低内聚高耦合开始出现**
- 证据：`apps/web/src/App.tsx` 同时承担 UI、SSE 消费、interrupt-resume loop、timeline 渲染、schema viewer；`apps/api/app/main.py` 同时承担存储、协议、SSE、resume 幂等/409、日志。  
- 风险：功能扩展（更多事件、更多工具、更多节点）时，改动面过大，回归概率上升。  
- 方向：小步拆分：把 run loop / timeline renderer / tool runner（前端）与 run manager / SSE emitter / storage adapter（后端）抽到独立模块。

2) **文档陈旧导致“规范 → 实现”链路断裂**
- 证据：`apps/web/README.md` 仍写 scaffold-only，但实际已可运行；`docs/design/architecture.md` 与 `docs/tasks/*` 仍以 v1 为主；`docs/README.md` 同时索引 v1/v2 文档但缺少明确“默认路径”。  
- 风险：协作沟通成本增加，尤其在“v2 允许破坏兼容”的前提下，文档若不及时标记会制造隐形冲突。  
- 方向：把“哪些是 v2、哪些是 v1/legacy、迁移到哪里”写清楚，并把任务拆分/ID 统一到 `docs/collaboration/todo.md`。

---

## 4) 重构任务清单（Prioritized，已写入 todo）

| ID | Priority | Title | Problem | Recommendation | Effort | Risk | DependsOn | Validation |
|---:|:--:|---|---|---|:--:|:--:|---|---|
| 122 | P0 | v2：文档/入口收敛（标记 v1 legacy） | v1/v2 并存但默认入口与文档事实源不一致 | 明确 v2 为默认路径；v1 标为 legacy；同步 Docs Index/Tasks/README | S | M | - | 跑 `docs/self-test.md` 的 v2 smoke；`npm --prefix apps/web run build` |
| 123 | P0 | v2：协议类型单一事实源（/api/schema/v2 → TS） | Python schema 与 TS event types 手写双份易漂移 | 以 `/api/schema/v2` 生成/校验 TS types（或 snapshot + CI diff） | M | M | 113 | `npm --prefix apps/web run build` + `python scripts/v2_smoke_test.py ...` |
| 124 | P1 | v2：工具注册表收敛（supported_tools + 严格校验） | tool 名单/输入输出 schema 分散在多处 | 输出 supported_tools；前后端共享 registry；UI 收到未知工具 fail fast | M | M | 123 | 浏览器跑 interrupt→resume；验证 409 诊断可读 |
| 125 | P1 | v2：API 模块化（RunManager / SSE emitter） | `main.py` 过载，状态/协议/传输耦合 | 拆分 store/事件序列/HTTP handlers，降低回归面 | M | M | 124 | v2 curl + smoke，trace 日志仍可用 |
| 126 | P1 | v2：Web run loop 拆分（hook + timeline renderer） | `App.tsx` 过载，难以局部修改 | 抽 `useRunStream`/`useInterruptLoop`/timeline renderer 组件 | M | M | 123 | `npm --prefix apps/web run build` + 浏览器主路径回归 |
| 127 | P1 | v2：状态/预算计数单一来源（避免双写） | RunState 与 GraphState 双写造成排障负担 | budget/plan 以 GraphState 为准；API 只读 snapshot 映射事件 | M/L | M | 125 | 多轮工具调用下 budget 单调递增且与 graph state 一致 |
| 128 | P2 | v2：持久化 checkpointer 方案评审（PostgresSaver） | InMemory 仅适合 POC，未来 durability 需要方案 | 给出迁移设计（配置、回放、自测、成本）并待你拍板 | M | M | 104 | 落地后：重启可恢复 thread/state/history |

---

## 5) 需要你拍板的决策（先定边界再动代码）

1) **v1 在 v2 worktree 的定位**：继续保留作参考，还是移动到 `legacy/`（或逐步删除）以避免误用？  
2) **协议事实源**：是否接受 “`/api/schema/v2` 作为唯一事实源 → TS types 自动生成/校验” 的方向？  
3) **工具收敛策略**：`eval_expression` 是否纳入 v2 的正式 tool roster（server 允许/LLM 可选/文档写清），还是先移出 schema 直到真正使用？  

