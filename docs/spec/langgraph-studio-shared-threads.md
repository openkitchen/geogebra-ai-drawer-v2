# LangGraph Studio 共享 Thread 快速指南

## 问题

你想在 LangGraph Studio 中重放和调试 FastAPI 产生的 thread，但发现两者使用不同的存储系统，thread 不共享。

## 解决方案

通过环境变量 `V2_CHECKPOINT_DIR` 配置 SQLite checkpointer，让两个服务器共享同一个数据库。

## 快速开始

### 1. 设置环境变量

```bash
export V2_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

**建议**：将这个环境变量添加到 `.env.local` 文件中，这样每次启动都会自动加载。

### 2. 启动两个服务器

**终端 1 - Studio Server**：
```bash
./scripts/v2_langgraph_studio.sh
```

**终端 2 - FastAPI Server**：
```bash
cd apps/api
uvicorn app.main:app --reload --port 3002
```

### 3. 工作流示例

#### 步骤 1：在 FastAPI 中创建 thread 并运行

```bash
# 创建 thread
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
echo "Thread ID: $THREAD_ID"

# 运行测试
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}'
```

#### 步骤 2：在 Studio 中打开同一个 thread

1. 打开 LangSmith Studio 网页（https://smith.langchain.com/o/.../studio）
2. 在 thread 列表中找到 `THREAD_ID`
3. 点击打开，可以看到：
   - 完整的执行过程
   - 节点流转（ingest → plan → act → ...）
   - State 变化
   - 工具调用结果

#### 步骤 3：在 Studio 中调试和测试

- **查看执行过程**：点击每个节点，查看输入输出
- **修改 prompt**：编辑 `prompts/v2/*.md` 文件
- **重新运行**：在 Studio 中点击 "Run" 按钮，使用修改后的 prompt 重新执行
- **对比效果**：观察修改前后的差异

## 重要限制

**注意**：由于 LangGraph Studio 的设计限制，它不允许 graph 使用自定义 checkpointer。Studio 会自动管理自己的持久化系统。

这意味着：
- **Studio 和 FastAPI 不能直接共享 thread 存储**
- Studio 使用自己的持久化（由 `langgraph dev` 管理）
- FastAPI 可以使用 SQLite checkpointer（如果设置了 `V2_CHECKPOINT_DIR`）

## 替代方案

### 方案 1：使用工具脚本自动创建（推荐）⭐

使用 `scripts/v2_create_studio_thread.py` 自动从 FastAPI thread 提取信息并创建 Studio thread：

```bash
# 1. 在 FastAPI 中运行测试
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}'

# 2. 自动生成 Studio 创建指令
python3 scripts/v2_create_studio_thread.py ${THREAD_ID}
```

脚本会：
- 从 FastAPI 提取 thread 信息（user_text, state 等）
- 生成详细的创建指令
- 如果 Studio API 支持，尝试自动创建

**详细文档**：`docs/spec/langgraph-studio-quick-create.md`

### 方案 2：使用 LangSmith Tracing

两个服务器都会发送 trace 到 LangSmith，你可以：
1. 在 FastAPI 中运行测试
2. 在 LangSmith 的 Tracing 页面查看完整的执行过程
3. 在 Studio 中创建新 thread 进行调试

### 方案 3：手动创建（简单场景）

对于简单的测试场景，可以直接在 Studio 中手动输入：
1. 打开 Studio
2. 点击 "New Thread"
3. 输入相同的 user_text
4. 点击 "Run"

## 优势

1. **真实场景数据**：使用 FastAPI 产生的真实用户场景，而不是在 Studio 中手动创建
2. **可视化调试**：在 Studio 中查看完整的执行过程，包括节点流转、state 变化
3. **快速迭代**：修改 prompt 后立即在 Studio 中测试，无需重新运行 FastAPI
4. **数据持久化**：Thread 数据保存在文件中，重启后不丢失

## 注意事项

1. **首次使用**：设置 `V2_CHECKPOINT_DIR` 后，需要重启两个服务器才会生效
2. **数据库位置**：SQLite 文件会在 `V2_CHECKPOINT_DIR` 目录下创建 `checkpoints.db`
3. **不需要共享时**：如果不设置 `V2_CHECKPOINT_DIR`，两个服务器使用独立的内存存储（默认行为）
4. **清理数据**：删除 `V2_CHECKPOINT_DIR` 目录即可清除所有 thread 数据

## 故障排查

### Q: 在 Studio 中看不到 FastAPI 创建的 thread？

**A**: 检查：
1. 是否设置了 `V2_CHECKPOINT_DIR` 环境变量
2. 两个服务器是否都重启了（设置环境变量后需要重启）
3. 两个服务器是否使用相同的 `V2_CHECKPOINT_DIR` 路径

### Q: Thread 数据丢失了？

**A**: 检查 SQLite 文件是否存在：
```bash
ls -la ./.langgraph-checkpoints/checkpoints.db
```

如果文件存在，数据应该还在。如果文件不存在，可能是：
- 没有设置 `V2_CHECKPOINT_DIR`
- 使用了不同的路径
- 文件被删除了

### Q: 如何清除所有 thread 数据？

**A**: 删除 checkpoints 目录：
```bash
rm -rf ./.langgraph-checkpoints
```

## 参考

- 详细文档：`docs/spec/langgraph-studio-usage.md`
- 代码实现：`apps/api/app/runtime_graph.py` 中的 `_get_checkpointer()` 函数

