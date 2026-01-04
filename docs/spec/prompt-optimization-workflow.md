# Spec — Prompt & LangGraph 优化工作流（可重复、可自动化）

> 目标：建立一套可重复的调优流程，优先通过系统提示词解决问题，必要时配合 LangGraph 节点或独立 agent，并使用 LangSmith 进行数据驱动的分析和测试。

---

## 1. 当前调优流程的痛点

### 1.1 现状
- **手动迭代**：发现问题 → 改 prompt → 手动测试 → 看日志 → 再改，循环依赖人工判断
- **缺乏量化**：没有 A/B 对比、成功率统计、回归检测机制
- **定位成本高**：需要人工从 LangSmith/trace 日志中找根因，效率低
- **版本管理混乱**：prompt 变更没有版本化，难以回滚和对比
- **测试不系统**：没有标准化的测试用例集，每次改完不知道是否引入回归

### 1.2 目标
- **可重复性**：所有调优步骤可自动化、可版本化
- **数据驱动**：用 LangSmith/trace 数据驱动决策，而不是凭感觉
- **渐进式优化**：先做低成本、高收益的自动化，再考虑复杂方案
- **人工审核保留**：AI 只负责“建议”，不自动改代码

---

## 2. 调优方法论（优先级顺序）

### 2.1 阶段 1：Prompt 调优（优先）

**原则**：能用 prompt 解决的，不新增代码逻辑。

**流程**：
```
问题发现 → 收集失败案例 → 分析根因 → 修改 prompt → 回归测试 → 评估效果
```

**可重复性保障**：
- **失败案例收集**：自动从 LangSmith/trace 提取失败 run
- **Prompt 版本管理**：Git 管理，每次修改打 tag（如 `v2.1.0-angle-interior`）
- **回归测试集**：维护 `test_cases/` 目录，每个问题对应一组测试用例

**适用场景**：
- 行为纠正（如“生成内角而非反角”）
- 规则注入（如“样式命令白名单约束”）
- 输出格式约束（如“严格证据绑定”）

**不适用场景**：
- 需要确定性逻辑（如“失败后强制查 KB”）
- 需要状态管理（如“多轮修复循环计数”）

### 2.2 阶段 2：LangGraph 节点调优（Prompt 不够时）

**原则**：当 prompt 无法稳定解决问题，或需要确定性逻辑时，增加 LangGraph 节点。

**流程**：
```
问题归类 → 判断是否需要确定性节点 → 设计新节点/边 → 实现 → 测试
```

**可重复性保障**：
- **问题归类**：建立问题分类（如 `angle_reflex`、`command_syntax`、`canvas_hygiene`）
- **节点模板**：常见节点模式（如 `preflight_canvas`、`kb_lookup_on_failure`）可复用
- **图版本管理**：LangGraph 图结构也版本化（通过代码版本控制）

**适用场景**：
- 需要强制执行的步骤（如“必须先 `get_canvas_state` 才能编辑”）
- 失败后的确定性修复策略（如“命令失败后强制查 KB 再重试”）
- 预算与止损逻辑（如“同类失败不超过 N 次”）

**不适用场景**：
- 可以用 prompt 约束解决的语义问题
- 一次性特例（应该用 prompt 的场景模板解决）

### 2.3 阶段 3：独立 LangGraph Agent（复杂问题）

**原则**：当问题需要独立的子图逻辑，或需要隔离测试时，创建专用 agent。

**流程**：
```
问题隔离 → 设计专用子图 → 集成到主图 → 路由规则
```

**可重复性保障**：
- **子图模块化**：每个专用 agent 是独立子图，可单独测试
- **路由规则**：通过 `IntentMiddleware` 或确定性条件边路由

**适用场景**：
- 复杂场景需要独立流程（如“证明题专用 agent”）
- 需要隔离测试的问题域（如“解析几何 vs 纯几何”）
- 需要独立预算/重试策略的场景

---

## 3. LangSmith 的使用方法

### 3.1 当前能力

**Trace 回放**：
- 每个 run 的完整链路（LLM 调用、工具执行、节点流转）
- 可按 `thread_id`/`run_id` 回放

**搜索过滤**：
- 按失败类型、时间范围、项目搜索
- 按 `verification.failed`、`tool_end.ok=false` 过滤

**项目隔离**：
- 不同环境用不同 project（如 `geogebra-ai-drawer-v2-dev`、`geogebra-ai-drawer-v2-prod`）

### 3.2 失败案例自动收集

**目标**：从 LangSmith 自动提取失败 run，按类型聚类，生成报告。

