Generate a short internal plan for this user request.

Output format (STRICT): return ONLY JSON:
{
  "steps": ["...", "...", "..."]
}

Rules:
- `steps` must be 3–6 short Chinese phrases.
- Each step should be one action (e.g. "读取画板对象", "生成作图命令", "执行并检查结果", "用孩子能懂的话解释").
- Do NOT include tool_call_id, run_id, or any low-level debug details.
