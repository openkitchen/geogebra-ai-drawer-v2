Generate a short, user-visible high-level approach plan (NOT private chain-of-thought).

Output format (STRICT): return ONLY JSON:
{
  "steps": ["...", "...", "..."]
}

Rules:
- `steps` must be 3–6 short Chinese phrases.
- Each step should be one action. Prefer "阶段式" steps for hard geometry: "提出假设" → "构造/作图" → "用画板/数值验证" → "根据反馈修正" → "总结".
- Use the provided canvas snapshot + tool capabilities to make the steps concrete, but NEVER include raw commands.
- Do NOT include tool_call_id, run_id, model/provider names, or any low-level debug details.
