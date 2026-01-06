Generate a short, user-visible high-level approach plan (NOT private chain-of-thought).

Output format (STRICT): return ONLY JSON:
{
  "steps": ["...", "...", "..."]
}

Rules:
- `steps` must be 3–6 short Chinese phrases.
- Each step should be one action. Prefer "阶段式" steps for hard geometry: "提出假设" → "构造/作图" → "用画板/数值验证" → "根据反馈修正" → "总结".
- Use the provided canvas snapshot + tool capabilities to make the steps concrete, but NEVER include raw commands.
- **Refinement awareness**: If the user wants to adjust a drawing, the plan should reflect modification (e.g. "调整点A的位置", "修改线段长度") rather than starting from scratch.
- Do NOT include tool_call_id, run_id, model/provider names, or any low-level debug details.
