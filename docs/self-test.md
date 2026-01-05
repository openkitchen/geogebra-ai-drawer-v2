## GeoGebraTutor 自测清单（面向小朋友的平面几何助手）

本清单用于验证：
- **多轮聊天**（能记住上下文/偏好）
- **GeoGebra 画图**（生成可执行命令）
- **错误自愈**（能看见 GeoGebra 反馈并修复重试）
- **教学表达**（适合小朋友：短句、分步、清晰）

---

## 0) 交付/验收方式（必须：ai-web + ai-api）

> 规则：**ai-web** 或 **ai-api** 任一不通过，都不能算验收通过。

### A. 启动（推荐一键）
```bash
./scripts/v2_dev.sh
```

### B. 浏览器验收（ai-web，必须用浏览器）
- 打开：`http://127.0.0.1:3000/`
- 期望：左侧 GeoGebra 画板可交互，状态显示 `ggbApplet: ready`
- 发送一条消息（例如“画一个圆”）
- 期望：画板出现目标图形；Debug/Timeline 能看到 `interrupt → resume → tool_end → final → run_end` 的完整链路

### C. API 基础用例（ai-api，必须跑）
另开终端（确保 API 已在 `127.0.0.1:3002` 或你的 `API_PORT` 上启动）：
```bash
./scripts/v2_acceptance_api.sh
```
期望：脚本以 `OK: v2 acceptance (api) passed.` 结束并返回 0。
该脚本会在每次 run 结束后检查 `logs/v2/run-<run_id>.jsonl` 是否出现 `kind="exception"` 并打印摘要；如需“出现 exception 就直接失败”，请用：
```bash
V2_ACCEPTANCE_FAIL_ON_EXCEPTION=1 ./scripts/v2_acceptance_api.sh
```
如果出现 `401/403` / `insufficient_quota` / “没能调用语言模型”，先检查并更新 `.env.local`（参考 `docs/env.example.md`），然后重启 `./scripts/v2_dev.sh` 再重跑。

### D. 验收记录（建议）
- 在 bd issue notes / PR 描述里记录：运行的命令 + 结果（脚本输出/截图）

### E. Agent 责任（强制）
- 如果你是自动化 agent（例如 Codex），**不得只把步骤留给人类**；必须自己完成 **B + C**，并在交付信息里附上：
  - 浏览器验收的证据（截图路径/录屏/关键日志）
  - `./scripts/v2_acceptance_api.sh` 的通过输出要点

---

## v2（Python API）Smoke Test（thread/run + SSE）

目标：先验证 v2 的 **thread/run + SSE** 基线端点可跑通（默认 stub；可选开启真实 LLM）。

### 启动（本地）

也可以直接用快捷脚本（推荐）：
```bash
# web + api
./scripts/v2_dev.sh

# 只起 api（默认 3002，可用 API_PORT 覆盖）
./scripts/v2_api_dev.sh
```

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
# 可选：开启真实 LLM（当前 v2 仅支持 openai/openai-compatible）
# 推荐：复用 v1 `.env.local` 的 LLM_MODEL_ALIASES_JSON + LLM_ROLE_BINDINGS_JSON
# export V2_LLM_ROLE="main"          # 或 gemini_fast / gemini_think（OpenAI-compatible）
# export V2_LLM_FALLBACK_ROLES="fast,fallback"  # 可选：主模型失败时自动换角色重试（逗号分隔）
# （注意：若 role 指向 provider=google，目前会退回 stub，待后续补齐原生 Gemini）
# 或：显式配置 OpenAI / OpenAI-compatible
# export V2_LLM_API_KEY="..."
# export V2_LLM_MODEL="gpt-5.2-chat-latest"
# export V2_LLM_BASE_URL="https://api.vectorengine.ai/v1"  # 可选
# 或：复用 v1 的 LLM_ENDPOINTS_JSON（仅 openai/openai-compatible）
# 或：复用另一份 `.env.local`（例如 v1 的 key），但需要显式指定：
# export V2_ENV_FILE="../geogebra-ai-drawer/.env.local"
uvicorn app.main:app --port 3002
```

### Debug trace（可选，排查“第二轮不对劲/断流/409”）

当 `ui_context.debug=true` 时，后端会把每次 run 的关键过程写到本地日志文件，便于你把 run 的全过程发我定位：

- 目录：`logs/v2/`
- 文件：`logs/v2/run-<run_id>.jsonl`
- `run_id` 可从 UI 的 `Timeline -> run_start` 里直接复制（现在会展示完整 run_id）

可选环境变量：
```bash
# 关闭 trace（默认：ui_debug=true 时开启）
export V2_TRACE_ENABLED="false"

