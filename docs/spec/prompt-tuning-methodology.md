# Prompt 调优方法论（正规流程）

## 概述

本文档描述使用 **FastAPI + LangGraph Studio** 进行 prompt 调优的正规方法。这是经过验证的、可重复的调优流程。

## 完整工作流

### 阶段 1：问题发现与复现

1. **在 FastAPI 中运行真实场景**：
   ```bash
   # 启动 FastAPI
   cd apps/api
   uvicorn app.main:app --reload --port 3002
   
   # 创建 thread 并运行测试
   THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
   curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
     -H "Content-Type: application/json" \
     -d '{"input":{"user_text":"画一个圆内接四边形"},"ui_context":{"debug":true}}'
   ```

2. **记录问题**：
   - 保存 `thread_id` 和 `run_id`
   - 记录观察到的错误行为
   - 截图或保存日志

### 阶段 2：在 Studio 中调试

1. **启动 Studio Server**：
   ```bash
   ./scripts/v2_langgraph_studio.sh --no-browser
   ```

2. **创建 Studio Thread**（使用工具脚本）：
   ```bash
   # 自动提取 FastAPI thread 信息并生成 Studio 创建指令
   python3 scripts/v2_create_studio_thread.py ${THREAD_ID}
   
   # 或者尝试自动创建
   python3 scripts/v2_create_studio_thread.py ${THREAD_ID} --auto-create
   ```

3. **在 Studio 中观察执行过程**：
   - 打开 LangSmith Studio 网页
   - 查看节点流转（ingest → plan → act → ...）
   - 查看每个节点的输入输出
   - 查看 state 变化
   - 定位问题节点

### 阶段 3：修改 Prompt

1. **定位需要修改的 prompt 文件**：
   - `prompts/v2/command_gen_system.md` - 命令生成
   - `prompts/v2/final_system.md` - 最终答案
   - `prompts/v2/plan_system.md` - 计划生成
   - `prompts/packs/draw.md` - 绘图阶段
   - `prompts/packs/repair.md` - 修复阶段

2. **修改 prompt**：
   ```bash
   # 创建备份
   cp prompts/v2/command_gen_system.md prompts/v2/command_gen_system.md.backup
   
   # 编辑 prompt
   vim prompts/v2/command_gen_system.md
   ```

3. **记录修改**：
   - 在 Git 中提交修改（带描述性 commit message）
   - 可选：打 tag（如 `prompt-v2.1.0-angle-interior`）

### 阶段 4：在 Studio 中测试修改效果

1. **重新运行 thread**：
   - 在 Studio 中点击 "Run" 按钮
   - 观察执行过程
   - 对比修改前后的差异

2. **验证效果**：
   - 检查问题是否解决
   - 检查是否引入新问题
   - 观察节点执行时间、token 消耗等指标

### 阶段 5：回归测试

1. **在 FastAPI 中运行完整测试**：
   ```bash
   # 使用相同的输入重新测试
   NEW_THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
   curl -X POST "http://127.0.0.1:3002/api/threads/${NEW_THREAD_ID}/runs/stream" \
     -H "Content-Type: application/json" \
     -d '{"input":{"user_text":"画一个圆内接四边形"},"ui_context":{"debug":true}}'
   ```

2. **对比结果**：
   - 对比修改前后的输出
   - 检查是否解决了原问题
   - 检查是否影响其他场景

3. **运行回归测试集**（如果存在）：
   ```bash
   # 运行测试用例
   python3 scripts/run_regression_tests.py --prompt-version v2.1.0
   ```

## 为什么这是正规方法？

### ✅ 符合最佳实践

1. **可重复性**：
   - 使用相同的输入可以复现问题
   - 修改后可以立即验证效果
   - 整个过程可以自动化

2. **可视化调试**：
   - Studio 提供完整的执行过程可视化
   - 可以精确定位问题节点
   - 可以观察 state 变化

3. **快速迭代**：
   - 修改 prompt 后无需重启服务（hot reload）
   - 在 Studio 中立即测试
   - 快速验证效果

4. **数据驱动**：
   - 使用真实的用户场景数据
   - 可以对比修改前后的差异
   - 可以量化效果（成功率、修复次数等）

### ✅ 符合项目设计原则

