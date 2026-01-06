# v2 Hard-mode 浏览器对话验收（真实用户对话）

目标：用“真实用户多轮对话”的方式，在浏览器里验证 hard-mode 的关键体验是否正确：
- 难题进入 hard-mode（`difficulty_update.difficulty="hard"`）
- UI 展示可公开的阶段化过程（`phase_update` 驱动，不依赖/不暴露 CoT）
- 作图/验证闭环可跑通（interrupt/resume、对象确实增加）
- debug trace 可用于复现（run_id 对齐 `logs/v2/run-<run_id>.jsonl`）

> 说明：该验收是“更贴近真实用户”的 UI 级别用例，优先稳定性与可观测性；不是数学正确性证明。

---

## 前置条件
- 已安装依赖（Playwright 可用）
- 允许启动本地 dev server（web+api）
- 建议保持 `.env.local` 有可用模型配置（至少能生成作图命令）

---

## 测试用例

### 用例 HM-D1：直角三角形（3-4-5）+ 验证
**用户输入（turn 1）**：
> 请画一个满足 AB=4，AC=3，BC=5 的三角形ABC，并验证它是直角三角形（如果验证失败请修正）。

**期望**：
- UI：出现“思考进度（难题模式）”面板
- SSE/Trace：出现 `difficulty_update` 且 `difficulty="hard"`
- SSE/Trace：出现 `phase_update`，至少包含阶段：`Plan`、`Understand`、`Verify`
- 画板：对象数增加（Canvas Inspector 里 objects count 增长）

### 用例 HM-D2：在同一对话中添加高线 + 验证
**用户输入（turn 2）**：
> 在画板上画点D=(1,1)，并连结A与D。

**期望**：
- 理想情况：画板对象数继续增加
- 若模型/网络不稳定导致无法生成作图命令：允许不增加，但必须 **run_end 正常到达**（不应卡住 busy）

---

## 执行方式（推荐自动化）
运行 Playwright 自动化脚本（会自动启动 web+api，并输出截图证据到 `logs/acceptance/`）：

```bash
npm run acceptance:v2:web:dialogue
```

脚本检查项：
- Applet ready
- 两轮对话均跑到 `run_end`
- 第 1 轮必须出现 hard-mode 面板与 `phase_update`
- 画板 objects count 在两轮后都应增长