# 指定 trace 输出目录（默认：repo/logs/v2）
export V2_TRACE_DIR="/absolute/path/to/logs"
```

你在 `run-<run_id>.jsonl` 里会看到：
- `kind="llm"`：记录每次 LLM 调用的开始/结束、耗时、返回摘要（以及是否走 fallback）
- `kind="exception"`：记录 LLM 调用异常（例如 401/429/5xx/超时等）

### LangSmith tracing（可选，推荐用于 RCA）

如果你希望“看见完整的 LLM prompt/response + 调用链路”，建议接入 LangSmith：

> 注意：修改 `.env.local` 后需要重启 `uvicorn` 才会生效。
> 你也可以直接把这些变量写进 `.env.local`（后端会自动加载），不一定要手动 `export`。

```bash
# 推荐（LangChain 标准 env）
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_API_KEY="..."
export LANGCHAIN_PROJECT="geogebra-ai-drawer-v2"

# （可选）自定义 LangSmith endpoint（自建/代理时有用）
# export LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"

# 兼容写法（v2 会自动映射到 LANGCHAIN_*）
# export LANGSMITH_TRACING="true"
# export LANGSMITH_API_KEY="..."
# export LANGSMITH_PROJECT="geogebra-ai-drawer-v2"
# export LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
```

### curl 自测
```bash
curl -sS http://127.0.0.1:3002/healthz
curl -sS http://127.0.0.1:3002/api/schema/v2 | jq .protocol_version
THREAD_ID=$(curl -sS -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
curl -sS "http://127.0.0.1:3002/api/threads/${THREAD_ID}/state" | jq .
curl -sS "http://127.0.0.1:3002/api/threads/${THREAD_ID}/state/history?limit=5" | jq .
curl -sS -N -H 'Content-Type: application/json' \
  -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -d '{"input":{"user_text":"hi"},"ui_context":{"debug":true,"plan_mode":true}}'
```

### 脚本自测（可选，免手动复制 tool_call_id）
```bash
# 先启动后端（另一个终端）
uvicorn app.main:app --port 3002

# 再运行 smoke test（脚本会模拟 frontend tools 回填）
python3 scripts/v2_smoke_test.py --base-url http://127.0.0.1:3002 --user-text "画一个圆"

# （可选）强制制造一次“画布诊断失败”，验证 verify→rollback→repair loop（会触发更多次 interrupt/resume）
python3 scripts/v2_smoke_test.py --base-url http://127.0.0.1:3002 --user-text "画一个圆" --force-repair-once

# （可选）严格模式：如果 debug trace 里记录了任何 exception，则直接失败并打印摘要
python3 scripts/v2_smoke_test.py --base-url http://127.0.0.1:3002 --user-text "画一个圆" --fail-on-exception
```

继续（拿到上一步 `run_start` 里的 `run_id` 后）：
```bash
RUN_ID="<copy_from_run_start>"
curl -sS -N -H 'Content-Type: application/json' \
  -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/${RUN_ID}/resume" \
  -d '{
    "command": {
      "resume": {
        "tool_name": "<copy_from_interrupt.tool_name>",
        "tool_call_id": "<copy_from_interrupt.tool_call_id>",
        "ok": true,
        "output": { "stub": true }
      }
    }
  }'
