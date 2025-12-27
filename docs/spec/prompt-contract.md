## Spec — Prompt Contract (LLM Output)

### 结构
LLM 输出 JSON：
- `explanation`: string，中文，简短、与图一致。
- `commands`: string[]，可执行的 GeoGebra 命令序列（或单个字符串也视为 1 条命令，但推荐数组）。
- `overlayText`（可选）：`{ corner, text }`，用于在画布四角显示固定提示文字（UI overlay，不随画布移动）。

### Tool / Commands 边界（重要）
- `commands` **只能**包含 GeoGebra 命令；**禁止**把 tool 名（如 `get_canvas_state()` / `set_corner_text(...)` / `ggb_response(...)`）混进 `commands`。
- 若模型错误地把 `get_canvas_state()` 写进 `commands`，服务端会剔除该“伪命令”，并可能在 `explanation` 里返回 `<<GET_CANVAS_STATE>>` 触发前端重试（该 token 不应展示给用户）。

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
