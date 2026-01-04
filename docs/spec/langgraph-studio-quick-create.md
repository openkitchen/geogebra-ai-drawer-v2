# 快速在 Studio 中创建 Thread（从 FastAPI）

## 问题

在 FastAPI 中运行测试后，想在 Studio 中调试，但不想手动输入所有参数。

## 解决方案

使用工具脚本 `scripts/v2_create_studio_thread.py` 自动提取 FastAPI thread 信息并创建 Studio thread。

## 快速使用

### 方法 1：自动创建（如果 Studio API 支持）

```bash
# 1. 在 FastAPI 中创建 thread 并运行
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}'

# 2. 自动在 Studio 中创建相同的 thread
python3 scripts/v2_create_studio_thread.py ${THREAD_ID} --auto-create
```

### 方法 2：生成指令（推荐）

```bash
# 1. 在 FastAPI 中创建 thread 并运行（同上）

# 2. 生成创建指令
python3 scripts/v2_create_studio_thread.py ${THREAD_ID} > studio_instructions.md

# 3. 查看指令并按照步骤在 Studio 中创建
cat studio_instructions.md
```

## 完整示例

```bash
# 终端 1：启动 FastAPI
cd apps/api
uvicorn app.main:app --reload --port 3002

# 终端 2：启动 Studio
./scripts/v2_langgraph_studio.sh --no-browser

# 终端 3：运行测试并创建 Studio thread
# 创建 thread
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
echo "FastAPI Thread ID: $THREAD_ID"

# 运行测试
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}' \
  > /tmp/fastapi_run.log

# 生成 Studio 创建指令
python3 scripts/v2_create_studio_thread.py ${THREAD_ID} > /tmp/studio_instructions.md
cat /tmp/studio_instructions.md

# 按照指令在 Studio 中创建 thread
```

## 脚本选项

```bash
python3 scripts/v2_create_studio_thread.py --help

选项：
  thread_id              FastAPI thread ID
  --fastapi-url URL     FastAPI base URL (default: http://127.0.0.1:3002)
  --studio-url URL      Studio base URL (default: http://127.0.0.1:2024)
  --output FILE         输出文件路径 (default: stdout)
  --auto-create         尝试通过 API 自动创建 Studio thread
```

## 输出示例

脚本会生成包含以下信息的指令：

1. **FastAPI Thread 信息**：
   - Thread ID
   - User Text（用户输入）
   - 创建时间

2. **Studio 创建步骤**：
   - 打开 Studio 网页
   - 点击 "New Thread"
   - 输入提取的 user_text
   - 点击 "Run"

3. **API 调用示例**（如果 Studio API 支持）：
   - curl 命令示例

4. **Thread State 摘要**：
   - Graph state 信息（用于调试）

## 工作流建议

### 推荐工作流

1. **在 FastAPI 中运行真实场景**：
   ```bash
   # 使用真实的用户输入和场景
   curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
     -H "Content-Type: application/json" \
     -d '{"input":{"user_text":"画一个圆内接四边形"},"ui_context":{"debug":true}}'
   ```

2. **提取信息到 Studio**：
   ```bash
   python3 scripts/v2_create_studio_thread.py ${THREAD_ID} > studio_setup.md
   ```

3. **在 Studio 中调试**：
   - 按照 `studio_setup.md` 中的步骤创建 thread
   - 观察执行过程
   - 修改 prompt 后重新运行
   - 对比效果

### 快速调试循环

```bash
# 一键脚本：运行测试 + 生成 Studio 指令
THREAD_ID=$(curl -s -X POST http://127.0.0.1:3002/api/threads | jq -r .thread_id)
curl -X POST "http://127.0.0.1:3002/api/threads/${THREAD_ID}/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{"input":{"user_text":"画一个圆"},"ui_context":{"debug":true}}' > /dev/null
python3 scripts/v2_create_studio_thread.py ${THREAD_ID}
```

## 故障排查

### 问题：无法连接到 FastAPI

**检查**：
```bash
curl http://127.0.0.1:3002/healthz
```

**解决**：确保 FastAPI 正在运行

### 问题：无法提取 user_text

**原因**：Thread 可能还没有运行，或者 state 为空

**解决**：确保 thread 已经执行过至少一次 run

### 问题：Studio API 不支持自动创建

**解决**：使用 `--auto-create` 失败时，脚本会自动生成手动创建指令

## 参考

- Studio 使用指南：`docs/spec/langgraph-studio-usage.md`
- 共享 Thread 指南：`docs/spec/langgraph-studio-shared-threads.md`