```

如果上一步 `/resume` 又返回了新的 `interrupt`（多步工具请求），继续复制新的 `tool_name/tool_call_id` 再 `/resume` 一次即可：
```bash
curl -sS -N -H 'Content-Type: application/json' \
  -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/${RUN_ID}/resume" \
  -d '{
    "command": {
      "resume": {
        "tool_name": "<copy_from_interrupt_2.tool_name>",
        "tool_call_id": "<copy_from_interrupt_2.tool_call_id>",
        "ok": true,
        "output": { "stub": true }
      }
    }
  }'
```

（可选）触发多步 demo：把 `user_text` 改成包含 “画/绘制/draw” 的内容（例如 “画一个圆”），预期会看到：
- 第 1 次 `interrupt`: `get_canvas_state`
- 第 2 次 `interrupt`: `exec_geogebra_commands`
- 第 3 次 `interrupt`: `get_canvas_state`
最后才输出 `final` → `run_end`

（可选）校验服务端严格一致性：故意传错 `tool_call_id`，应返回 HTTP 409（JSON detail 含 expected/got）。

期望：
- `runs/stream` 能看到 SSE 的 `event:` 序列（至少 `run_start` → `budget` → `plan_update` → `token` → `tool_start` → `interrupt`），且**不会**在此处输出 `run_end`（run 被挂起等待 `/resume`）
- `thread_id/run_id` 均为 UUID 字符串（可从 `run_start` 里拿到 `run_id`）
- `run_start.data` 里包含 `protocol_version`（用于排障；UI 可忽略）
- `run_start.data` 里包含 `llm_enabled`（true/false），并可选包含 `llm_model/llm_base_url`（仅用于排障；UI 可忽略）
- `budget` 至少包含 `tool_calls_used/tool_calls_limit`，若开启真实 LLM 还应包含 `model_calls_used/model_calls_limit`
- `resume` 可能需要多次（直到不再出现 `interrupt`）；每次 `resume` 至少包含 `tool_end`，并伴随 `budget`；最终一次会输出 `final` → `run_end`
- `state` 返回里包含 `graph.values/graph.next/graph.checkpoint_id`（用于 debug/time-travel）
- `state/history` 返回里包含最近的 checkpoints（用于回放与 RCA）

### （可选）脚本自测（自动跟随 interrupt→resume）

前置：服务已按上文启动在 `127.0.0.1:3002`。

```bash
python scripts/v2_smoke_test.py --base-url http://127.0.0.1:3002 --user-text "画一个圆"
```

期望：命令输出包含 `interrupt`/`resume` 多轮流程，并以 `OK: completed after ... resume(s).` 结束。

### UI 自测（SSE 过程不会消失）
```bash
cd apps/web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:3000/`：
- 期望：页面左侧显示 GeoGebra Classic 画板，状态显示 `ggbApplet: ready`；可用工具栏手动创建点/线
- 发送一条消息（例如 “hi from ui”）
- 期望：assistant bubble 显示最终文本；`Debug events` 可展开看到包含 `interrupt` 与后续 `/resume` 的 `tool_end/final/run_end`，并且 **进展/工具过程不会在结束后消失**
- 期望：`Trace info` 默认折叠；展开后 `Copy run_id/thread_id` 会复制带 key 前缀的整行（例如 `run_id: <uuid>`）
- 期望：`Timeline`（默认展开）能看到 `tool_use get_canvas_state` 与 `tool_result get_canvas_state`，且 output 摘要里能看到 `objects=<n>`（先手动在画板上创建至少 1 个对象再测更直观）
- 期望：若触发 `/resume` HTTP 409（tool_call_id/tool_name mismatch），UI 会在 `Timeline/Debug events` 里记录 `client_error`（含 expected/got），便于排障

---

### 运行前检查
- 后端 `/api/providers` 能返回至少一个 endpoint（例如 `packy-glm47` / `kimi` 等）。
- 前端模型下拉里能选到 **GLM 4.7 (Packy)**，并能看到 **Kimi**。
- 页面右上角 `Debug` 可打开：
  - Debug 面板能切换 **View Chat / View Debug**（DebugPanel 不再与主对话割裂）。
  - 能看到 `window.__ggbDebugLog`（用于验证“AI有没有看到错误并重试/回滚/降级”）。

### 本轮测试要求（2025-12-25）
- 主力模型：**GLM 4.7 (Packy)**（endpointId=`packy-glm47`）。
- 降级策略：当 **GLM 后端报错/超时** 时，**优先 fallback 到 Kimi**（usedEndpointId 应显示为 `kimi`）。

### 本轮执行记录（2025-12-28）
- 已验证：浏览器主路径可用（画圆后追问“有哪些对象”会触发 `get_canvas_state` 的 tool runner：`kind=tool_request → TOOL_RESULT → kind=final`，运行记录可见 `llmTurns`）。
- 已验证：`npm run build` 通过。

---

## 验收标准（Pass/Fail）

### A. 基础聊天 + 画图
- A1：能解释概念并画示意图（commands 非空）  
- A2：只解释不画图时（commands 为空）也能工作  
- A3：命令执行后画板确实出现目标图形  
- A4：聊天解释文本保留换行（分步编号不会粘连成一段）  
- A5：绘图步骤默认折叠；展开后可查看命令并一键复制  
- A6：发送后未返回时，对话区显示 `thinking...`（而不仅是输入框 placeholder/按钮转圈）  

### B. 多轮对话记忆
- B1：第二轮能复用上一轮对象/设定（例如“把刚才的圆加半径标注/再加切线”）  
- B2：能记住用户偏好（例如“线太多，看不懂 → 简化/加粗关键线”）  

### C. GeoGebra 自愈（关键）
- C1：出现 Unknown command / Illegal argument / Undefined variable 时，能自动重试并修复  
- C2：自愈时会把错误反馈放进 `tool` 消息（可在 Debug log 看到）  
- C3：不会无限循环；最多重试 N 次并给出可理解的失败说明  
- C4：当模型走 tool-calling 策略时，服务端响应包含 `toolCalls`，且 Debug 面板可查看 provider 原始 tool calls  
- C5：`commands` 中不会出现 tool 名（如 `get_canvas_state()`）；若出现，服务端会剔除并触发正确的“获取画布状态”路径（不执行伪命令）。  
- C6：对话中每条 assistant 回复包含“运行记录（默认折叠）”，可查看 toolCalls / 重试次数 / rollback 等信息（用于现场排障，不影响小朋友主体验）。  
- C7：当模型需要画布信息时，应先调用 `get_canvas_state`，并触发 **tool runner**：服务端返回 `kind=tool_request`，前端执行后回传 `TOOL_RESULT`，再获得最终 `kind=final` 的绘图/回答（运行记录里可见 llmTurns）。  

### D. 面向小朋友的教学风格
- D1：中文短句、分步骤（编号/分点），避免长段落堆砌  
- D2：解释和图形一致（解释提到的点/线在图中能找到）  
- D3：出现术语（如“同位角/内错角”）会给 1 句通俗解释  

### E. 配置与模型健壮性
- E1：`.env.local` 里改 `LLM_ENDPOINTS_JSON` 后，模型列表随之变化  
- E2：选定 `packy-glm47` 时，若该 endpoint 后端错误/超时，应自动 fallback 到 `kimi`（Debug log 里可看到 `usedEndpointId` 切换）  
- E3：DebugPanel 的 Quick Prompt Runner 走主聊天链路（同一套 history + repair loop），不再是独立调用  
- E4：客户端不主动发送 `canvasState`；当用户“引用/修改现有图”时，应优先走 `get_canvas_state` 的 tool runner（服务端 `kind=tool_request` → 前端回传 `TOOL_RESULT` → `kind=final`）。  
- E5：可通过 `set_corner_text`/`overlayText` 在画布四角展示固定说明文字（不随画布平移缩放），用于提示作图关键步骤。  

---

## 测试用用户提示词（建议按顺序跑）

### 1) 概念 + 示意图（基础）
1. “什么是勾股定理，解释，然后画一个示意图”  
2. “什么是等腰三角形？画一个等腰三角形，并解释底角为什么相等”  
3. “什么是垂直平分线？请画出一条线段的垂直平分线，并解释用途”  
4. “画一个圆，并说明圆心、半径、直径分别是什么”（注意：本环境可能不支持 Label 命令，应靠对象命名/构造说明）  
5. “在 GeoGebra Classic 里画出函数 y = sin(x) * x（不要用 FunctionGraph）”

### 2) 作图题（中等）
1. “过直线外一点，如何做平行线？给出两种方法，并画示意图”  
2. “过直线外一点作垂线，并画示意图”  
3. “作一个三角形 ABC，作 BC 的中点 M，并连接 AM”  
4. “已知两点 A、B，作以 AB 为直径的圆，并标出圆心”  

### 3) 证明题（中等→偏难）
1. “如何证明三角形的内角和是 180 度？你可以画图，然后给我一个说明”  
2. “在△ABC中，AB=AC，证明∠B=∠C，并画出示意图。”  
3. “证明：圆周角定理（同弧所对圆周角相等）。画示意图并解释关键步骤。”  

### 4) 多轮追问（必须通过）
（先发 4.1，再发 4.2…，观察是否记住上下文）  
1. 4.1 “画一个三角形 ABC（随便画）”  
2. 4.2 “把刚才的三角形画出 BC 的垂直平分线，并说明它与外接圆圆心的关系”  
3. 4.3 “把外接圆也画出来（如果你能），并解释为什么圆心在垂直平分线上”  
4. 4.4 “你知道我画了什么吗？”（期望触发 `get_canvas_state` tool call，并走 tool runner：先 `tool_request` 再 `final`；且不会把 tool 名写进 `commands`）  

### 5) 错误自愈（故意让它错）
1. “用 RegularPolygon 画一个正方形。”（本环境会 Unknown command，应能自愈改用可用构造）  
2. “把点 A 的标签显示出来。”（如果模型输出 `Label(A,\"A\")`，应触发 bridge 或自愈）  
3. “清屏”（应生成 Delete(...) 序列并执行成功；或至少不报错）  

#### 5.x 失败回滚（避免“错误残留叠加”）
（目标：第一次失败后产生的碎片对象应被清理，再重试时画布不叠加旧错误）
1. “先用 RegularPolygon 画正方形（会失败），然后你要修正并重新画。”  
   - 期望：重试前清理掉失败尝试创建的对象（A,B,... 辅助线/点），最终只保留正确构造需要的对象。  
2. “你刚才画错了：请把错误图形删掉，再画一个正确的。”  
   - 期望：AI 能根据 `Current objects: ...` 删除错误对象；即使 AI 没删干净，前端也会对失败尝试进行自动回滚。  
3. “连续两次纠错：第一次错用 Square(...)，第二次错用 Label(...)，请都修正。”  
   - 期望：每次失败后都不会留下叠加残留；Debug log 可看到 `Rolled back: ...`。  

### 6) 更复杂的综合题（探索性）
1. “画一个圆与一条直线，并作出它们的交点，说明为什么最多有两个交点。”  
2. “画一个梯形，并说明它的中位线性质（平行且等于两底和的一半）。”  
3. “我不懂，线太多了：请把辅助线变浅，把关键线加粗，并用步骤解释。”  

### 7) Commandbook 签名纠正（新增，需开启提示注入）
1. **Text 参数纠正**：提示 “在 (0.2,0.2) 处放一个文本 α”，预期模型改用 `Text(\"α\", (0.2,0.2))` 而非用 x,y 两数。  
2. **正多边形别名纠正**：提示 “用 RegularPolygon 画一个五边形”，预期改写为 `Polygon(A,B,5)` 并创建 A,B。  
3. **色值范围纠正**：提示 “把线段 a 设成天蓝色 (0,0.5,1)”，预期转换为 0-255 `SetColor(a,0,128,255)`。  
4. **线型参数纠正**：提示 “把直线 f 变成虚线”，预期使用 `SetLineStyle(f,1)`。  
5. **角度顶点顺序纠正**：提示 “求角 BAC 的度数”，预期使用 `Angle(B,A,C)` 而非 `Angle(A,B,C)`。  
6. **三角形内角标注（防外角）**：提示 “画一个钝角三角形并标出三个内角”，预期使用 `InteriorAngles(Polygon(A,B,C))` 或确保点序使 Angle 结果 <180°，不得出现外角标注。
7. **钝角判定一致性**：提示 “钝角在 A 的三角形，指出哪个角是钝角”，预期坐标选择保证 ∠A>90°（如 A=(0,0), B=(4,0), C=(-1,1.5)），并只声明可确认的钝角；不得随口说“∠A 是钝角”而图中非钝角。
8. **经过指定点的钝角三角形**：提示 “给我画一个过点 (1,1) 的钝角三角形”，预期把该点设为钝角顶点（如 A=(1,1), B=(5,1), C=(0,3)），保证三角形经过该点且钝角确实>90°，不要遗漏用户给定的点。
9. **钝角顶点指定为 B 且含用户点**：提示 “钝角在 B，经过点 (2,0) 画一个钝角三角形”，预期 B=(2,0) 为钝角顶点，其他点生成确保 ∠B>90° 且包含该点；如条件不够应先澄清。

---

## 结果记录模板

建议把每条用例记录为：
- **Prompt**：…  
- **Expected**：…  
- **Actual**：…  
- **Pass/Fail**：…  
- **Notes**：…（如：GeoGebra 报错内容、是否触发重试、是否简化解释）  

---

## 当前基线结果（2025-12-24）

说明：以下为我在浏览器中手动跑过的代表性用例结果（以 **Kimi** 为主）。

### 已通过（Pass）
- **1.1 勾股定理示意图**：能给中文解释 + 生成可执行命令，画板出现直角三角形与构造示意。  
- **2.1 过线外一点作平行线**：能给两种方法说明，并用“双垂线法”画出示意图。  
- **3.1 三角形内角和 180°**：能用平行线证明思路 + 画出示意图（通过 A 作 BC 的平行线）。  
- **3.2 等腰三角形底角相等（示意）**：能画出等腰三角形并解释性质。  
- **E1 配置与模型列表**：后端读取 `.env.local` 的 `LLM_ENDPOINTS_JSON` 后，`/api/providers` 能返回 Kimi/Gemini；前端下拉能显示对应选项。  

### 部分通过（Partial）
- **C1/C2 自愈**：对“Unknown command / evalCommand=false”的错误反馈链路已具备，且可在 Debug log 看到错误上下文；但复杂构造（例如需要较多步骤的证明/作图）仍可能需要进一步增强策略与重试上限调参。  

### 仍需补测（Not tested yet）
- **4) 多轮追问链路**（同一张图的“复用对象”能力）：建议跑 4.1→4.3 全链路验证。  
- **5.1 RegularPolygon 正方形替代构造**：需要验证“Unknown command”时能自动改用可用命令（或最小可行替代）。  
- **5.x 失败回滚（避免错误残留叠加）**：需要验证失败后是否自动回滚（Debug log 中出现 `Rolled back: ...`），以及重试后画布不叠加旧错误。  
- **6) 综合题**：如“中位线性质”“把辅助线变浅/关键线加粗”等更复杂的教学交互。  

### 结论（当前是否达到期望？）
- **核心能力已达到**：多模型配置（env）、结构化输出、GeoGebra 执行反馈、自愈闭环、提示词体系、Debug 可观测性。  
- **离“给小朋友稳定使用”还差一段**：需要把“多轮复用对象”“更复杂题型策略”“风格控制（更短更清晰）”“失败时的降级解释与继续教学”进一步做实并补测覆盖。  
