"""Utility functions for graph nodes."""

from __future__ import annotations

import os
from typing import Any

from ..canvas.extractors import extract_latest_canvas_objects
from .state import GraphState


def intent_flags(state: GraphState) -> dict[str, bool]:
    """Extract intent flags from state."""
    intent = state.get("intent")
    d: dict[str, Any] = intent if isinstance(intent, dict) else {}
    return {
        "wants_draw": bool(d.get("wants_draw")),
        "forbids_drawing": bool(d.get("forbids_drawing")),
    }


def read_int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    """Read integer from environment variable with bounds."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(min_value, min(max_value, value))


def compact_memory_messages(messages: Any) -> list[dict[str, Any]]:
    """Compact memory messages list."""
    if not isinstance(messages, list):
        return []
    out: list[dict[str, Any]] = []
    for m in messages[-24:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        text = m.get("text")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(text, str):
            continue
        t = text.strip()
        if not t:
            continue
        out.append({"role": role, "text": t[:2000]})
    return out


def llm_unavailable_text(state: GraphState) -> str:
    """Generate text when LLM is unavailable."""
    run_id = state.get("run_id") or ""
    if state.get("ui_debug") and run_id:
        return (
            "我这次没能调用语言模型来回答你的问题（可能是模型繁忙或配置缺失）。\n"
            f"run_id: {run_id}\n"
            "你可以稍后重试；或在本目录 `.env.local` 调整 `LLM_ROLE_BINDINGS_JSON` 把 main/fast 绑定到其他模型。"
        )
    return "我这次没能回答上来，你可以稍后再试一次。"


def build_runtime_feedback(state: GraphState, issues: list[str]) -> str:
    """Build runtime feedback string for repair."""
    lines: list[str] = []
    if issues:
        lines.append("Canvas verification failed:")
        for issue in issues[:12]:
            lines.append(f"- {issue}")

    # Capture tool-level execution failures (per-command) for repair.
    tool_results = state.get("tool_results")
    if isinstance(tool_results, list):
        for entry in reversed(tool_results):
            if not isinstance(entry, dict):
                continue
            if entry.get("tool_name") != "exec_geogebra_commands":
                continue
            resume = entry.get("resume")
            if not isinstance(resume, dict):
                break
            output = resume.get("output")
            if isinstance(output, dict):
                results = output.get("results")
                if isinstance(results, list):
                    failed: list[dict[str, str]] = []
                    for r in results[:60]:
                        if not isinstance(r, dict) or r.get("ok") is not False:
                            continue
                        cmd = r.get("command")
                        err = r.get("error")
                        cmd_s = cmd.strip() if isinstance(cmd, str) else ""
                        msg_s = ""
                        if isinstance(err, dict):
                            msg = err.get("message")
                            if isinstance(msg, str):
                                msg_s = msg.strip()
                        if cmd_s:
                            failed.append({"command": cmd_s, "message": msg_s})
                        if len(failed) >= 6:
                            break
                    for item in failed:
                        msg = item.get("message") or "Command failed"
                        lines.append(f'Command failed: "{item.get("command")}" ({msg})')

                rb = output.get("rolled_back_objects")
                if isinstance(rb, list):
                    names = [str(x) for x in rb if isinstance(x, str) and x.strip()]
                    if names:
                        lines.append(f"Rolled back: {', '.join(names[:60])}{' …' if len(names) > 60 else ''}.")
            break

    dialogs = state.get("last_exec_dialogs")
    if isinstance(dialogs, list) and dialogs:
        for d in dialogs[:6]:
            if isinstance(d, str) and d.strip():
                lines.append(f'GeoGebra dialog: "{d.strip()}"')

    if state.get("last_exec_had_failure") is True:
        lines.append("At least one command failed (evalCommand returned false).")

    created = state.get("last_exec_created_objects")
    if isinstance(created, list) and created:
        names = [str(x) for x in created if isinstance(x, str) and x.strip()]
        if names:
            lines.append(f"Attempt created objects: {', '.join(names[:30])}{' …' if len(names) > 30 else ''}")

    current = extract_latest_canvas_objects(state.get("tool_results"))
    current_names: list[str] = []
    for obj in current[:30]:
        name = obj.get("name")
        if isinstance(name, str) and name.strip():
            current_names.append(name.strip())
    if current_names:
        lines.append(f"Current objects (partial): {', '.join(current_names)}")

    lines.append("IMPORTANT: Re-generate a COMPLETE command list for the original user request (not a patch).")
    lines.append("Avoid degenerate geometry (duplicate points / zero-length segments / zero-area polygons).")

    return "\n".join(lines).strip()


def summarize_last_delete(state: GraphState) -> str | None:
    """Summarize last delete operation."""
    tool_results = state.get("tool_results", [])
    if not isinstance(tool_results, list):
        return None

    for entry in reversed(tool_results):
        if entry.get("tool_name") != "delete_objects":
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict):
            return None
        output = resume.get("output")
        if not isinstance(output, dict):
            return None
        deleted = output.get("deleted_objects")
        failed = output.get("failed_objects")
        deleted_n = len(deleted) if isinstance(deleted, list) else 0
        failed_n = len(failed) if isinstance(failed, list) else 0
        return f"cleanup(delete_objects): deleted={deleted_n} failed={failed_n}"

    return None


def render_draw_failure_answer(state: GraphState) -> str:
    """Render answer text when drawing failed."""
    base = "真抱歉，我这次没能把图形画对。我已经把画板清理干净了，别担心，你可以尝试换一种描述方式再发给我，我们再试一次！"
    if not bool(state.get("ui_debug")):
        return base

    lines: list[str] = [base]
    issues = state.get("last_verify_issues")
    if isinstance(issues, list) and issues:
        lines.append("")
        lines.append("失败原因（调试信息）：")
        for issue in [x for x in issues if isinstance(x, str) and x.strip()][:8]:
            lines.append(f"- {issue.strip()}")

    cleanup = summarize_last_delete(state)
    if cleanup:
        lines.append(f"- {cleanup}")

    run_id = (state.get("run_id") or "").strip()
    if run_id:
        lines.append(f"- run_id: {run_id}")

    return "\n".join(lines).strip()
