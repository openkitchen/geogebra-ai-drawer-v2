# Track Spec: Dynamic Refinement & AI Explanation

## Overview
本 Track 旨在提升 AI 在几何绘图中的“对话交互”体验，使其能够理解并执行连续的、口语化的修改指令，同时能像助教一样解释图形背后的数学意义。

## Target User
- **初中生：** 能够用最自然的语言（如“变高”、“拉长”、“移动”）控制 GeoGebra。

## Functional Requirements
1. **指令理解增强：** AI 能够识别指示代词（如“它”、“这个点”）并关联到当前图形。
2. **动态微调接口：** 支持修改现有几何对象的属性（如坐标、长度、角度）。
3. **口语化解释系统：** AI 在完成操作后，生成一段针对初中生的解释。例如：“我已经帮你把三角形拉高了，现在的面积变大了，因为底没变但高增加了。”
4. **错误反馈优化：** 当微调指令违反几何逻辑时（如“把这个三角形变成四边形”），给出友好的解释。

## Technical Implementation
- **LLM Prompting:** 更新 LangGraph 中的 prompt 系统，引入当前画布状态（Canvas State）作为上下文。
- **GeoGebra Command Generation:** 实现从属性修改指令到 GeoGebra API 调用（如 `setValue`, `setCoords`）的映射。
- **Response Formatting:** 结构化输出，区分“绘图命令”和“解释文本”。

## Success Criteria
- 用户可以说出“把 A 点往上移”且图形能即时更新。
- AI 的解释中不包含过于艰涩的大学数学术语，而是侧重初中考点。
