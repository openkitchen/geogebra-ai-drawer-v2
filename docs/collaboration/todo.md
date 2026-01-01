# 任务看板（单一来源）

字段：`ID | Title | Owner | Status | DependsOn | LastUpdated | Notes`

- Owner: codex-A / codex-B / wei
- Status: backlog | in-progress | blocked | review | done

| ID  | Title | Owner | Status | DependsOn | LastUpdated | Notes |
| --- | ----- | ----- | ------ | --------- | ----------- | ----- |
| 100 | v2：创建独立 worktree 目录（隔离 v1/v2） | codex-A | done | - | 2025-12-31 | v2 worktree：`/Users/wei/workspaces/openkitchen/geogebra-ai-drawer-v2`；并更新 v2 `AGENTS.md` 与 decision-log |
| 101 | v2：Python API 脚手架（FastAPI + SSE echo） | codex-A | done | 100 | 2025-12-31 | 新增 `apps/api`：`POST /api/threads`、`POST /api/threads/{thread_id}/runs/stream`、`GET /healthz`；SSE 输出 `run_start/plan_update/token/final` |
| 102 | v2：补齐文档索引与自测（API smoke test） | codex-A | done | 101 | 2025-12-31 | 已更新 `docs/README.md` 索引；在 `docs/self-test.md` 增加 v2 API 的 curl 自测步骤（thread/run SSE） |
| 103 | v2：Web UI 迁移到 `apps/web` 并消费 SSE | codex-A | done | 101 | 2025-12-31 | 已完成：最小 UI + SSE 解析；对话气泡持久化 `RunStreamEvent`；支持 interrupt→/resume 多轮继续 |
| 104 | v2：LangGraph durable state（checkpointer + interrupts/resume） | codex-A | done | 101 | 2025-12-31 | 已接入 LangGraph `interrupt()` + `Command(resume=...)`；已提供 `GET /state` 与 `GET /state/history`；POC 先用 InMemorySaver |
| 105 | v2（codex-B）：Web 嵌入 GeoGebra 画板（最小可用） | codex-B | done | 103 | 2025-12-31 | `apps/web` 嵌入 Classic（deployggb.js）+ ready 状态；build 通过 |
| 106 | v2（codex-B）：前端工具实现（get_canvas_state / eval_expression / exec_geogebra_commands） | codex-B | done | 105,104 | 2025-12-31 | interrupt(kind=frontend_tool)→前端执行→/resume 回填真实结果；build 通过 |
| 107 | v2（codex-A）：/resume 严格校验与一致性契约（tool_call_id/shape） | codex-A | done | 104 | 2025-12-31 | tool_call_id/tool_name mismatch 返回 409；duplicate resume 兜底；自测文档同步 |
| 108 | v2（codex-A）：多步 action loop（支持多次 interrupt） | codex-A | done | 107 | 2025-12-31 | 支持连续多次 frontend_tool；budget 事件可见 |
| 109 | v2（codex-B）：UI 过程展示（更像 codex-cli） | codex-B | done | 103,106 | 2025-12-31 | Timeline（budget/node/plan/tool_use/tool_result/final/run_end）+ Debug events 折叠；build 通过 |
| 110 | v2（codex-A）：补齐 v2 工具/事件契约文档（可直接对照实现） | codex-A | done | 107 | 2025-12-31 | 更新 `docs/spec/langgraph-orchestration.md` + `docs/self-test.md` |
| 111 | v2（codex-A）：demo draw（exec_geogebra_commands）+ 结果摘要 | codex-A | done | 106 | 2025-12-31 | 最小 demo：get_canvas_state→exec→get_canvas_state→final |
| 112 | v2（codex-B）：前端工具幂等 + /resume 409 诊断 | codex-B | done | 106,111 | 2025-12-31 | tool_call_id 缓存防重复执行；/resume 非 2xx 写 client_error 事件；build 通过 |
| 113 | v2（codex-A）：协议/类型收敛（Pydantic schema + protocol_version + schema endpoint） | codex-A | done | 112 | 2025-12-31 | `apps/api/app/protocol_v2.py` + `GET /api/schema/v2`；run_start.data 带 protocol_version |
| 114 | v2（codex-B）：Web UX 小步增强（New thread / Clear chat / Clear canvas / 多行输入 / 自动滚动） | codex-B | done | 103 | 2025-12-31 | build 通过 |
| 115 | v2（codex-B）：Schema viewer + protocol_version 展示（对齐 113） | codex-B | done | 113 | 2025-12-31 | UI 增加 schema 面板；labels string→string[]；build 通过 |
| 116 | v2（codex-A）：后端接入真实 LLM（最小可用，stub fallback） | codex-A | done | 113 | 2026-01-01 | `.env(.local)` 驱动模型（aliases+roles）；修复 python-dotenv 默认插值导致 `${VECTORENGINE_API_KEY}` 变空；command-gen 注入 `prompts/commandbook.json` + `prompts/geogebra-constraints.md`；支持按 role 调用（main/repair） |
| 117 | v2（codex-B）：Canvas Inspector（只读，对照 schema） | codex-B | done | 115 | 2025-12-31 | UI 增加 Canvas Inspector（get_canvas_state 展示 objects） |
| 118 | v2（codex-B）：e2e smoke script（SSE 自动 interrupt→resume） | codex-B | done | 116 | 2026-01-01 | `scripts/v2_smoke_test.py` 支持模拟工具并可 `--force-repair-once` 覆盖 repair loop；支持 `--turn` 多轮（同 thread） |
| 119 | v2（codex-B）：UI budget + LLM meta 展示增强 | codex-B | done | 116 | 2025-12-31 | Timeline 展示 tool/model budget；meta 展示 llm_enabled/llm_model |
| 120 | v2（codex-A）：后端支持 Gemini 原生 API（provider=google / v1beta） | codex-A | backlog | 116 | 2025-12-31 | 目前先用 VectorEngine OpenAI-compatible 调 `gemini-*`；该任务用于补齐原生 Google API 的行为差异与稳定性 |
| 121 | v2（codex-A）：多轮问题排障 trace（后端写入 logs + UI 一键复制 run_id） | codex-A | done | 116 | 2025-12-31 | 后端写 `logs/v2/run-<run_id>.jsonl`；UI 可 copy run_id/thread_id/debug JSON/draw commands |
| 122 | P0 v2：执行层“无残留”闭环（dialog 捕获 + 差集回滚 + 高信号反馈结构） | codex-A | done | 106,104 | 2025-12-31 | exec 增加 dialogs + created/deleted 差集 + 硬失败自动回滚；新增 delete_objects 工具供语义失败 deterministic 回滚；`npm --prefix apps/web run build` ✅ |
| 123 | P0 v2：verify + repair loop（硬失败 + 语义失败） | codex-A | done | 122 | 2026-01-01 | verify 覆盖退化 + 关键对象缺失 +（新增）内接/直角三角形的坐标语义校验；语义失败直接 `delete_objects` 回滚再重试；tool_calls_limit=12；预算耗尽时绘图场景 final 保持 deterministic；`python scripts/v2_smoke_test.py --force-repair-once` ✅ |
| 124 | P0 v2：画布卫生/可读性兜底（几何 preset + 标签/角度展示 + 质量校验） | codex-A | done | 105,106 | 2025-12-31 | geometry preset 隐藏轴/网格；showKeyLabels；hideAngleValueLabels；validateDiagram 告警通过 tool output 回传 |
| 125 | P0 v2：工具 roster 单一事实源 + 对齐校验（schema/前端/后端/文档） | codex-A | done | 113 | 2025-12-31 | schema 增补 delete_objects 与 exec 输出字段；同步 `docs/spec/langgraph-orchestration.md`、`docs/self-test.md` |
| 126 | P1 v2：prompt/playbook 资产化（packs/scenarios/constraints/commandbook 注入） | codex-A | done | 123 | 2026-01-01 | 已接入：`prompts/v2/*` + `prompts/packs/*` + `prompts/scenarios/*` + `prompts/commandbook.json`；command-gen/final/plan/memory 均 file-based |
| 127 | P1 v2：多轮记忆/偏好（history + summarization 策略） | codex-A | done | 123 | 2026-01-01 | GraphState 增加 `memory_messages` + `memory_summary`；超阈值自动 summarization（`V2_MEMORY_*` 可配）；LLM 调用注入 memory context |
| 128 | P1 v2：编辑意图与安全边界（删/改/重画/复用对象策略） | codex-A | backlog | 127 | 2025-12-31 | 明确 edit intent + 安全动作边界（Child-first） |
| 134 | P1 v2：Plan 可见（模型 plan → plan_update 事件） | codex-A | done | 123 | 2026-01-01 | graph 增加 `plan_node`；SSE 输出真实 `plan_update`；UI 时间线展示 plan（可折叠） |
| 135 | v2：文档/入口收敛（标记 v1 legacy） | codex-A | done | - | 2026-01-01 | root `README.md` 增加 v2 Quickstart；root `package.json` 增加 `npm run dev:v2`；v2 Web 默认端口 3000（见 `apps/web/vite.config.ts` 与 `docs/self-test.md`） |
| 136 | v2：协议类型单一事实源（/api/schema/v2 → TS） | codex-B | backlog | 125 | 2025-12-31 | 以 `GET /api/schema/v2` 为事实源生成/校验 TS types（替代手写 `RunStreamEvent`）；加 CI/脚本防漂移 |
| 137 | v2：工具注册表收敛（supported_tools + 严格校验） | codex-A | backlog | 125 | 2025-12-31 | server 输出 supported_tools；UI 收到未知 tool fail-fast；明确 `eval_expression` 的正式定位 |
| 138 | v2：API 模块化（RunManager / SSE emitter） | codex-A | backlog | 125 | 2025-12-31 | 拆分 `apps/api/app/main.py`：store/事件序列/handlers 解耦，减少全局状态散落 |
| 139 | v2：Web run loop 拆分（hook + timeline renderer） | codex-B | backlog | 136 | 2025-12-31 | 拆分 `apps/web/src/App.tsx`：SSE consume、interrupt loop、timeline 渲染解耦 |
| 140 | v2：状态/预算计数单一来源（避免 RunState/GraphState 双写） | codex-A | backlog | 138 | 2025-12-31 | 明确 source-of-truth（优先 GraphState）；API 层只读 snapshot 映射 budget/plan |
| 141 | v2：持久化 checkpointer 方案评审（PostgresSaver） | wei | backlog | 104 | 2025-12-31 | 输出迁移设计（配置、回放/恢复、自测、成本）并待拍板 |
| 142 | P1 v2：数值测量工具（measure_expression / eval_numeric） | codex-A | done | 125 | 2026-01-01 | 新增 `eval_numeric`（multi-expressions）并接入前端工具；用于补强三角形语义验证（必要时先测再判定） |