**实现方式**：
```python
# 伪代码示意
def collect_failure_cases(
    project: str,
    start_time: datetime,
    end_time: datetime
) -> list[dict]:
    """从 LangSmith 自动提取失败模式"""
    runs = langsmith.list_runs(
        project_name=project,
        start_time=start_time,
        end_time=end_time,
        filter='eq(status, "error") OR eq(feedback.score, 0)'
    )
    
    failures = []
    for run in runs:
        trace = langsmith.get_trace(run.id)
        for span in trace.spans:
            if span.kind == "verification" and not span.data.get("ok"):
                failures.append({
                    "run_id": run.id,
                    "thread_id": run.extra.get("thread_id"),
                    "type": "verification_failed",
                    "issue": span.data.get("details"),
                    "context": extract_context(span),
                    "timestamp": run.start_time
                })
            elif span.kind == "tool" and not span.data.get("ok"):
                failures.append({
                    "run_id": run.id,
                    "type": "tool_failed",
                    "tool_name": span.name,
                    "error": span.data.get("error"),
                    "context": extract_context(span),
                    "timestamp": run.start_time
                })
    
    return categorize_failures(failures)
```

**输出格式**：
- JSON 报告：`failures-{date}.json`
- 分类统计：按失败类型（`angle_reflex`、`command_syntax`、`canvas_hygiene` 等）聚类
- Trace 链接：每个失败案例包含 LangSmith trace URL

### 3.3 根因分析（AI 辅助）

**目标**：用 LLM 分析失败 trace，输出结构化建议（不自动改代码）。

**实现方式**：
```python
# 伪代码示意
def analyze_failure_root_cause(
    failure_case: dict,
    trace_data: dict,
    current_prompts: dict
) -> dict:
    """用 LLM 分析失败根因，并给出 prompt/LangGraph 修改建议"""
    analysis_prompt = f"""
    分析以下失败案例，判断根因是：
    1) Prompt 不够明确（需要改 prompt）
    2) 需要确定性节点（需要改 LangGraph）
    3) 需要独立 agent（需要新子图）
    4) 数据/环境问题（不需要改代码）
    
    失败信息：{json.dumps(failure_case, indent=2)}
    Trace 上下文：{json.dumps(trace_data, indent=2)}
    当前 prompt 版本：{current_prompts.get('version')}
    
    请输出 JSON：
    {{
        "recommendation": "update_prompt" | "add_node" | "add_agent" | "no_change",
        "confidence": 0.0-1.0,
        "target_file": "prompts/v2/command_gen_system.md" (if update_prompt),
        "suggested_change": "...",
        "rationale": "..."
    }}
    """
    return llm_call(analysis_prompt, model="gpt-4")
```

**输出格式**：
- 结构化建议 JSON
- 人工审核后应用（不自动改代码）
- 记录审核结果（采纳/拒绝/修改后采纳）

### 3.4 Prompt A/B 测试

**目标**：对同一组测试用例，分别用两个 prompt 版本跑，对比效果。

**实现方式**：
```python
# 伪代码示意
def ab_test_prompt(
    prompt_variant_a: str,
    prompt_variant_b: str,
    test_cases: list[dict],
    project_a: str,
    project_b: str
) -> dict:
    """对同一组测试用例，分别用两个 prompt 版本跑，对比结果"""
    results_a = run_test_suite(
        prompt_variant_a,
        test_cases,
        langsmith_project=project_a
    )
    results_b = run_test_suite(
        prompt_variant_b,
        test_cases,
        langsmith_project=project_b
    )
    
    return {
        "variant_a": {
            "success_rate": results_a.success_rate,
            "avg_repair_count": results_a.avg_repair_count,
            "avg_token_usage": results_a.avg_token_usage,
            "langsmith_project": project_a
        },
        "variant_b": {
            "success_rate": results_b.success_rate,
            "avg_repair_count": results_b.avg_repair_count,
            "avg_token_usage": results_b.avg_token_usage,
            "langsmith_project": project_b
        },
        "improvement": {
            "success_rate_delta": results_b.success_rate - results_a.success_rate,
            "repair_count_delta": results_b.avg_repair_count - results_a.avg_repair_count
        }
    }
```

**测试用例格式**：
```json
{
  "id": "test-angle-interior-001",
  "user_text": "画一个圆内接四边形，并测量对角",
  "expected_verification": {
    "has_quadrilateral": true,
    "angles_are_interior": true,
    "angle_sum_equals_180": true
  },
  "expected_commands_contain": ["Angle(", "Polygon("],
  "expected_commands_not_contain": ["Angle(B, C, D)"]
}
```

**对比指标**：
- 成功率（`verification.ok` 通过率）
- 平均修复次数（`attempt` 平均值）
- 命令执行成功率（`exec_geogebra_commands.ok` 通过率）
- Token 消耗（成本对比）
- 平均延迟（性能对比）