根据 `docs/spec/prompt-optimization-workflow.md`：

1. **Prompt 优先**：优先通过 prompt 解决问题，不新增代码逻辑
2. **可观测性**：使用 LangSmith/Studio 观察完整执行过程
3. **版本管理**：Prompt 修改通过 Git 管理，可追溯
4. **回归测试**：修改后运行测试确保不引入回归

### ✅ 工具支持

1. **自动化工具**：
   - `scripts/v2_create_studio_thread.py` - 自动创建 Studio thread
   - `scripts/run_regression_tests.py` - 回归测试（默认启用 LLM Judge；可用 `--no-llm-judge` 只跑 deterministic 断言）

2. **可视化工具**：
   - LangGraph Studio - 完整的执行过程可视化
   - LangSmith Tracing - 详细的 trace 数据

## 与其他方法的对比

| 方法 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **FastAPI + Studio（当前方法）** | 可视化、可重复、快速迭代 | 需要两个服务器 | ⭐⭐⭐⭐⭐ |
| 直接修改 prompt 后重启 | 简单 | 无法可视化、难以定位问题 | ⭐⭐ |
| 手动测试 | 灵活 | 不可重复、效率低 | ⭐ |
| 自动化测试脚本 | 可重复 | 缺乏可视化、难以调试 | ⭐⭐⭐ |

## 注意事项

1. **LLM 配置**：
   - 确保设置了 `V2_LLM_API_KEY` 或相关环境变量
   - 当前默认是 stub 模式（`llm_enabled: false`），不会真正调用 LLM

2. **Hot Reload**：
   - Prompt 文件修改后，LangGraph 会自动重新加载
   - 无需重启服务器

3. **Thread 共享**：
   - Studio 和 FastAPI 使用不同的存储系统
   - 使用 `scripts/v2_create_studio_thread.py` 在 Studio 中创建相同的 thread

4. **版本管理**：
   - 每次修改 prompt 前创建备份
   - 使用 Git 管理版本
   - 记录修改原因和效果

## 完整示例

```bash
# ===== 阶段 1: 启动服务 =====
# 终端 1: FastAPI + Web UI
./scripts/v2_dev.sh

# 终端 2: Studio Server
./scripts/v2_langgraph_studio.sh --no-browser

# ===== 阶段 2: 在 FastAPI 中运行测试 =====
# 创建 thread
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
echo "FastAPI Thread ID: $THREAD_ID"

# 运行测试（保存输出用于对比）
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}' \
  > /tmp/before_prompt_change.log

# ===== 阶段 3: 在 Studio 中创建 thread =====
# 生成 Studio 创建指令
python3 scripts/v2_create_studio_thread.py ${THREAD_ID} > /tmp/studio_setup.md
cat /tmp/studio_setup.md

# 按照指令在 Studio 网页中创建 thread，或使用 Studio API:
# 打开 https://smith.langchain.com/o/.../studio
# 点击 "New Thread"，输入 {"user_text": "画一个圆"}

# ===== 阶段 4: 修改 prompt =====
# 创建备份
cp prompts/v2/command_gen_system.md prompts/v2/command_gen_system.md.backup

# 编辑 prompt（例如：添加新的规则）
vim prompts/v2/command_gen_system.md

# Git 提交（可选）
git add prompts/v2/command_gen_system.md
git commit -m "prompt: add rule for circle construction order"

# ===== 阶段 5: 在 Studio 中测试修改效果 =====
# Studio 会自动重新加载 prompt（hot reload）
# 在 Studio 网页中点击 "Run" 按钮，观察执行过程
# 对比修改前后的差异

# ===== 阶段 6: 在 FastAPI 中回归测试 =====
# 使用相同的输入重新测试
NEW_THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
curl -X POST "http://127.0.0.1:3002/api/threads/${NEW_THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}' \
  > /tmp/after_prompt_change.log

# 对比结果
diff /tmp/before_prompt_change.log /tmp/after_prompt_change.log
```

## 参考

- Prompt 优化工作流：`docs/spec/prompt-optimization-workflow.md`
- Studio 使用指南：`docs/spec/langgraph-studio-usage.md`
- 快速创建 Thread：`docs/spec/langgraph-studio-quick-create.md`
