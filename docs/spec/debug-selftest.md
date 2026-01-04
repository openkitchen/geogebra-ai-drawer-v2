## Spec — Debug & SelfTest (Proof-focused)

### 目标
用可重复的自测快速回归：判断图是否“足够清晰”、失败是否被回滚、Auto 是否走到 Kimi。

### 验收门槛（必须：ai-web + ai-api）
> 规则：**ai-web** 或 **ai-api** 任一不通过，都不能算验收通过。

- **ai-web（浏览器）**：必须在 `http://127.0.0.1:3000/` 走一遍主路径（画板 ready + 发送消息 + 图形出现 + Debug/Timeline 能看到 interrupt/resume 链路）。
- **ai-api（脚本）**：必须跑 `./scripts/v2_acceptance_api.sh`（healthz + schema + thread/run SSE + interrupt/resume + repair once）。
- **Agent 责任**：自动化 agent 必须亲自执行上述两项，并在交付信息中提供浏览器验收证据（截图/录屏/日志）与脚本输出摘要。
- 详细操作步骤与期望：见 `docs/self-test.md` 的「0) 交付/验收方式」。

### 测试用例格式
- 每个用例：`{ id, prompt }`
- 执行流程：通过 **主聊天链路** 发起 run（SSE）→ 前端按 interrupt/resume 执行工具 → 记录 pass/fail、usedEndpointId、耗时、错误。

### 回归用例（最少集）
- `angle-sum`：三角形内角和=180°（平行线法）
- `parallel-through-point`：过直线外一点作平行线，并标注 l/P/m
- `pythagoras-demo`：直角三角形 + 文字解释（可只画三角形，但角度数值应隐藏）

### 判定逻辑
- 存在性：
  - angle-sum：A,B,C；平行线；三角形；至少 1 条文本锚点；角弧对象存在。
  - parallel：l、P、m 三对象可检测（线与点）；平行线绘出。
  - pythagoras：直角三角形（含直角点）；解释文本存在。
- 可读性：
  - 角度数值标签不可见；可用 α/β/γ 文本。
  - 辅助线不应过多：对象数有上限（建议 <=30），无大面积交叉延长线。
- 执行成功：所有命令 `evalCommand` 成功，无未知命令；失败需回滚新建对象。
- 残留：用例结束时画布恢复到执行前对象集。
- 路由：记录 `usedEndpointId`，Auto 下应优先 `kimi`（或本地 fallback）。

### Debug 面板要求
- 按钮：Run SelfTest（执行全部用例）；Run Prompt（单条 prompt）。
- 日志：结构化输出到 `__ggbDebugLog` 与 console（JSON 一行），字段包含 `type`, `id/prompt`, `pass`, `stage`, `error`, `usedEndpointId`, `rolledBack/cleaned`, `ms`，以及可选的 `toolCalls`（用于确认 tool-calling 是否发生）。***
