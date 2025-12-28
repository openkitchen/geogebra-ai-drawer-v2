# 任务看板（单一来源）

字段：`ID | Title | Owner | Status | DependsOn | LastUpdated | Notes`

- Owner: codex-A / codex-B / wei
- Status: backlog | in-progress | blocked | review | done

| ID  | Title | Owner | Status | DependsOn | LastUpdated | Notes |
| --- | ----- | ----- | ------ | --------- | ----------- | ----- |
| 001 | 建立 commandbook（常用命令签名+示例） | codex-A | backlog | - | 2025-12-25 | 初始条目包含 Text/Polygon/SetColor/Angle/Circle |
| 002 | 记录执行错误并自动注入 commandbook | codex-B | in-progress | 001 | 2025-12-25 | server hook：根据 errorContext 检索注入 system prompt；codex-B 正在设计最小实现 |
| 003 | 扩充自测用例（签名纠正/降级路径） | codex-A | backlog | 001 | 2025-12-25 | 在 docs/self-test.md 增补 3-5 条场景 |
| 004 | 决策：色值 0..1 vs 0..255 归一策略 | wei | backlog | - | 2025-12-25 | 记录到 decision-log.md，统一前后端参数约定 |
| 005 | Reflection: 轴/网格命令失败 & 提示修正 | codex-B | in-progress | - | 2025-12-26 | 落盘错误日志 + 修正 SetAxesVisible/SetGridVisible 提示，补自测 |
| 006 | 工具链稳定化（get_canvas_state 仍报 result is not defined） | codex-B | done | - | 2025-12-27 | 修复 /api/chat 成功路径 ReferenceError；服务端统一返回 toolCalls；DebugPanel 增加 toolCalls 展示；build + browser self-test 通过 |
| 007 | CanvasState on-demand（默认不发 state） | codex-B | done | - | 2025-12-28 | 客户端不主动发送 `canvasState`；引用/修改现有图时通过 `get_canvas_state()` 的 tool runner 按需获取（服务端 `tool_request` 兜底）。 |
| 008 | 工具/命令边界兜底（禁止 tool 混进 commands） | codex-B | done | 007 | 2025-12-28 | 服务端对 `commands` 做安全/一致性校验：剔除 `get_canvas_state()` 等 tool 伪命令；统一走 `tool_request`/`TOOL_RESULT` 闭环，避免旧 token/直传 state。 |
| 009 | 去掉 GLOBAL_CANVAS_STATE（per-request context） | codex-B | done | 007,014 | 2025-12-28 | 已移除服务端全局可变画布 state，避免未来并发/多 tab 串线风险。 |
| 010 | 聊天窗口：解释保留换行 + 命令可折叠/复制 + 多行输入 | codex-A | done | - | 2025-12-26 | implemented in components/ChatInterface.tsx; self-test updated |
| 011 | 聊天窗口可观测性：显示 tool 使用/重试记录（默认折叠） | codex-B | done | 006 | 2025-12-27 | 在对话中追加“运行记录”折叠块：展示 toolCalls / fallback / retry / rollback 等摘要与详情（自测通过） |
| 012 | 聊天窗口：pending 时显示 thinking... | codex-B | done | - | 2025-12-27 | 发送后未返回时，在对话区显示一条临时 assistant bubble：thinking...（自测通过） |
| 013 | 新增工具：set_corner_text（画布四角固定提示文字） | codex-B | done | 011 | 2025-12-27 | 服务端新增 tool + 协议字段；前端渲染 overlay；模型可调用 tool 更新角落提示（自测通过） |
| 014 | 通用工具调用（前端执行 tool runner，多轮 HTTP） | codex-B | done | 007,008 | 2025-12-28 | 主链路已收敛为 kind=tool_request → TOOL_RESULT → kind=final；并已移除旧 token/直传 state 与 /api/ggb。 |
| 015 | 协议收敛：/api/chat 版本化响应（kind/tool_request/tool_result） | codex-B | backlog | 014 | 2025-12-27 | 引入共享类型与 zod 输出校验，避免前后端/文档漂移；为后续模块化重构提供回归面 |
| 016 | 下线 /api/ggb，统一走 /api/chat | codex-B | done | 014 | 2025-12-28 | 已删除 `/api/ggb` 旧路由，统一走 `/api/chat`（kind=final/tool_request）。 |
| 017 | 服务端模块化拆分（index.mjs 拆分 router/llm/prompt/cache/tools） | codex-B | backlog | 015 | 2025-12-28 | 016 已完成，剩余依赖为 015；降低 god-file 风险；小步迁移，确保 build+自测通过 |
| 018 | 前端模块化拆分（App.tsx 拆分 chatRunner/toolRunner/ggbExecutor） | codex-B | backlog | 015 | 2025-12-28 | 依赖不变；降低 App.tsx 复杂度，减少回归概率；保持行为不变为第一原则 |
| 019 | 统一 overlay 路径（overlayText vs set_corner_text） | codex-B | backlog | 015 | 2025-12-28 | 依赖不变；明确主路径与降级路径，减少模型行为不确定性与文档困惑 |
| 020 | 新增 Codex skill：refactor-arch（并纳入 docs 索引） | codex-B | done | - | 2025-12-28 | 仓库内：`skills/refactor-arch/SKILL.md`；安装说明见 `docs/spec/agent-skills.md` |
