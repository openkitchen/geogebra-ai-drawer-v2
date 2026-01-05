# Spec v2 — Hard-mode（难题模式）：分阶段思路 + 画板验证循环 + 可观测/可复现

目标：当用户提出“较难的几何题/约束题”时，系统进入 **hard-mode**，以“阶段 → 假设 → 画板验证 → 修正”的方式稳定推进，并把**可公开的过程**展示在 UI 上（不依赖/不暴露模型的私有 CoT）。

非目标：不强行要求所有题都解对（MVP-A 先把机制、观测与复现打通）。

---

## 1) 触发与路由（必须：小模型判定，无兜底）

### 1.1 Difficulty classifier（小模型，必需组件）
- 后端在每次用户输入的 `ingest_node` 阶段调用小模型，输出：
  - `difficulty: "simple" | "hard"`
  - `confidence: 0..1`
  - `reasons[]`：**安全、可公开**的短理由（禁止 chain-of-thought）
- 若小模型不可用 / 返回无效：**直接报错（fail fast）**，并确保 trace 可用于排障。

### 1.2 UI 行为（按难度分流）
- `simple`：保持轻量交互（直接画/答），不展示阶段化过程。
- `hard`：开启阶段化过程展示（见 §2），同时后端会强制打开 `plan_mode`（用于输出整体思路）。

---

## 2) Hard-mode 的运行循环（plan → act → verify → revise）

Hard-mode 的核心是一个可重复的“验证驱动”循环：

1. **Plan**：先给出整体思路（plan_update + phase_update/Plan）
2. **Understand**：读取画板状态（get_canvas_state）
3. **Act**：生成并执行作图步骤（exec_geogebra_commands）
4. **Verify**：刷新画板并验证是否满足条件（verify_canvas / 必要时 eval_numeric）
5. **Revise**：若验证失败：
   - 清理本次新增对象（delete_objects）
   - 结合反馈生成修复版步骤，进入下一轮 Act → Verify
6. **Finalize**：验证通过后输出讲解；或预算耗尽后结束（尽量保持画板干净）

> 备注：MVP-A 里 `verification` 字段应使用**面向用户的描述**（如“读取画板状态/数值检查/清理对象”），不要直接暴露工具函数名；调试细节可从 SSE 的 tool_start/tool_end 与 trace 中获取。

---

## 3) UI 可见过程（不依赖 CoT）

### 3.1 事件（SSE）
后端会额外发出两类 hard-mode 事件（均写入 trace）：
- `difficulty_update`：难度判定结果 + reasons（可公开）
- `phase_update`：阶段化进度（可公开）

其中 `phase_update` 的字段为：
- `seq`：单调递增序号（便于 UI 排序/去重）
- `phase`：阶段名（Plan/Understand/Act/Verify/Revise/Finalize/…）
- `summary`：该阶段对孩子可读的“在做什么”
- `hypothesis`：可公开的假设（短句，不是推导）
- `verification`：本步将如何验证（面向用户描述）
- `result`：阶段结果（可公开）
- `next`：下一步（可公开）

### 3.2 UI 展示原则（Child-first UX）
- 难题才展示（simple 不展示）
- 不展示“命令细节/工具函数名/复杂推导”
- 展示“阶段 + 关键假设 + 如何验证 + 结论 + 下一步”
- 开发调试仍通过 Debug/Timeline 查看完整事件流与工具 I/O

---

## 4) 可观测与复现（RCA / 评估）

### 4.1 Debug trace（JSONL）
当 `ui_context.debug=true` 时，后端会记录：
- `logs/v2/run-<run_id>.jsonl`
- 包含：HTTP（runs_stream.request / resume.request）、SSE（difficulty_update / phase_update / tool_start / tool_end / final …）、异常等。

### 4.2 快速定位脚本
可用脚本快速提取“为什么被判 hard、阶段走到哪、哪里失败”：
```bash
python3 scripts/v2_trace_inspect.py --run-id "<run_id>"
```

### 4.3 建议的复现流程（人工/自动都适用）
1) 在 UI Debug/Timeline 里复制 `run_id`
2) 打开 `logs/v2/run-<run_id>.jsonl`
3) 用 `scripts/v2_trace_inspect.py` 摘要查看：
   - difficulty_update（reasons）
   - phase_update（最后阶段/失败点）
   - exceptions（是否有隐藏异常）
4) 用相同输入再次运行，比较两次的 phase_update 路径差异；把两份 trace 贴到 bd issue notes 里做 RCA

