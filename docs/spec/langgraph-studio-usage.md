# LangGraph Studio 使用指南

## 架构说明

### 三个独立的系统

```
┌─────────────────────────────────────────────────────────────┐
│                    LangSmith (云端)                          │
│  - Tracing 服务（记录所有 LLM 调用）                        │
│  - Studio UI（网页界面）                                     │
└─────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
    │        │         │        │         │        │
    │ Studio │         │ FastAPI│         │  Web   │
    │ Server │         │ Server │         │  UI    │
    │ :2024  │         │ :3002  │         │ :3000  │
    └────────┘         └────────┘         └────────┘
```

### 1. LangGraph Studio Server（开发工具）

**作用**：可视化调试 LangGraph，观察节点流转、state 变化

**启动方式**：
```bash
./scripts/v2_langgraph_studio.sh
# 启动 langgraph dev 服务器，监听端口 2024
```

**特点**：
- 使用 `graph` 实例（无 checkpointer，由 Studio 提供）
- 独立的 thread 存储系统
- 通过 LangSmith 网页访问 UI

### 2. FastAPI Server（应用服务器）

**作用**：实际的应用后端，处理前端请求

**启动方式**：
```bash
cd apps/api
uvicorn app.main:app --reload --port 3002
```

**特点**：
- 使用 `graph_local` 实例（内存 checkpointer）
- 独立的 thread 存储系统（内存字典）
- 提供 `/api/threads`、`/api/threads/{thread_id}/runs/stream` 等 API

### 3. LangSmith（云端服务）

**作用**：
- **Tracing**：记录所有 LLM 调用、工具调用（两个服务器都会发送 trace）
- **Studio UI**：提供网页界面，连接到本地 Studio Server（端口 2024）

**配置**：
```bash
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_API_KEY="..."
export LANGCHAIN_PROJECT="geogebra-ai-drawer-v2"
```

## 问题：Thread 404 错误

**症状**：在 LangGraph Studio 中选择一个 thread 时，显示 "Error: HTTP 404: Thread with ID ... not found"

**原因**：
1. **两个独立的存储系统**：
   - LangGraph Studio（`langgraph dev`）使用自己的 checkpointer（默认可能是内存或 SQLite）
   - FastAPI（`apps/api/app/main.py`）使用内存字典 `_threads` 和 `_runs`
   - 这两个系统完全分离，thread ID 不共享

2. **数据丢失**：
   - 如果 Studio 使用内存存储，重启后 thread 会丢失
   - 或者，这个 thread 是在另一个 Studio 实例中创建的

## 解决方案

### 方案 1：在 Studio 中创建新 thread（推荐）

1. **不要使用旧的 thread ID**：在 Studio 中，点击 "New Thread" 或 "Create Thread" 创建一个新的 thread
2. **使用新 thread 测试**：在新 thread 中输入测试消息，观察 graph 执行过程

### 方案 2：配置 Studio 使用持久化存储

如果需要持久化 thread 数据，可以配置 Studio 使用 SQLite checkpointer：

1. **修改 `apps/api/app/runtime_graph.py`**：
```python
from langgraph.checkpoint.sqlite import SqliteSaver

# 为 Studio 使用 SQLite checkpointer
_studio_checkpointer = SqliteSaver.from_conn_string(":memory:")  # 或使用文件路径
graph = _builder.compile(checkpointer=_studio_checkpointer)
```

2. **或者使用环境变量**：
```bash
export LANGGRAPH_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

### 方案 3：共享 thread 存储（推荐用于调试）

**目的**：在 LangGraph Studio 中重放和调试 FastAPI 产生的 thread

**配置步骤**：

1. **设置环境变量**（使用 SQLite 共享存储）：
```bash
export V2_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

2. **重启两个服务器**：
```bash
# 终端 1：启动 Studio Server
./scripts/v2_langgraph_studio.sh

# 终端 2：启动 FastAPI Server
cd apps/api
uvicorn app.main:app --reload --port 3002
```

3. **工作流**：
   - 在 FastAPI 中创建 thread 并运行测试
   - 在 LangGraph Studio 中可以看到同一个 thread
   - 可以在 Studio 中重放、调试、修改 prompt 后重新运行

**工作原理**：
- 两个服务器使用同一个 SQLite 数据库（`./.langgraph-checkpoints/checkpoints.db`）
- Thread 数据持久化到文件，重启后不丢失
- Studio 和 FastAPI 可以访问相同的 thread

**注意事项**：
- SQLite 文件会在 `V2_CHECKPOINT_DIR` 目录下创建
- 如果不需要共享，不设置 `V2_CHECKPOINT_DIR` 即可（默认使用内存存储）

## 当前架构说明

### 两个 graph 实例

在 `apps/api/app/runtime_graph.py` 中：

```python
# `graph` 用于 LangGraph Studio（langgraph dev）
# 如果 V2_CHECKPOINT_DIR 设置，使用 SQLite checkpointer（与 FastAPI 共享）
# 否则使用内存 checkpointer（默认）
graph = _builder.compile(checkpointer=_checkpointer)

# `graph_local` 用于 FastAPI（apps/api/app/main.py）
# 使用与 `graph` 相同的 checkpointer
graph_local = _builder.compile(checkpointer=_checkpointer)
```

### 存储系统对比

| 系统 | Graph 实例 | Checkpointer | 存储位置 | 持久化 | 共享 |
|------|-----------|--------------|----------|--------|------|
| LangGraph Studio | `graph` | SQLite（如果 `V2_CHECKPOINT_DIR` 设置）<br>或内存（默认） | `V2_CHECKPOINT_DIR/checkpoints.db`<br>或内存 | 是（SQLite）<br>否（内存） | 是（SQLite）<br>否（内存） |
| FastAPI | `graph_local` | 同上 | 同上 | 同上 | 同上 |

