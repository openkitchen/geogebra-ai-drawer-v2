# Implementation Plan: Dynamic Refinement

## Phase 1: Context Awareness & Basic Refinement (Backend Focus) [checkpoint: 5bd8559]

- [x] Task: 分析现有 API 的状态管理，确保 Canvas State 能准确传回给 LLM
- [x] Task: 更新后端 Prompt，使其能够识别针对已有对象的修改指令
- [x] Task: 为基础修改操作编写单元测试（测试覆盖率 >30%）
- [x] Task: 实现基础的微调指令转换（如移动点、更改线段长度）
- [x] Task: Conductor - User Manual Verification 'Phase 1: Context Awareness' (Protocol in workflow.md)

## Phase 2: AI Explanation & Natural Language Optimization [checkpoint: 00ebb8f]

- [x] Task: 引入“初中助教”风格的 Response Generator
- [x] Task: 在 LangGraph 工作流中加入解释生成的环节
- [x] Task: 编写针对“解释文本风格”的评估脚本或测试
- [x] Task: 优化中英文术语混用的处理逻辑
- [x] Task: Conductor - User Manual Verification 'Phase 2: AI Explanation' (Protocol in workflow.md)

## Phase 3: Frontend Integration & Polish [checkpoint: b896a42]

- [x] Task: 更新前端 Web UI，使其能流畅展示 AI 的连续操作和解释
- [x] Task: 实现前端对绘图错误的友好弹窗提醒
- [x] Task: 编写 Playwright 验收测试，模拟初中生对话场景
- [x] Task: Conductor - User Manual Verification 'Phase 3: Frontend Integration' (Protocol in workflow.md)