### 3.5 数据集构建（用于持续优化）

**目标**：从 LangSmith 导出失败/成功案例，用于 prompt 优化和回归测试。

**实现方式**：
```python
# 伪代码示意
def export_training_dataset(
    project: str,
    start_time: datetime,
    end_time: datetime,
    include_success: bool = True
) -> list[dict]:
    """导出训练数据集（失败/成功案例）"""
    runs = langsmith.list_runs(
        project_name=project,
        start_time=start_time,
        end_time=end_time
    )
    
    dataset = []
    for run in runs:
        trace = langsmith.get_trace(run.id)
        is_success = all(
            span.data.get("ok", True)
            for span in trace.spans
            if span.kind in ("verification", "tool")
        )
        
        if not include_success and is_success:
            continue
        
        dataset.append({
            "run_id": run.id,
            "thread_id": run.extra.get("thread_id"),
            "user_text": extract_user_text(trace),
            "success": is_success,
            "context": extract_context(trace),
            "verification_results": extract_verification(trace),
            "tool_results": extract_tool_results(trace),
            "langsmith_url": f"https://smith.langchain.com/runs/{run.id}"
        })
    
    return dataset
```

**用途**：
- 回归测试用例（成功案例）
- Prompt 优化参考（失败案例）
- 问题模式识别（聚类分析）

---

## 4. 需要的功能清单

### 4.1 Phase 1：基础自动化（1-2 周）

#### 4.1.1 失败案例收集脚本
**功能**：
- 扫描 LangSmith 项目，提取失败 run
- 按类型聚类（`angle_reflex`、`command_syntax`、`canvas_hygiene` 等）
- 生成 JSON 报告（含 trace 链接）

**输出**：
- `scripts/collect_failures.py`
- 报告格式：`logs/failures/failures-{date}.json`

**依赖**：
- LangSmith API（`langsmith` Python 包）
- 环境变量：`LANGCHAIN_API_KEY`、`LANGCHAIN_PROJECT`

#### 4.1.2 回归测试框架
**功能**：
- 维护 `test_cases/` 目录（YAML/JSON 格式）
- 每次 prompt 变更自动跑测试
- 生成测试报告（通过率、失败用例列表）

**输出**：
- `scripts/run_regression_tests.py`
- 测试用例格式：`docs/evals/golden_set.jsonl`（JSONL）
- 报告格式：`logs/regression/regression-{prompt_version}.json`

**依赖**：
- v2 API 可调用（`curl` 或 Python `requests`）
- 测试用例定义（见 3.4 节）

#### 4.1.3 Prompt 版本管理
**功能**：
- Git tag 管理 prompt 版本（如 `prompt-v2.1.0-angle-interior`）
- 记录每次变更的测试结果
- 支持 prompt 版本回滚

**输出**：
- `scripts/tag_prompt_version.py`
- 版本记录：`docs/prompt-versions.md`

**依赖**：
- Git 仓库
- 测试结果（来自回归测试框架）

### 4.2 Phase 2：AI 辅助分析（2-3 周）

#### 4.2.1 根因分析工具
**功能**：
- 用 LLM 分析失败 trace，输出结构化建议
- 人工审核后应用（不自动改代码）
- 记录审核结果

**输出**：
- `scripts/analyze_failure_root_cause.py`
- 建议格式：`logs/analysis/suggestions-{date}.json`

**依赖**：
- LangSmith API（获取 trace）
- LLM API（分析用，如 GPT-4）
- 当前 prompt 版本（Git 读取）

#### 4.2.2 A/B 测试工具
**功能**：
- 对比不同 prompt 版本的效果
- 生成对比报告（成功率、修复次数、成本）

**输出**：
- `scripts/ab_test_prompt.py`
- 报告格式：`logs/ab_test/ab-{variant_a}-vs-{variant_b}.json`

**依赖**：
- 测试用例集（`test_cases/`）
- LangSmith 项目隔离（不同 variant 用不同 project）
- v2 API 可调用

### 4.3 Phase 3：持续优化循环（长期）

#### 4.3.1 监控仪表板
**功能**：
- 实时显示失败率、平均修复次数
- 自动告警（失败率突增时）
- 趋势分析（按时间、问题类型）

**输出**：
- `scripts/monitor_dashboard.py`（CLI 输出或 Web 界面）
- 数据源：LangSmith API

**依赖**：
- LangSmith API
- 可选：Web 界面（Flask/FastAPI + 前端）

#### 4.3.2 自动建议系统
**功能**：
- 定期分析失败趋势，提出优化建议
- 人工决策是否采纳
- 记录采纳历史

