# 并行开发流程（codex-A / codex-B / wei）

## 角色与职责
- **codex-A / codex-B**：实现与测试，按任务拆分，遵循本文与 `AGENTS.md`。
- **wei（PM/maintainer）**：分配任务、确认设计/决策、合并/发布。

## 任务认领与看板
- 单一任务源：`docs/collaboration/todo.md`。
- 开工前：认领 `Owner`，将 `Status` 置为 `in-progress`；如有依赖，填 `DependsOn`。
- 阻塞：将 `Status` 改为 `blocked`，在 `Notes` 写明阻塞原因与需要谁解。
- 完成：将 `Status` 置 `done`，更新 `LastUpdated`，在 PR 描述引用任务 ID。

## 日常节奏
- **每日更新**：每个在做的任务更新 `LastUpdated`，保持 Notes 简短可读。
- **决策记录**：涉及接口/提示词/路由/闭环的取舍，追加到 `docs/collaboration/decision-log.md`。

## 分支与提交
- 分支命名：`task/<id>-<short-slug>`（例：`task/012-commandbook`）。
- 提交信息：推荐 Conventional Commits；在首条提交或 PR 描述中引用任务 ID。

## 协作与冲突
- 提前声明：如果需要触及他人文件，在 `todo.md` Notes 标注“will touch <path>”。
- 合并顺序：先完成的先提 PR，后者负责 rebase/merge 主干。
- 发现设计冲突：不自行拍板，改为在 `decision-log.md` 写出选项 + 推荐方案，@wei 选择。

## 交接与收尾
- 交接给另一名开发：在对应 `inbox-codex-*.md` 写下上下文（任务 ID、变更点、待办、测试命令）。
- PR 前自检：最小可行测试（至少 `npm run build`），并在 PR 描述列出运行命令与结果。
