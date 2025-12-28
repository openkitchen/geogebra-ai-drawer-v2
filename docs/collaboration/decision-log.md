# 决策日志（高影响取舍）

记录格式：`Date | Owner | Topic | Options | Decision | Rationale | Follow-ups`

| Date | Owner | Topic | Options | Decision | Rationale | Follow-ups |
| ---- | ----- | ----- | ------- | -------- | --------- | ---------- |
| 2025-12-25 | wei (pending) | 色值规范（SetColor 0..1 vs 0..255） | A) 前端改为 0..1；B) 前端容忍 0..1 并转换到 0..255；C) 统一 JS API 接口为 0..255 | TBD | 待讨论 | 与 commandbook 一并更新规范和自测 |
| 2025-12-27 | wei | 画布状态默认不下发（canvasState） | A) 默认不发，按需发送；B) 默认每次发送 | A | 与 tool-first / token 成本控制一致；避免把“画布摘要”变成隐性依赖；只有在编辑/引用现有图时才需要 | 落地 tool runner：服务端 `tool_request` 兜底 + 前端回传 `TOOL_RESULT`（见 todo 007/008/014） |