**输出**：
- `scripts/auto_suggest_optimizations.py`
- 建议格式：`logs/suggestions/suggestions-{date}.json`

**依赖**：
- 失败案例数据（来自收集脚本）
- LLM API（分析用）

---

## 5. 实施路径

### 5.1 短期（Week 1-2）

**目标**：建立基础自动化能力

1. **失败案例收集脚本**
   - 实现 `scripts/collect_failures.py`
   - 支持从 LangSmith 提取失败 run
   - 按类型聚类，生成 JSON 报告

2. **回归测试框架**
   - 实现 `scripts/run_regression_tests.py`
   - 定义测试用例格式（YAML）
   - 创建初始测试用例集（5-10 个核心用例）

3. **Prompt 版本管理**
   - 实现 `scripts/tag_prompt_version.py`
   - 建立版本记录文档（`docs/prompt-versions.md`）

### 5.2 中期（Week 3-4）

**目标**：AI 辅助分析能力

1. **根因分析工具**
   - 实现 `scripts/analyze_failure_root_cause.py`
   - 集成 LLM 分析（GPT-4）
   - 输出结构化建议（人工审核）

2. **A/B 测试工具**
   - 实现 `scripts/ab_test_prompt.py`
   - 支持多 prompt 版本对比
   - 生成对比报告

### 5.3 长期（Week 5+）

**目标**：持续优化循环

1. **监控仪表板**
   - 实现 `scripts/monitor_dashboard.py`
   - 实时显示关键指标
   - 自动告警机制

2. **自动建议系统**
   - 实现 `scripts/auto_suggest_optimizations.py`
   - 定期分析失败趋势
   - 提出优化建议（人工审核）

---

## 6. 关键原则

### 6.1 可重复性优先
- 所有调优步骤都要可自动化、可版本化
- 测试用例要标准化、可复现
- 每次变更都要有测试结果记录

### 6.2 人工审核保留
- AI 只负责“建议”，不自动改代码
- 所有 prompt/LangGraph 变更都要经过人工审核
- 记录审核结果（采纳/拒绝/修改后采纳）

### 6.3 数据驱动
- 用 LangSmith/trace 数据驱动决策，而不是凭感觉
- 所有对比都要有量化指标（成功率、修复次数、成本）
- 建立问题分类体系，便于聚类分析

### 6.4 渐进式优化
- 先做低成本、高收益的自动化（失败案例收集、回归测试）
- 再考虑复杂方案（AI 辅助分析、自动建议）
- 避免过度工程化

---

## 7. 参考资源

### 7.1 LangSmith 文档
- [LangSmith Observability Concepts](https://docs.langchain.com/langsmith/observability-concepts)
- [LangSmith Python SDK](https://github.com/langchain-ai/langsmith-sdk)

### 7.2 相关文档
- `docs/spec/langgraph-orchestration.md`：LangGraph 架构
- `docs/prompt-system.md`：Prompt 系统设计
- `docs/spec/runtime-feedback-repair.md`：修复闭环规范

### 7.3 工具脚本位置
- 脚本目录：`scripts/`
- 日志目录：`logs/failures/`、`logs/regression/`、`logs/analysis/`
- 测试用例：`test_cases/`

---

## 8. 后续增强 Backlog（待讨论）

以下功能需要根据实际使用情况决定优先级：

- [x] **Studio Thread 创建工具**：`scripts/v2_create_studio_thread.py` - 从 FastAPI thread 自动创建 Studio thread ✅ (2026-01-02)
- [ ] **数据集导出工具**：从 LangSmith 导出训练数据集（失败/成功案例）
- [ ] **问题分类自动标注**：用 LLM 自动标注失败案例的问题类型
- [ ] **Prompt 变更影响分析**：分析某个 prompt 变更影响了哪些测试用例
- [ ] **LangGraph 节点性能分析**：分析各节点的执行时间、失败率
- [ ] **多模型对比**：对比不同 LLM provider 在同一 prompt 下的表现
- [ ] **Web 监控界面**：可视化监控仪表板（替代 CLI）
- [ ] **CI/CD 集成**：prompt 变更自动触发回归测试
- [ ] **Prompt 模板库**：常见问题的 prompt 模板（可复用）
- [ ] **自动化 Studio Thread 创建**：改进 `v2_create_studio_thread.py`，支持通过 API 自动创建（需要研究 Studio API 格式）
- [x] **回归测试框架（基础）**：实现 `scripts/run_regression_tests.py`（A/B 对比待做）

---

**文档版本**：v1.0  
**最后更新**：2026-01-02  
**维护者**：codex-A
