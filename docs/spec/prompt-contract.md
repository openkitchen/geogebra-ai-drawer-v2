## Spec — Prompt Contract (LLM Output)

### 结构
LLM 输出 JSON：
- `explanation`: string，中文，简短、与图一致。
- `commands`: string[]，可执行的 GeoGebra 命令序列（或单个字符串也视为 1 条命令，但推荐数组）。
- `overlayText`（可选）：`{ corner, text }`，用于在画布四角显示固定提示文字（UI overlay，不随画布移动）。

### Tool / Commands 边界（重要）
- `commands` **只能**包含 GeoGebra 命令；**禁止**把 tool 名（如 `get_canvas_state()` / `set_corner_text(...)` / `ggb_response(...)`）混进 `commands`。

### 通用工具调用执行方式（前端执行 tool runner）
我们采用 **前端执行工具 + 多轮 HTTP** 的通用模式（不依赖 SSE/WS）：
1) LLM 需要画布信息/前端能力时先调用工具（例如 `get_canvas_state()` / `set_corner_text(...)`）。
2) 服务端返回 `kind: "tool_request"` + `toolCalls`（不直接执行前端工具）。
3) 前端解析 `toolCalls` 并在浏览器执行，得到 `toolResults`。
4) 前端把 `toolResults` 作为 `role:"tool"` 的消息回传 `/api/chat`，继续下一轮，直到 LLM 返回最终 `ggb_response`。

目标：
- 默认不发送 `canvasState`（客户端不主动上报画布摘要）；画布信息通过 `get_canvas_state()` 的 tool runner 按需获取。
- 让前端能力（读取画布/测量/更新 UI）以 tool 形式可扩展（白名单 + schema 校验）。

### 命名与稳定性
- 点/线/角命名：使用简短、稳定的名称（A,B,C,l, angA, angB2 等），避免随机后缀。
- 避免一次生成过长的命令列表；优先“少而稳”。

### 场景约束（triangle-angle-sum）
- 只需平行线法的关键元素；不添加多余辅助点/线。
- 角对象用于画弧，生成后请隐藏数值标签：`SetLabelVisible(angX,false)`。
- 文字：包含 180° 提示，如 `Text("∠A+∠B+∠C = 180°", ...)`。

### 失败修复要求
- 收到 `RUNTIME_FEEDBACK` 后，输出**完整修正后的命令序列**（不要只给增量补丁）。
- 若提示“angle labels still visible / too many angle objects”，应减少角对象并显式隐藏角标签。***
