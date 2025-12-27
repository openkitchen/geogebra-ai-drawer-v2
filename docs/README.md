## GeoGebra AI Drawer — Docs Index

这份索引把文档分成三层：**Design（为什么这么做）**、**Spec（要做到什么程度）**、**Tasks（怎么分阶段做）**。后续实现以 Spec 与 Tasks 为准，Design 负责解释取舍与原则；并行协作与流程见 Collaboration。

### 设计（Design）
- `docs/design/overview.md`: 产品目标、用户体验原则、非目标
- `docs/design/architecture.md`: 系统架构与关键数据流（LLM ⇄ GeoGebra ⇄ UI）
- `docs/design/decisions.md`: 关键设计决策与取舍（context engineering vs deterministic rules）

### 规格（Spec）
- `docs/spec/prompt-contract.md`: Prompt/Scenario 的组织方式与输出约束（DSL 结构）
- `docs/spec/runtime-feedback-repair.md`: 运行时反馈、自我修正、回滚语义
- `docs/spec/canvas-presets.md`: 画布预设（几何 vs 代数）、标签显示、角度数值标签策略
- `docs/spec/model-routing.md`: 多模型路由与降级（Auto 优先 Kimi）、本地兜底
- `docs/spec/debug-selftest.md`: Debug Panel、自测用例格式、验收方式
- `docs/spec/diagram-quality.md`: “可读性”与“教学直观性”的验收标准
- `prompts/geogebra-constraints.md`: 关键 GeoGebra 约束补充（内角优先等）

### 任务（Tasks）
- `docs/tasks/roadmap.md`: 里程碑与阶段性目标
- `docs/tasks/backlog.md`: 任务拆分（可直接进迭代）

### 协作（Collaboration）
- `docs/collaboration/parallel-dev.md`: 并行开发流程、分支/提交流程、冲突处理
- `docs/collaboration/todo.md`: 单一任务源（ID/Owner/Status/Notes）
- `docs/collaboration/decision-log.md`: 高影响决策记录（Topic/Options/Decision）
- `docs/collaboration/inbox-codex-A.md` / `docs/collaboration/inbox-codex-B.md`: 双开发的收件箱，用于交接与提醒

### 现有文档（Existing）
- `docs/prompt-system.md`: 现有提示词系统说明（历史与实现细节）
- `docs/self-test.md`: 当前自测集合与结果（将逐步迁移到 spec 定义的格式）
- `docs/env.example.md`: 环境变量说明
