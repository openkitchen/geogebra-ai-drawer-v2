## Tasks — Roadmap

### M0: Running baseline
- [x] Client + server proxy can start locally.
- [x] Multi-endpoint config via `.env.local` (`LLM_ENDPOINTS_JSON`).

### M1: Reliability
- [ ] Stronger runtime feedback capture (dialogs, evalCommand=false details).
- [ ] Consistent rollback with clear debug logs.
- [ ] Timeouts and retry budget tuning.
- [x] Canvas state on-demand: 默认不下发 `canvasState`；引用/修改现有图时通过 tool runner 获取，并具备服务端 `tool_request` 兜底（todo 007/008）。

### M2: Teaching quality
- [ ] More scenario playbooks (proof, construction, simplification).
- [ ] Better “too many lines” handling (polish phase).
- [ ] Multi-turn object reuse and naming stability.
