# 决策日志（高影响取舍）

记录格式：`Date | Owner | Topic | Options | Decision | Rationale | Follow-ups`

| Date | Owner | Topic | Options | Decision | Rationale | Follow-ups |
| ---- | ----- | ----- | ------- | -------- | --------- | ---------- |
| 2025-12-25 | wei (pending) | 色值规范（SetColor 0..1 vs 0..255） | A) 前端改为 0..1；B) 前端容忍 0..1 并转换到 0..255；C) 统一 JS API 接口为 0..255 | TBD | 待讨论 | 与 commandbook 一并更新规范和自测 |
| 2025-12-27 | wei | 画布状态默认不下发（canvasState） | A) 默认不发，按需发送；B) 默认每次发送 | A | 与 tool-first / token 成本控制一致；避免把“画布摘要”变成隐性依赖；只有在编辑/引用现有图时才需要 | 落地 tool runner：服务端 `tool_request` 兜底 + 前端回传 `TOOL_RESULT`（见 todo 007/008/014） |
| 2025-12-28 | wei | 画布感知主链路收敛为 tool runner（移除旧 API/旧机制） | A) 多轮 HTTP tool runner（后端发起工具请求，前端执行并回传）；B) 默认直传 canvasState；C) SSE/WS 双向工具桥 | A | 更通用、可扩展、稳定性更好；不需要长连接；默认不发 state 与“工具优先”一致；避免旧路由/旧 token 漂移 | 继续做 015（协议版本化/强类型），再做 017/018/019 |
| 2025-12-31 | wei | v2 开发目录与隔离策略（worktree） | A) 在 v1 目录原地重构；B) 使用 git worktree 在上一级目录创建 v2（Python+UI）；C) 新建独立 repo | B | 降低 v1/v2 依赖与配置互相污染；允许 v2 破坏兼容并快速迭代；仍共享同一 git 历史便于协作与回滚 | v2 worktree：`/Users/wei/workspaces/openkitchen/geogebra-ai-drawer-v2`；在本 worktree 的 `AGENTS.md` 明确 v2 目标结构与协作边界 |
| 2025-12-31 | wei | v2 Checkpointer：只用内存（不接真实数据库） | A) InMemorySaver；B) SQLite；C) PostgresSaver | A | 当前阶段目标是把 thread/run + interrupt/resume + streaming 跑稳；引入真实 DB 会增加配置/调试成本，且不利于快速迭代 | 先用 InMemorySaver；后续若需要 durability/部署，再按官方建议优先 PostgresSaver，并补 migration 与自测 |
| 2025-12-31 | codex-A | v2 协议对齐：schema endpoint + protocol_version | A) 只靠文档/口头对齐；B) `run_start.data.protocol_version` + `/api/schema/v2` 输出 schema | B | 降低前后端漂移风险；让 409/工具闭环等问题可快速对照定位；保持“只加不改”向后兼容 | 后续如需更严格校验再引入共享类型生成（例如从 JSON schema 生成 TS types） |
| 2025-12-31 | codex-A | v2 最小 LLM 接入：OpenAI/OpenAI-compatible | A) 直连 OpenAI SDK；B) LangChain v1 + `langchain-openai`；C) 复用 v1 的 `LLM_ENDPOINTS_JSON` router | B | 与 v2 选型（LangChain v1/LangGraph）一致；后续可扩展到更多 provider；同时支持 `OPENAI_BASE_URL` 风格的 OpenAI-compatible | 默认用 `V2_LLM_API_KEY` + 可选 `V2_LLM_BASE_URL/V2_LLM_MODEL`；也支持在无 key 时 fallback 读取 `LLM_ENDPOINTS_JSON`（仅 openai/openai-compatible）。后续再评估更完整的 model routing |
| 2025-12-31 | codex-A | v2 复用 v1 本地 `.env.local`（开发便利） | A) 手动 export `V2_LLM_*`；B) v2 自动读取本 worktree `.env.local`；C) v2 自动读取 sibling v1 `.env.local`（可用 env 覆盖） | C（含 B） | 避免重复维护 key；符合当前 v1/v2 并行开发现实；仍保持“不提交 key”的安全边界 | 新增 `V2_ENV_FILE` 作为显式覆盖；未来如引入部署环境，生产仍应走标准 env 注入而非读取本地文件 |
| 2026-01-01 | codex-A | v2 env 加载策略：默认仅使用本 worktree `.env.local` | A) 继续隐式读取 v1 sibling `.env.local`；B) 只读本 worktree `.env.local`；C) 本 worktree `.env.local` + 可选 `V2_ENV_FILE`（仅补齐缺失值） | C | 避免 v1/v2 配置互相污染（尤其是 role/model 绑定）；行为更可预测。需要复用 v1 key 时显式设置 `V2_ENV_FILE="../geogebra-ai-drawer/.env.local"` | 同步更新 `docs/self-test.md`、`docs/spec/langgraph-orchestration.md`；建议在 UI `run_start` 里核对 `llm_model` 是否符合本 worktree 配置 |
| 2025-12-31 | codex-A | v2 Rollback-first：前端差集回滚 + delete_objects 工具 | A) 只靠 LLM 生成 Delete(...)；B) 前端执行层差集回滚（硬失败）+ 后端触发 deterministic delete_objects（语义失败） | B | 回滚必须可重复、可诊断、低风险；把“无残留”从 prompt 依赖变成 deterministic 能力；减少错误残留叠加导致的二次失败 | 协议 schema 增补 delete_objects 与 exec 输出字段；自测脚本覆盖 verify→rollback→repair（`--force-repair-once`） |
| 2025-12-31 | wei | v1 移除策略（仓库内 v1 代码删除） | A) 长期保留 v1；B) 标记 legacy 但保留；C) 迁移关键能力后删除 | C | v2 为主、允许破坏兼容；避免双实现/双文档造成协作与回归负担 | 先迁移 v1 的执行兜底/repair loop/prompt 资产，再删除 v1（见 todo 129–133） |
| 2026-01-01 | wei | v2 文字输出零包装（LLM-only Text） | A) 服务端根据画板对象/命令拼装“我画了什么/怎么画”；B) 完全由 LLM 生成自然语言说明 | B | 防止“画对了但说错了/答非所问”；提升泛化能力；明确职责：只包装结构化动作闭环，不包装文字 | 更新 `docs/design/decisions.md` 与 `docs/spec/prompt-contract.md`；移除后端基于画板内容的文本模板 |
