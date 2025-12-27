## Tasks — Roadmap

### M0: Running baseline
- [x] Client + server proxy can start locally.
- [x] Multi-endpoint config via `.env.local` (`LLM_ENDPOINTS_JSON`).

### M1: Reliability
- [ ] Stronger runtime feedback capture (dialogs, evalCommand=false details).
- [ ] Consistent rollback with clear debug logs.
- [ ] Timeouts and retry budget tuning.
- [x] Canvas state on-demand: 默认不下发 `canvasState`，仅在“编辑/引用现有图”时发送，并具备兜底请求路径（todo 007/008）。

### M2: Teaching quality
- [ ] More scenario playbooks (proof, construction, simplification).
- [ ] Better “too many lines” handling (polish phase).
- [ ] Multi-turn object reuse and naming stability.
