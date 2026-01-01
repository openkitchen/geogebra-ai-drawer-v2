## v2 Prompt + LangGraph 能力完整性审计

日期：2025-12-31  
范围：`apps/api/app/*`、`apps/web/src/*`（对照 v1 的 prompt/执行/修复优势，但本次聚焦 v2 是否“可替代 v1”）  
结论（2025-12-31）：v2 的 **thread/run + SSE + interrupt/resume** 骨架已稳，但“教学画图产品”所需的 **命令生成可靠性、失败回滚与修复闭环、画布卫生/可读性兜底、场景化 prompt/playbook、多轮记忆** 当时尚不完整，仍处于 POC→MVP 过渡阶段。

更新（2026-01-01）：已补齐到 MVP：
- ✅ prompt/playbook 已接入（`prompts/v2/*` + `prompts/packs/*` + `prompts/scenarios/*` + `prompts/commandbook.json`）
- ✅ plan_node（模型 plan → `plan_update`）
- ✅ 多轮记忆（`memory_messages` + `memory_summary`，带 summarization）
- ✅ 数值测量工具 `eval_numeric`（用于语义验证补强）

---

## 1) 当前 v2 已具备的能力（✅）

### 1.1 运行骨架与可观测性
- ✅ **thread/run + SSE streaming**：`apps/api/app/main.py` + `apps/web/src/sse.ts`  
- ✅ **interrupt/resume 协议与严格一致性**：`tool_call_id/tool_name` mismatch 返回 409（`apps/api/app/main.py`）  
- ✅ **前端工具幂等去重**：以 `tool_call_id` 缓存工具结果避免重复执行（`apps/web/src/App.tsx`）  
- ✅ **协议 schema endpoint + protocol_version**：`GET /api/schema/v2`（`apps/api/app/protocol_v2.py`）  
- ✅ **thread state/history 可取证**：`GET /state` + `GET /state/history`（`apps/api/app/main.py`）  
- ✅ **本地 debug trace**：`logs/v2/run-<run_id>.jsonl`（`apps/api/app/debug_trace.py`）
- ✅ **Rollback-first（MVP）**：`exec_geogebra_commands` 返回 `created_objects` 差集；硬失败时前端自动删除新增对象；语义失败由后端触发 `delete_objects` 回滚
- ✅ **verify→repair loop（MVP）**：后端以 `canvas_diagnostics + required types` 做验证；失败→回滚→拼装 runtime_feedback→重试（有限次数）
- ✅ **画布卫生（MVP）**：前端按任务类型 best-effort 应用 preset（隐藏轴/网格、关键点标签、隐藏角度数值标签、质量告警）

---

## 2) v2 距离“产品能力完整”还缺什么（❌/⚠️）

下面按“产品不可协商项”（可读性、稳定性、可修复）逐条对照。

### 2.1 失败必须无残留（Rollback-first）— ❌
（已修复到 MVP）
- v2 已在前端工具层补齐：
  - dialog 捕获并关闭（避免阻塞）
  - 执行前后对象差集（`created_objects/deleted_objects`）
  - 硬失败自动回滚（删除本次新增对象）
  - 语义失败可由后端触发 `delete_objects` 做 deterministic 回滚
- 仍待增强：更细粒度的 per-command error（含 GeoGebra 更完整的错误文本）、更强的“仅回滚本 attempt 新增”的边界验证。

### 2.2 运行时修复闭环（repair loop）— ❌
（已修复到 MVP）
- v2 graph 已落地：`generate (full commands) → exec → get_canvas_state → verify → (delete_objects rollback + runtime_feedback) → retry`。
- 现阶段 verify 覆盖：退化（重复点/零面积/零长度）+ 关键对象类型缺失（如缺圆/缺三角形）。
- 仍待增强：语义验证（角度/约束/退化更丰富）与更可扩展的 measure 工具（已补齐最小 `eval_numeric`；见 todo）。

### 2.3 “画布卫生/可读性兜底”（deterministic allowed）— ❌
（已修复到 MVP）
- v2 已在前端工具层补齐：
  - geometry preset：隐藏轴/网格
  - showKeyLabels：显示关键点标签
  - hideAngleValueLabels：隐藏角度数值标签（只留弧）
  - validateDiagram：角对象数量上限告警、角度标签仍可见告警

### 2.4 v2 “prompt 系统”目前过于简化 — ✅（已补齐到 MVP）
- 现状（v2）：prompt 已收敛为 **file-based per-node prompts**（见 `docs/prompt-system.md`）：
  - commands 生成：`prompts/v2/command_gen_system.md` + `prompts/geogebra-constraints.md` + `prompts/packs/{draw|repair}.md` + `prompts/scenarios/*.md` + `prompts/commandbook.json`
  - final 文本：`prompts/v2/final_system.md`
  - plan：`prompts/v2/plan_system.md`
  - memory summarization：`prompts/v2/memory_summary_system.md`
- 原则：保持“文字输出零包装”，自然语言由 LLM 自己生成（见 `docs/spec/prompt-contract.md`）。

