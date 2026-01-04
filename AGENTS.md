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
  - Collaboration：`docs/collaboration/`（decision-log/inbox/self-test；任务用 bd 跟踪）

## 工具优先（画布感知）
- LLM 不直接“猜”画布：获取/测量画布状态应通过工具调用，当前已有 `get_canvas_state`（后端 ai-sdk tool）。
- 默认请求不自动下发画布摘要；如需让模型看到画布，可前端传入 `canvasState` 或让模型主动调用工具。
- 新增工具请放后端（安全、可扩展），前端仅负责提供数据（例如对象摘要、测量结果）。

## 自主测试（先测再交付）
- 交付/验收必须同时覆盖 **ai-web + ai-api**（任一不通过，都不能算通过）。
- **ai-web（核心，必须用浏览器）**：必须用浏览器打开 `http://127.0.0.1:3000/` 做一次主路径交互（画板 ready + 发送消息 + 图形出现 + Debug/Timeline 有完整 interrupt/resume 链路）。
- **ai-api（命令行）**：必须跑 `./scripts/v2_acceptance_api.sh`（healthz + schema + SSE interrupt/resume + repair once）。
- **Agent 责任（强制）**：如果你是自动化 agent（例如 Codex/CI bot），**不得只“建议”人类去点**；你必须自己完成上述浏览器与命令行验收，并在交付信息里写明：使用的命令、通过/失败、以及浏览器验收的证据（例如截图路径/录屏/日志）。
- **教训（别忘）**：如果浏览器/日志里出现 `401/403`、`insufficient_quota`、或“没能调用语言模型”，优先检查并更新 `.env.local` 的 key/role 绑定（必要时改用 `V2_ENV_FILE=../geogebra-ai-drawer/.env.local` 复用 v1 的密钥），并**重启** `./scripts/v2_dev.sh` 后再重新验收。
- 其余回归（按改动挑选）：最近问题复现用例、关键工具调用（toolCalls）、返回字段完整性；详见 `docs/self-test.md`。

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
2. **Run acceptance gates（必须：ai-web + ai-api）**：
   - 浏览器打开 `http://127.0.0.1:3000/` 跑一遍主路径（画板 ready + 发送消息 + 图形出现 + Debug/Timeline 有 interrupt/resume）。
   - 命令行跑 `./scripts/v2_acceptance_api.sh`。
   - 记录证据（截图/录屏/日志）到 bd issue notes / PR 描述。
3. **Run quality gates**（如改了代码）：`npm --prefix apps/web run build` / `cd apps/api && uv run python -m compileall app`。
4. **Update issue status**：进行中用 `bd update --status in_progress`；完成用 `bd close`。
5. **SYNC + PUSH（必须）**：
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
6. **Clean up**：清理 stashes、无用 worktrees/分支。
7. **Verify**：代码与 `.beads/issues.jsonl` 均已提交并 push；bd 里状态/notes 记录完整。
8. **Hand off**：在 bd issue notes 写明结论、测试命令与下一步。

**CRITICAL RULES:**
- Work is NOT complete until `bd sync` and `git push` both succeed
- NEVER stop before pushing - that leaves work stranded locally
- Use `bd` for task tracking

<!-- bv-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View issues (launches TUI - avoid in automated sessions)
bv

# CLI commands for agents (use these instead)
bd ready              # Show issues ready to work (no blockers)
bd list --status=open # All open issues
bd show <id>          # Full issue details with dependencies
bd create --title="..." --type=task --priority=2
bd update <id> --status=in_progress
bd close <id> --reason="Completed"
bd close <id1> <id2>  # Close multiple issues at once
bd sync               # Commit and push changes
```

### Workflow Pattern

1. **Start**: Run `bd ready` to find actionable work
2. **Claim**: Use `bd update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `bd close <id>`
5. **Sync**: Always run `bd sync` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `bd ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers, not words)
- **Types**: task, bug, feature, epic, question, docs
- **Blocking**: `bd dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
bd sync                 # Commit beads changes
git commit -m "..."     # Commit code
bd sync                 # Commit any new beads changes
git push                # Push to remote
```

### Best Practices

- Check `bd ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `bd create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always `bd sync` before ending session

<!-- end-bv-agent-instructions -->
