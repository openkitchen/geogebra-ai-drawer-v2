## Spec — Runtime Feedback & Repair Loop

### 目标
执行失败时做到“无残留可修复”：回滚本次新增对象 → 把错误和现有对象列表反馈给模型 → 重新生成完整指令。

### 契约
- 最大重试次数：5 次。
- 失败后必须回滚：比较执行前后的对象列表，删除新增对象。
- 反馈格式（发送给 LLM 的 `RUNTIME_FEEDBACK` 文本示例）：
  - `Command failed: "..." (Object "...")`
  - `GeoGebra dialog: "..."`
  - `Rolled back: A1, B1.`
  - `Current objects: A, B, C, l, ...`
- 不要让模型“增量补丁”旧命令，要求其输出**完整的、可直接执行的全量命令序列**。

### UI/执行侧要做的事
- 执行前：记录对象列表。
- 执行中：捕获 `evalCommand` false、异常、GeoGebra 弹窗文本。
- 执行后（失败）：按差集删除新增对象；构造反馈文本；再次调用 LLM。
- 执行后（成功）：应用展示层卫生（如隐藏角度数值标签、显示关键点标签）。

补充（v2 落地约定）：
- 硬失败：前端工具 `exec_geogebra_commands` 可直接自动回滚本次 `created_objects`。
- 语义失败：后端可触发前端工具 `delete_objects` 做 deterministic 回滚（避免让 LLM 自己拼 Delete 命令）。

### 何时终止
- 达到重试上限仍失败：向用户返回“修正失败”并保留干净画面（已回滚）。***