**注意**：如果设置了 `V2_CHECKPOINT_DIR`，两个系统使用**同一个 SQLite 数据库**，thread 完全共享。

## 推荐工作流

### 场景 1：使用 LangGraph Studio 进行开发调试

**目的**：可视化调试 graph 结构、节点流转、state 变化

**步骤**：
1. **启动 Studio Server**（必须）：
```bash
./scripts/v2_langgraph_studio.sh
# 这会启动 langgraph dev 服务器，监听端口 2024
```

2. **打开 LangSmith Studio 网页**：
   - 访问 https://smith.langchain.com/o/.../studio
   - LangSmith 会自动连接到本地的 `http://127.0.0.1:2024`

3. **在 Studio 中创建新 thread**：
   - 点击 "New Thread" 创建新 thread
   - **不要使用旧的 thread ID**（可能已失效）
   - 输入测试消息，观察 graph 执行

4. **观察 graph 执行**：
   - 查看节点流转（ingest → plan → act → ...）
   - 查看 state 变化
   - 查看工具调用

**注意**：Studio Server 和 FastAPI Server 是**两个独立的服务器**，thread 数据不共享。

### 场景 2：使用 FastAPI 进行集成测试

**目的**：测试实际的应用场景、前端交互

**步骤**：
1. **启动 FastAPI Server**：
```bash
cd apps/api
uvicorn app.main:app --reload --port 3002
```

2. **启动 Web UI**（可选）：
```bash
cd apps/web
npm run dev
```

3. **创建 thread**：
```bash
curl -X POST http://127.0.0.1:3002/api/threads
```

4. **运行测试**：
```bash
curl -X POST http://127.0.0.1:3002/api/threads/{thread_id}/runs/stream \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}'
```

**注意**：FastAPI 的 thread 数据存储在内存中，重启后丢失。

### 场景 3：共享 thread 进行调试（推荐）

**目的**：在 FastAPI 中产生真实的 thread，然后在 Studio 中重放和调试

**步骤**：
1. **配置共享存储**（可选，但推荐）：
```bash
export V2_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

2. **启动 Studio Server**（终端 1）：
```bash
./scripts/v2_langgraph_studio.sh
```

3. **启动 FastAPI Server**（终端 2）：
```bash
cd apps/api
uvicorn app.main:app --reload --port 3002
```

4. **在 FastAPI 中创建 thread 并运行**：
```bash
# 创建 thread
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)

# 运行测试
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}'
```

5. **在 Studio 中打开同一个 thread**：
   - 打开 LangSmith Studio 网页
   - 在 thread 列表中找到 `THREAD_ID`
   - 点击打开，可以查看完整的执行过程、state 变化、节点流转
   - 可以修改 prompt 或 graph 结构后重新运行

**优势**：
- 使用真实的用户场景数据
- 可视化调试完整的执行过程
- 可以修改 prompt 后立即测试效果
- Thread 数据持久化，重启后不丢失

## 常见问题

### Q: 我需要启动 LangGraph Studio Server 吗？

**A**: 是的！如果你想使用 LangGraph Studio 进行调试，**必须启动 Studio Server**：
```bash
./scripts/v2_langgraph_studio.sh
```
这个服务器运行在端口 2024，LangSmith 网页会连接到它。

### Q: FastAPI 可以替代 Studio Server 吗？

**A**: 不可以。它们是**两个独立的服务器**，服务于不同目的：
- **Studio Server**：开发工具，用于可视化调试 graph
- **FastAPI Server**：应用服务器，处理实际的前端请求

### Q: 为什么 Studio 中的 thread 重启后消失了？

**A**: 如果 Studio 使用内存存储（默认），重启后数据会丢失。可以配置 SQLite checkpointer 来持久化。

### Q: 可以在 Studio 中使用 FastAPI 创建的 thread 吗？

**A**: 可以！设置环境变量 `V2_CHECKPOINT_DIR` 后，两者使用同一个 SQLite checkpointer，thread 完全共享：

```bash
export V2_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

然后重启两个服务器。这样：
- FastAPI 创建的 thread 可以在 Studio 中看到
- Studio 创建的 thread 也可以在 FastAPI 中访问
- Thread 数据持久化到文件，重启后不丢失

### Q: 如何让 Studio 和 FastAPI 共享 thread？

**A**: 设置环境变量 `V2_CHECKPOINT_DIR`，让两者使用同一个 SQLite checkpointer：

```bash
export V2_CHECKPOINT_DIR="./.langgraph-checkpoints"
```

然后重启两个服务器。这样：
- FastAPI 创建的 thread 可以在 Studio 中看到
- Studio 创建的 thread 也可以在 FastAPI 中访问
- Thread 数据持久化到文件，重启后不丢失

**推荐工作流**：
1. 在 FastAPI 中运行实际场景，产生真实的 thread
2. 在 Studio 中打开这个 thread，进行可视化调试
3. 修改 prompt 或 graph 结构后，在 Studio 中重新运行测试

### Q: LangSmith 和这两个服务器是什么关系？

**A**: LangSmith 是**云端服务**，提供：
- **Tracing**：记录所有 LLM 调用、工具调用（两个服务器都会发送 trace）
- **Studio UI**：提供网页界面，连接到本地 Studio Server（端口 2024）

两个服务器都会发送 trace 到 LangSmith，但 thread 数据存储在各自的本地服务器中。

## 参考

- [LangGraph Studio 文档](https://langchain-ai.github.io/langgraph/tutorials/studio/)
- [LangGraph Persistence](https://langchain-ai.github.io/langgraph/how-tos/persistence/)

