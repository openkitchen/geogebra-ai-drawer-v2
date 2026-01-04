# Repository Guidelines (Worktree v2)

> 决策记录：本目录是 **v2 独立 worktree**（LangGraph/LangChain Python 重构，允许破坏兼容）。  
> v1 目录保留在：`/Users/wei/workspaces/openkitchen/geogebra-ai-drawer`。  
> 协作约定：请默认只在本目录推进 v2；涉及跨版本共用的决策/规范，写入 `docs/collaboration/decision-log.md` 并用 `bd` 跟踪（团队模式：`.beads/issues.jsonl` 进 git）。

> 并行开发指南：协作规则与最小必读清单，保持 300 字内便于快速上手。

## Working agreements
- 回复使用中文；代码/注释使用英文；文档按项目要求（见 `docs/`）。

## Onboarding（先读这些）
- `docs/design/overview.md`、`docs/design/decisions.md`：产品目标、LLM 优先取舍、不能由前端硬编码替代的边界。
- `docs/spec/prompt-contract.md`、`docs/spec/runtime-feedback-repair.md`：LLM 输出契约与错误闭环。
- `docs/collaboration/parallel-dev.md`：多人并行流程与任务认领规则。
- `docs/self-test.md`：自测清单（改动后补充或勾选）。

## 设计与交互原则（必守）
1) **Child-first UX**：输出以概念+分步+可定位元素为主，命令细节不直接暴露给孩子用户。
2) **LLM 优先**：能用提示/工具/约束解决的，不新增特例 if/else；deterministic 代码只做画布卫生、安全兜底。
3) **文档同步**：涉及路由、修复闭环、输出格式、画布预设、提示体系的改动，必须同步更新对应 spec/decisions，并在 PR 中注明章节。

## 项目结构
- v2 目标结构（允许调整，但需在 PR/决策日志里同步）：
  - Web UI（React/Vite）：`apps/web/`
  - API（Python/FastAPI + LangGraph）：`apps/api/`
  - Docs：`docs/`（v2 spec 以 `docs/spec/langgraph-orchestration.md` 为主；v1 相关文档标记为 legacy 或迁移）
  - Collaboration：`docs/collaboration/`（todo/decision-log/inbox/self-test）

## 工具优先（画布感知）
- LLM 不直接“猜”画布：获取/测量画布状态应通过工具调用，当前已有 `get_canvas_state`（后端 ai-sdk tool）。
- 默认请求不自动下发画布摘要；如需让模型看到画布，可前端传入 `canvasState` 或让模型主动调用工具。
- 新增工具请放后端（安全、可扩展），前端仅负责提供数据（例如对象摘要、测量结果）。

## 自主测试（先测再交付）
- 完成改动后，开发者需自行选择合适方式验证（本地浏览器、curl、脚本或自测用例），确保核心场景通过，避免反复让 PM 代测。
- 测试重点：新/改功能的主路径、最近问题的复现用例、关键工具调用是否触发（toolCalls）、返回字段完整性。

## 并行开发流程
- 任务系统：使用 **bd（beads）** 作为唯一任务源（团队模式：`.beads/issues.jsonl` 进 git；收尾必须 `bd sync`）。
- 多 agent 身份：每个 agent/终端建议设置 `BD_ACTOR=<agent_name>`；任务用 `--assignee <agent_name>` 归属。
- 并行改代码：建议每个 agent 使用独立 worktree 目录（避免互相覆盖/冲突），用 `bd worktree create` 管理。
- 决策记录：高影响决策写入 `docs/collaboration/decision-log.md`；对应落地任务写入 bd。

## 构建与测试
- v2（规划）：
  - Web：`npm run dev` / `npm run build`（具体命令以 `apps/web/package.json` 为准）
  - API：`uv run uvicorn ...`（具体命令以 `apps/api/pyproject.toml` 为准）
  - 自测优先：每次改动后更新并勾选 `docs/self-test.md`

## 编码规范
- TypeScript + React，ESM，2 空格缩进；组件/文件 PascalCase，函数/变量 camelCase，环境变量 UPPER_SNAKE_CASE。
- 避免引入新框架/大改结构；改 Prompt/工具/路由需在 PR 描述说明触及的 spec 文档与自测用例。

## 提交与 PR
- 建议 Conventional Commits（例：`feat: add commandbook lookup`）。
- PR 需包含：变更摘要、触及文档/自测条目、运行的命令与结果、截图（UI 变更）。
- 禁止提交 `.env*`、`node_modules/`；合并前确认相关 bd issue 已更新（status/notes）。

## 环境与安全
- `.env.local` 仅服务端读取；默认代理端口 3002，可用 `API_PROXY_PORT` 覆盖。
- 模型密钥支持 OpenAI/Google/OpenAI-Compatible；确保未留占位符，避免在客户端暴露。

## Landing the Plane (Session Completion)
结束前清单（团队模式）：

1. **File issues for remaining work**：把未完事项建成/补充到 bd issue（notes/依赖/assignee）。
2. **Run quality gates**（如改了代码）：`npm --prefix apps/web run build` / `cd apps/api && uv run python -m compileall app`。
3. **Update issue status**：进行中用 `bd update --status in_progress`；完成用 `bd close`。
4. **SYNC + PUSH（必须）**：
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up**：清理 stashes、无用 worktrees/分支。
6. **Verify**：代码与 `.beads/issues.jsonl` 均已提交并 push；bd 里状态/notes 记录完整。
7. **Hand off**：在 bd issue notes 写明结论、测试命令与下一步。

**CRITICAL RULES:**
- Work is NOT complete until `bd sync` and `git push` both succeed
- NEVER stop before pushing - that leaves work stranded locally
- Use `bd` for task tracking