### 2.5 工具 roster 与 schema 的“单一事实源”尚未形成 — ⚠️
- 现状：
- 典型风险：schema/前端实现/后端允许名单/文档之间容易不同步，造成“看似存在但永远用不到”的假能力（例如曾出现 `eval_expression` 在 schema/前端存在，但后端不允许的错配）。
- 风险：工具能力会“看似存在但永远用不到”，并在协作中制造误解；未来新增工具会更难对齐。
- 结论：这是 **机制问题**，不是某个工具名的问题；需要明确“单一事实源”（例如以 `protocol_v2.py` + `/api/schema/v2` 为锚点）并在自测/CI 中持续校验对齐。

### 2.6 多轮“记忆/偏好”在 v2 里还不完整 — ✅（已补齐到 MVP）
- 已实现：
  - `memory_messages`：最近多轮 user/assistant 消息
  - `memory_summary`：超出阈值时自动 summarization（可配置阈值）
- 仍待增强（P1）：编辑意图（删/改/重画/复用对象）策略与更结构化的偏好持久化。

---

## 3) LangGraph 设计评估（v2）

### 3.1 结构现状（2026-01-01）
- 当前 graph 节点：
  - `ingest_node`：新用户轮次入口（重置 per-run 状态 + 记忆 summarization）
  - `plan_node`：生成内部 plan（UI 折叠展示）
  - `act_node`：主循环（command-gen → exec → refresh → verify → repair）
  - `finalize_node`：把最终答案写入多轮记忆
  - `frontend_tool_node`：发出 interrupt，等待 resume，并把结果写入 `tool_results`
（见 `apps/api/app/runtime_graph.py`）

### 3.2 与 `docs/spec/langgraph-orchestration.md` 的差距
- spec 目标态提到 `create_agent + middleware`、summarization、verification/reflection、LangSmith 等；当前实现仍是最小可用 POC。
- 这不算“错误”，但意味着：**能力完整性主要还没做**（尤其是执行失败处理与教学质量兜底）。

### 3.3 建议的最小“能力闭环”节点形态（不涉及实现细节）
为了覆盖产品核心闭环，建议把 graph 拆成可回归的小节点（并保持 deterministic 只做卫生/安全）：
1) `intent_node`：识别 draw/edit/explain、是否禁止画、是否需要清屏/复用对象  
2) `plan_node`（可选）：内部 plan（UI 折叠展示）  
3) `command_gen_node`：基于 prompts/scenarios/constraints 生成 **全量 commands**（不做增量补丁）  
4) `exec_node`：通过 interrupt 请求前端执行（返回 results + dialog + created/deleted 等结构化信息）  
5) `verify_node`：判断 success/quality/requirement（角标签、对象数上限、关键对象存在、约束成立、退化检测：重合点/零长度/零面积等）  
6) `repair_node`：失败时拼装 runtime feedback（含 rollback 信息）并回到 `command_gen_node`（有限次数）

---

## 4) v1 “优点”建议迁移清单（在删除 v1 前）

> 你已明确 v1 会被删除；因此建议把这些能力抽成 v2 的可复用资产（prompt/工具/执行兜底），而不是搬运 v1 大文件。

### 4.1 前端执行与反馈（高优先级）
- dialog 捕获 + 自动关闭（避免阻塞）
- `evalCommand=false` / “无新对象” 等高信号失败判定
- 本次 attempt 的差集回滚（Rollback-first）
- 语义验证：退化检测（点重合/零长度/零面积）、关键对象存在、关键约束成立（必要时用测量类工具）
- 画布预设（几何/代数）+ 标签/角度数值隐藏 + 质量校验（最小集合）
（均可参考 v1 `App.tsx` 的 `executeAndVerify` 相关实现）

### 4.2 Prompt 资产（高优先级）
- `prompts/system.md` 的 kid-friendly + strict contract 思路
- `prompts/geogebra-constraints.md` 的约束
- `prompts/packs/repair.md` 的“典型报错→替换”
- `prompts/scenarios/*` 的 playbook（triangle-angle-sum 等）
- `prompts/commandbook.json` 的命令示例/坑点（可做检索或压缩注入）

---

## 5) 推荐下一步（已写入 todo）

为让 v2 能在删除 v1 后仍保持“可用+可修复+可读”，建议先补齐 P0：
- **执行闭环**：把 v1 的 rollback/dialog/验证迁移到 v2 的前端工具/执行层，并把结果结构化回传给 graph。  
- **verify + repair loop**：把 `docs/spec/runtime-feedback-repair.md` 的语义真正落到 v2 graph（有限次数、全量重发、无残留），并把“语义失败”纳入 failure 判定（不是只有 evalCommand=false 才算失败）。  
- **prompt/playbook**：把 v1 prompts 资产迁移为 v2 可组合的 prompt 系统（不要散落在代码字符串里），并优先覆盖 MVP 场景。

---

## 6) 需要你确认的点（影响设计边界）

1) v2 的“命令生成”是否继续让模型在 `exec_geogebra_commands` 的 tool input 中直接产出 `commands`？  
   - 备选：拆成两步（先决策，再专门命令生成），更利于注入场景 playbook 与修复循环。  
2) `/api/schema/v2` 是否要做成“唯一事实源”（TS 自动生成/校验）目前你不确定：  
   - 建议：先把它作为 **对照与运行时校验锚点**，等事件/工具稳定后再决定是否引入生成（避免过早绑定）。  
