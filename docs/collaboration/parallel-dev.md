# 并行开发流程（团队模式，多 agent）

目标：你可以同时跑多个 agent/终端，做到 **任务可同步、改动不互相覆盖、可复盘**。

## 角色与身份（建议）
- **人类维护者**：负责拍板决策与合并。
- **多个 agent**：用 `BD_ACTOR=<agent_name>` 区分身份；用 `bd --actor <agent_name>` 也行。

## 任务认领与看板（bd）
- 单一任务源：`bd` issues（`docs/tasks/*.md` 已废弃移除）。
- 开工前：`bd update <id> --status in_progress` + `--assignee <agent_name>`。
- 阻塞：`bd update <id> --status blocked --notes "...blocker..."`。
- 完成：`bd close <id> --reason "..."`（并把验证命令/结果写进 notes）。
- 依赖：用 `bd dep add <issue> <depends-on>`（或创建时 `--deps ...`）。

## 并行改代码（worktree）
- **推荐**：每个 agent 一个 worktree 目录，避免同时改同一份工作区。
- **原则**：不要在 worktree 里面再创建子 worktree（嵌套）。优先从“主 checkout”（`.git/` 是目录）创建，或创建到同级目录。
- 从主 checkout 创建（推荐）：`bd worktree create .worktrees/<name> --branch <branch>`。
- 已在 worktree 里：`bd worktree create ../<name> --branch <branch>`（sibling，避免嵌套）。

## 同步（团队模式）
- `.beads/issues.jsonl` 会进入 git；多人/多机通过 git 同步任务。
- 收尾必须跑：`bd sync`（导出 issues.jsonl → 提交 → pull/merge → import → push）。

## 端口与本地测试
- 默认端口：Web `3000`、API `3002`、Studio `2024`。
- 多实例：为每个 worktree/agent 设置不同端口（例如 `WEB_PORT=3001 API_PORT=3003 LANGGRAPH_PORT=2025`）。

## 决策与冲突
- 发现设计冲突：在 `docs/collaboration/decision-log.md` 追加选项/取舍，并在 bd issue notes 记录结论。
- 触及关键文件：在 bd issue notes 标注“will touch <path>”，减少冲突。
