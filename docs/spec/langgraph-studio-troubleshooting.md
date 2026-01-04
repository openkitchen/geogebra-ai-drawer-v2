# LangGraph Studio 故障排查

## 问题 1：Studio 启动失败 - "custom checkpointer" 错误

### 错误信息
```
ValueError: Heads up! Your graph 'graph' from 'None' includes a custom checkpointer...
```

### 原因
LangGraph Studio 不允许 graph 使用自定义 checkpointer。Studio 会自动管理持久化。

### 解决方案
确保 `apps/api/app/runtime_graph.py` 中的 `graph` 不使用 checkpointer：

```python
# ✅ 正确：Studio 的 graph 不使用 checkpointer
graph = _builder.compile()

# ✅ 正确：FastAPI 的 graph_local 可以使用 checkpointer
graph_local = _builder.compile(checkpointer=_checkpointer)
```

## 问题 2：v2_dev.sh 启动失败

### 检查步骤

1. **检查脚本权限**：
```bash
chmod +x scripts/v2_dev.sh scripts/v2_api_dev.sh scripts/v2_web_dev.sh
```

2. **检查依赖**：
```bash
# 检查 uv
which uv

# 检查 node
which node
which npm

# 检查 Python
cd apps/api
uv run python --version
```

3. **检查端口占用**：
```bash
lsof -i :3002  # FastAPI
lsof -i :3000  # Web UI
lsof -i :2024  # Studio
```

4. **手动启动测试**：
```bash
# 终端 1：FastAPI
cd apps/api
uv run uvicorn app.main:app --reload --port 3002

# 终端 2：Web UI
cd apps/web
npm run dev

# 终端 3：Studio（可选）
./scripts/v2_langgraph_studio.sh --no-browser
```

## 问题 3：Studio 和 FastAPI 不能共享 thread

### 原因
LangGraph Studio 不允许 graph 使用自定义 checkpointer，所以不能直接共享 SQLite 数据库。

### 解决方案
使用 LangSmith Tracing 查看 FastAPI 的执行过程，然后在 Studio 中创建新 thread 进行调试。

## 问题 4：端口冲突

### 错误信息
```
Address already in use
```

### 解决方案
```bash
# 查找占用端口的进程
lsof -i :3002
lsof -i :3000
lsof -i :2024

# 停止进程
kill <PID>

# 或者使用不同的端口
export API_PORT=3003
export WEB_PORT=3001
export LANGGRAPH_PORT=2025
```

## 问题 5：依赖缺失

### 错误信息
```
ModuleNotFoundError: No module named 'langgraph'
```

### 解决方案
```bash
cd apps/api
uv sync  # 或 uv pip install -e .
```

## 问题 6：langgraph.json 配置错误

### 检查配置
```bash
python3 scripts/v2_generate_langgraph_json.py --check
```

### 重新生成配置
```bash
python3 scripts/v2_generate_langgraph_json.py
```

## 快速测试

### 测试 Studio
```bash
./scripts/v2_langgraph_studio.sh --no-browser
# 应该看到：API: http://127.0.0.1:2024
```

### 测试 FastAPI
```bash
curl http://127.0.0.1:3002/healthz
# 应该返回：{"ok":true}
```

### 测试 Web UI
```bash
curl http://127.0.0.1:3000
# 应该返回 HTML 页面
```

## 常见错误日志

### Studio 启动成功标志
```
INFO: Application started up in 0.702s
🚀 API: http://127.0.0.1:2024
```

### FastAPI 启动成功标志
```
INFO:     Uvicorn running on http://127.0.0.1:3002
INFO:     Application startup complete.
```

### Web UI 启动成功标志
```
VITE v6.4.1  ready in 251 ms
➜  Local:   http://127.0.0.1:3000/
```
