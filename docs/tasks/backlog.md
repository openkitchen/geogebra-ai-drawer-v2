## Tasks — Backlog

### Product
- [ ] Onboarding: show “how to configure endpoints” in UI when none enabled.
- [ ] Presets: one-click “simplify / highlight key lines”.

### Engineering
- [ ] Add a lightweight “doctor” command for env/config sanity checks.
- [ ] Add CI: build + typecheck.
- [x] **Stability: canvasState on-demand**（todo 007）— 默认不发送 `canvasState`，仅在“编辑/引用现有图”时发送，并补一个“误判时再请求 state”的兜底路径。
- [x] **Stability: tool vs commands boundary**（todo 008）— 服务端/协议侧禁止把 `get_canvas_state()` 混进 GeoGebra `commands`，并在必要时强制走 tool-calling 链路。
- [ ] **Tech debt: remove GLOBAL_CANVAS_STATE**（todo 009）— 去掉服务端全局可变 state，把画布状态变为 per-request context（为未来并发与可测性铺路）。

### Prompt Engineering
- [ ] Expand repair pack for common GeoGebra errors (unknown command, illegal argument).
- [ ] Add more kid-friendly templates for explanations.
