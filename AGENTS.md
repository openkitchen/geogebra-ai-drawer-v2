# Repository Guidelines

> 并行开发指南：协作规则与最小必读清单，保持 300 字内便于快速上手。

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
- Client：`App.tsx`、`components/`；共享类型 `types.ts`；入口 `index.html`。
- Server：`server/index.mjs`（Express，加载 `prompts/` packs/constraints/scenarios）。
- Config：`scripts/`（setup/doctor）、`vite.config.ts`、`tsconfig.json`；生成物 `dist/`。
- Prompts & Docs：`prompts/` 为系统提示；规范与协作文件位于 `docs/`、`docs/collaboration/`。

## 工具优先（画布感知）
- LLM 不直接“猜”画布：获取/测量画布状态应通过工具调用，当前已有 `get_canvas_state`（后端 ai-sdk tool）。
- 默认请求不自动下发画布摘要；如需让模型看到画布，可前端传入 `canvasState` 或让模型主动调用工具。
- 新增工具请放后端（安全、可扩展），前端仅负责提供数据（例如对象摘要、测量结果）。

## 自主测试（先测再交付）
- 完成改动后，开发者需自行选择合适方式验证（本地浏览器、curl、脚本或自测用例），确保核心场景通过，避免反复让 PM 代测。
- 测试重点：新/改功能的主路径、最近问题的复现用例、关键工具调用是否触发（toolCalls）、返回字段完整性。

## 并行开发流程
- 任务看板：`docs/collaboration/todo.md` 是唯一任务源，字段：ID | Title | Owner | Status | DependsOn | LastUpdated | Notes。
- 领取规则：开始前先认领/更新状态；若发现设计冲突，用 `Status: blocked` + Blocker 说明。
- 日更节奏：每日提交前同步 `LastUpdated`，重要决定写入 `docs/collaboration/decision-log.md`。
- 协作手册：详见 `docs/collaboration/parallel-dev.md`（含冲突解决、分支命名、手动合并顺序）。

## 构建与测试
- `npm run setup`（首次），`npm run doctor`（检查 env），`npm run dev`（前后端联调 3000/3002）。
- `npm run build` → `dist/`；`npm run preview` 本地预览；`npm start` 生产模式。
- 暂无自动化测试；新增功能优先补 Vitest/Cypress，文件后缀 `.test.ts(x)`/`.spec.ts(x)`；至少确保 `npm run build` 通过。

## 编码规范
- TypeScript + React，ESM，2 空格缩进；组件/文件 PascalCase，函数/变量 camelCase，环境变量 UPPER_SNAKE_CASE。
- 避免引入新框架/大改结构；改 Prompt/工具/路由需在 PR 描述说明触及的 spec 文档与自测用例。

## 提交与 PR
- 建议 Conventional Commits（例：`feat: add commandbook lookup`）。
- PR 需包含：变更摘要、触及文档/自测条目、运行的命令与结果、截图（UI 变更）。
- 禁止提交 `.env*`、`node_modules/`；合并前确认 todo 状态已更新。

## 环境与安全
- `.env.local` 仅服务端读取；默认代理端口 3002，可用 `API_PROXY_PORT` 覆盖。
- 模型密钥支持 OpenAI/Google/OpenAI-Compatible；确保未留占位符，避免在客户端暴露。
