from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    ui_debug: bool
    plan_mode: bool
    plan: list[dict[str, Any]]
    user_text: str
    # Optional structured hint from UI (NOT derived from text parsing).
    intent_hint: dict[str, Any]
    memory_summary: str
    memory_messages: list[dict[str, Any]]
    intent: dict[str, Any]
    tool_calls_used: int
    tool_calls_limit: int
    model_calls_used: int
    model_calls_limit: int
    did_draw: bool
    needs_canvas_refresh: bool
    canvas_diagnostics: dict[str, Any]
    regen_needed: bool
    attempt: int
    max_attempts: int
    repair_feedback: str
    pending_delete_objects: list[str]
    give_up_after_cleanup: bool
    last_exec_created_objects: list[str]
    last_exec_had_failure: bool
    last_exec_dialogs: list[str]
    last_verify_issues: list[str]
    pending_numeric_eval: dict[str, Any]
    measured_triangle_kinds: dict[str, str]
    numeric_verified: bool
    next_step_kind: Literal["tool", "final"]
    next_tool_name: str
    next_tool_call_id: str
    next_tool_input: Any
    tool_results: list[dict[str, Any]]
    answer_text: str


