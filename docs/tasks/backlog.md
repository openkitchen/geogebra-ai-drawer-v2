## Tasks — Backlog

### Product
- [ ] Onboarding: show “how to configure endpoints” in UI when none enabled.
- [ ] Presets: one-click “simplify / highlight key lines”.

### Engineering
- [ ] Add a lightweight “doctor” command for env/config sanity checks.
- [ ] Add CI: build + typecheck.
- [x] **Stability: canvas state on-demand**（todo 007）— 默认不发送 `canvasState`；引用/修改现有图时通过 `get_canvas_state()` 的 tool runner 按需获取（服务端 `tool_request` 兜底）。
- [x] **Stability: tool vs commands boundary**（todo 008）— 服务端/协议侧禁止把 `get_canvas_state()` 混进 GeoGebra `commands`，并在必要时强制走 tool-calling 链路。
- [x] **Tech debt: remove GLOBAL_CANVAS_STATE**（todo 009）— 去掉服务端全局可变 state（为未来并发与可测性铺路）。

### Prompt Engineering
- [ ] Expand repair pack for common GeoGebra errors (unknown command, illegal argument).
- [ ] Add more kid-friendly templates for explanations.
