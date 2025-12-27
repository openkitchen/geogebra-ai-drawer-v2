## Design — Architecture

### 系统组件
- **Web UI（React）**
  - 聊天输入/消息展示
  - GeoGebra Classic Web 嵌入与 JavaScript API 调用
  - Debug Panel（日志、Quick Prompt Runner、自测）
- **API Server（Node）**
- `/api/chat`：拼接 prompt + messages → 调用 LLM
- 工具原则：LLM 通过工具获取画布状态/测量结果，不直接“猜”；当前已暴露 `get_canvas_state`（后端 ai-sdk tool，前端提供对象摘要）。默认不自动下发画布状态，需模型主动调用或前端显式传入。
  - 多 provider 路由：Auto 模式下优先 Kimi，失败再降级
  - 本地兜底：关键场景（如 triangle angle sum）在 LLM 不可用时返回稳定答案
- **Prompt 层（Markdown 文件）**
  - `prompts/system.md`: 全局规则（格式、约束、通用策略）
  - `prompts/scenarios/*.md`: 场景配方（可靠的图形构造 recipe）
- **GeoGebra Applet（执行环境）**
  - 执行 LLM 生成的指令序列（DSL / `evalCommand`）
  - 产出对象列表、错误提示、弹窗等运行时反馈

### 关键数据流（高层）
1. 用户输入自然语言问题
2. Server：选择 system + scenario（如匹配到“三角形内角和”）
3. Server：调用 LLM，要求输出结构化指令（可执行的 GeoGebra 命令序列 + 讲解文本）
4. UI：逐条执行命令并收集运行时反馈
5. UI：对执行结果做**可视化卫生处理**（仅限展示层预设：如隐藏轴/网格、显示关键点标签、隐藏角度数值标签）
6. UI：若执行失败，回滚本次新增对象，并把“错误 + 当前对象列表”回传给 LLM 进行修复重试
7. 最终给用户：清晰图形 + 简洁讲解

### 为什么要区分三层（Prompt / Spec / Deterministic UI）
- **Prompt 层**负责“意图→构造策略”：画什么、怎么证明、哪些元素是关键。
- **Spec 层**负责“可验证的契约”：输出格式、失败时如何反馈、验收什么叫“清晰”。
- **Deterministic UI 层**只做“展示卫生与安全兜底”：让不同模型/不同随机性下，输出仍然可读且不会留下脏数据。

### 失败处理与修复闭环（核心机制）
- **失败来源**：语法错误、对象引用不存在、GeoGebra 弹窗中断、模型生成不符合 schema、网络/鉴权失败等。
- **处理目标**：用户只看到最终一张正确图；中间失败不会“叠图”。
- **机制**：
  - 执行前后对比对象列表（或记录 created names）→ 失败则删除新增对象（rollback）
  - 把错误消息 + 当前对象列表（RUNTIME_FEEDBACK）返给模型 → 让模型用“现状”修补，而不是从零重画

