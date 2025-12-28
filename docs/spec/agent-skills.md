## Spec — Agent Skills（Codex Skills）

本项目把 “Skill” 理解为 **Codex CLI 的可复用工作流包**（不是产品功能）。Skill 用于约束/固化一类高频工作方式，减少遗漏与回归。

### 1) 本仓库提供的自定义技能

#### `refactor-arch`
- 目标：面向未来需求做架构/代码模式重构审计，输出“优先级清单”，由人类决策后再逐项落地。
- 产出物：
  - `docs/design/refactor-arch-report-YYYY-MM-DD.md`
  - `docs/collaboration/todo.md`：新增/更新与报告对应的重构任务（含 DependsOn 与验证方式）
- 约束：
  - **只做诊断与任务分解**，不直接改代码；除非用户明确要求开始重构。
  - 稳定性优先：优先收敛协议/边界/可观测性，再做结构拆分。

代码位置：`skills/refactor-arch/SKILL.md`

### 2) 如何安装到本机 Codex（让它“出现在 Skills 列表里”）

Codex 默认从 `$CODEX_HOME/skills`（常见为 `~/.codex/skills`）加载自定义技能。本仓库里的 skill 不会自动被 Codex 发现，需要安装/同步一次：

```bash
mkdir -p ~/.codex/skills
rm -rf ~/.codex/skills/refactor-arch
cp -R skills/refactor-arch ~/.codex/skills/refactor-arch
```

安装后，在对话中输入 `refactor-arch` 即可触发。

### 3) 系统内置技能（仅说明）

系统内置技能通常位于 `~/.codex/skills/.system/*`，用于通用能力（例如 skill-creator/skill-installer）。它们不属于本仓库文档的一部分，但会在运行时被 Codex 发现并可用。

