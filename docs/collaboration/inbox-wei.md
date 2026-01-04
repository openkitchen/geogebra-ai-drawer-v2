# Inbox wei (PM/Maintainer)

| Date | From | Task ID | Message | Status |
| ---- | ---- | ------- | ------- | ------ |
| 2025-12-25 | codex-B | 002 | commandbook 注入 hook 已落地为：errorContext→token→commandbook hints（限量 0-3 条）并拼入 system prompt（见后续继续完善）；当前以“控制 prompt 体积”为主，不依赖额外小模型 | done |
| 2025-12-31 | codex-A | 116/120 | v2 基础链路自测：后端 `compileall` ✅；`scripts/v2_smoke_test.py`（stub + llm）均 ✅；`npm --prefix apps/web run build` ✅。已在 v2 看板新增 120（Gemini 原生 API / provider=google / v1beta，backlog）；短期先用 VectorEngine 的 OpenAI-compatible 方式调用 `gemini-*`（`/v1/models` 已包含），避免立刻接原生 Google API。待 codex-B 做一次 UI 回归（画一个圆 + Canvas Inspector）确认无 UX/事件异常。 | open |
| 2025-12-31 | codex-A | 116 | v2 端到端回归（多轮对话）：同一 thread 连续 4 轮（画圆→改半径→再画圆→纯概念解释），SSE 的 plan_update/budget/interrupt→resume 闭环均正常；并补了 3 个基础兜底：A) tool_calls 用尽后 final 会再走一次 LLM 给出更“教小朋友”的总结/步骤；B) 用户明确说“不要/不用画”时，只做一次 get_canvas_state 后直接文本回答（避免误画）；C) tool_results 仅保留最近 30 条避免 state 无界增长。 | open |
| 2025-12-31 | codex-A | 116 | UI 回归反馈：第二次交互“有点不太对”。为便于定位，已新增后端 debug trace：默认在 `logs/v2/run-<run_id>.jsonl` 记录 HTTP/SSE/异常；并在 UI Timeline 的 run_start 行展示完整 run_id（便于直接对照日志）。待复现并收集该 run 的 trace + Debug events。 | open |
