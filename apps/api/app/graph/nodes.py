"""Graph node functions for LangGraph orchestration."""

from __future__ import annotations

import os
import uuid
from typing import Any

from langgraph.types import interrupt

from ..canvas.analyzers import list_triangle_candidates, triangle_kind_from_sides2
from ..canvas.extractors import extract_latest_canvas_objects
from ..canvas.validators import verify_canvas
from ..canvas_diagnostics import compute_canvas_diagnostics
from ..llm.difficulty_classifier import classify_difficulty
from ..llm.intent_classifier import classify_intent
from ..llm_decider import (
    generate_final_answer,
    generate_geogebra_commands,
    generate_plan,
    load_llm_config,
    summarize_memory,
)
from .state import GraphState
from .utils import (
    build_runtime_feedback,
    compact_memory_messages,
    intent_flags as get_intent_flags,
    llm_unavailable_text,
    read_int_env,
    render_draw_failure_answer,
)


def _emit_phase_update(
    state: GraphState,
    phase: str,
    *,
    summary: str | None = None,
    hypothesis: str | None = None,
    verification: str | None = None,
    result: str | None = None,
    next_step: str | None = None,
) -> dict:
    """Emit a safe, UI-visible phase update for hard-mode (NOT private chain-of-thought)."""

    if not bool(state.get("hard_mode")):
        return {}

    seq = int(state.get("phase_seq", 0)) + 1
    payload = {
        "seq": seq,
        "phase": phase,
        "summary": (summary or "").strip() or None,
        "hypothesis": (hypothesis or "").strip() or None,
        "verification": (verification or "").strip() or None,
        "result": (result or "").strip() or None,
        "next": (next_step or "").strip() or None,
    }
    return {"phase_seq": seq, "phase_update": payload}


def ingest_node(state: GraphState) -> dict:
    user_text = (state.get("user_text") or "").strip()
    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))

    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))

    max_attempts = read_int_env("V2_MAX_ATTEMPTS", 2, min_value=0, max_value=6)
    max_messages = read_int_env("V2_MEMORY_MAX_MESSAGES", 12, min_value=4, max_value=60)
    keep_last = read_int_env("V2_MEMORY_KEEP_LAST", 8, min_value=2, max_value=max_messages)

    memory_messages = compact_memory_messages(state.get("memory_messages"))
    if user_text:
        memory_messages.append({"role": "user", "text": user_text[:2000]})

    memory_summary = (state.get("memory_summary") or "").strip()
    if len(memory_messages) > max_messages:
        to_summarize = memory_messages[: max(0, len(memory_messages) - keep_last)]
        keep = memory_messages[-keep_last:]
        can_use_llm = load_llm_config(role=os.getenv("V2_LLM_SUMMARY_ROLE") or "fast") is not None
        if can_use_llm and model_calls_used < model_calls_limit:
            model_calls_used += 1
            summary = summarize_memory(
                previous_summary=memory_summary or None,
                messages=to_summarize,
                run_id=run_id,
                ui_debug=ui_debug,
            )
            if isinstance(summary, str) and summary.strip():
                memory_summary = summary.strip()
        memory_messages = keep

    # Intent sources (strict): UI structured hint or LLM intent-classifier.
    # Do NOT add heuristic/keyword parsing here.
    intent: dict[str, Any] = {}
    hint = state.get("intent_hint")
    if isinstance(hint, dict) and hint:
        intent = {k: v for k, v in hint.items() if isinstance(k, str)}
    else:
        can_use_llm = load_llm_config(role=os.getenv("V2_LLM_INTENT_ROLE") or "fast") is not None
        if user_text and can_use_llm and model_calls_used < model_calls_limit:
            model_calls_used += 1
            classified = classify_intent(
                user_text=user_text,
                run_id=run_id,
                ui_debug=ui_debug,
                context={"memory_summary": memory_summary or None},
            )
            if classified is not None:
                intent = classified.model_dump()

    # Difficulty routing (required): use a small model to decide whether to enter hard-mode.
    # No heuristic fallback. If the difficulty model is unavailable or returns invalid output, fail fast.
    fatal_error: dict[str, Any] = {}
    difficulty: str | None = None
    difficulty_reasons: list[str] = []
    difficulty_confidence: float | None = None
    hard_mode = False

    # Allow UI hint to override difficulty only if explicitly provided.
    # (This is still "structured hint", not heuristic parsing.)
    hinted_difficulty = None
    if isinstance(hint, dict) and hint:
        raw = hint.get("difficulty")
        if isinstance(raw, str) and raw.strip().lower() in {"simple", "hard"}:
            hinted_difficulty = raw.strip().lower()

    if hinted_difficulty is not None:
        difficulty = hinted_difficulty
        hard_mode = difficulty == "hard"
        difficulty_reasons = ["UI hint"]
        difficulty_confidence = 0.9
    else:
        if not user_text:
            difficulty = "simple"
            hard_mode = False
        elif model_calls_used >= model_calls_limit:
            fatal_error = {
                "code": "difficulty_classifier_unavailable",
                "message": "难度判定服务不可用（需要小模型）。请稍后重试，或检查服务端模型配置。",
            }
        else:
            model_calls_used += 1
            classified = classify_difficulty(
                user_text=user_text,
                run_id=run_id,
                ui_debug=ui_debug,
                context={"memory_summary": memory_summary or None},
            )
            if classified is None:
                fatal_error = {
                    "code": "difficulty_classifier_failed",
                    "message": "难度判定失败（小模型返回无效）。请稍后重试。",
                }
            else:
                difficulty = classified.difficulty
                hard_mode = difficulty == "hard"
                difficulty_reasons = list(classified.reasons or [])
                difficulty_confidence = float(classified.confidence)

    # Auto-enable plan mode when hard-mode is selected (simple mode stays direct).
    plan_mode = bool(state.get("plan_mode")) or hard_mode

    # Reset per-run ephemeral state so a new user turn starts cleanly.
    return {
        "did_draw": False,
        "needs_canvas_refresh": False,
        "regen_needed": False,
        "attempt": 0,
        "max_attempts": max_attempts,
        "repair_feedback": "",
        "pending_delete_objects": [],
        "give_up_after_cleanup": False,
        "last_exec_created_objects": [],
        "last_exec_had_failure": False,
        "last_exec_dialogs": [],
        "last_verify_issues": [],
        "pending_numeric_eval": {},
        "measured_triangle_kinds": {},
        "numeric_verified": False,
        "intent": intent,
        "difficulty": difficulty or "simple",
        "difficulty_reasons": difficulty_reasons,
        "difficulty_confidence": difficulty_confidence if difficulty_confidence is not None else 0.6,
        "hard_mode": hard_mode,
        "phase_seq": 0,
        "phase_update": {},
        "fatal_error": fatal_error,
        "plan_mode": plan_mode,
        "memory_messages": memory_messages,
        "memory_summary": memory_summary,
        "model_calls_used": model_calls_used,
        "model_calls_limit": model_calls_limit,
    }


def plan_node(state: GraphState) -> dict:
    plan_mode = bool(state.get("plan_mode"))
    if not plan_mode:
        return {"plan": []}

    user_text = (state.get("user_text") or "").strip()
    if not user_text:
        return {"plan": []}

    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))
    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))

    can_use_llm = load_llm_config(role=os.getenv("V2_LLM_PLAN_ROLE") or "main") is not None
    if not can_use_llm or model_calls_used >= model_calls_limit:
        return {"plan": []}

    model_calls_used += 1
    steps = generate_plan(
        user_text=user_text,
        memory_summary=state.get("memory_summary") or None,
        recent_messages=state.get("memory_messages") or None,
        run_id=run_id,
        ui_debug=ui_debug,
    )
    if not steps:
        return {"plan": [], "model_calls_used": model_calls_used, "model_calls_limit": model_calls_limit}

    plan = [{"id": f"p{i+1}", "text": s, "done": False} for i, s in enumerate(steps[:8]) if isinstance(s, str) and s.strip()]

    # In hard-mode, provide a safe, UI-visible "overall approach" phase (no CoT).
    phase: dict[str, Any] = {}
    if bool(state.get("hard_mode")) and plan:
        top_steps = "；".join([p["text"] for p in plan[:3] if isinstance(p.get("text"), str) and p.get("text")])
        phase = _emit_phase_update(
            state,
            "Plan",
            summary="先制定整体思路，再用画板验证每一步是否满足条件。",
            hypothesis="按计划逐步构造，能满足题目要求。",
            verification="用画板检查关键性质是否成立。",
            next_step=(top_steps or "开始读取画板状态，然后按计划构造。"),
        )

    return {**phase, "plan": plan, "model_calls_used": model_calls_used, "model_calls_limit": model_calls_limit}


def act_node(state: GraphState) -> dict:
    tool_calls_used = int(state.get("tool_calls_used", 0))
    tool_calls_limit = int(state.get("tool_calls_limit", 3))
    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))
    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))
    user_text = state.get("user_text") or ""
    remaining = max(0, tool_calls_limit - tool_calls_used)
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 2))
    intent_flags = get_intent_flags(state)
    is_draw_request = intent_flags["wants_draw"] and not intent_flags["forbids_drawing"]

    fatal = state.get("fatal_error")
    if isinstance(fatal, dict) and fatal.get("message"):
        msg = str(fatal.get("message") or "").strip()
        if not msg:
            msg = "服务端出现致命错误（已记录日志）。"
        return {
            **_emit_phase_update(
                state,
                "Error",
                summary="难题模式准备失败：必需组件不可用。",
                result=msg,
                next_step="请检查服务端模型配置（尤其是小模型角色绑定）后重试。",
            ),
            "next_step_kind": "final",
            "answer_text": msg,
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    if tool_calls_used >= tool_calls_limit:
        if is_draw_request:
            if state.get("give_up_after_cleanup") is True:
                return {
                    **_emit_phase_update(
                        state,
                        "Finalize",
                        summary="清理完成，但本轮工具预算已用完。",
                        result="未能在预算内完成作图。",
                        next_step="可以重试同一题目，我会换一种更稳的作图方法。",
                    ),
                    "give_up_after_cleanup": False,
                    "next_step_kind": "final",
                    "answer_text": render_draw_failure_answer(state),
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            # If we just deleted objects, our latest canvas snapshot may be stale.
            if state.get("needs_canvas_refresh") is True:
                return {
                    **_emit_phase_update(
                        state,
                        "Finalize",
                        summary="本轮工具预算已用完，无法刷新画板确认最终状态。",
                        result="无法确认结果是否正确。",
                        next_step="可以重试同一题目，我会换一种更稳的作图方法。",
                    ),
                    "next_step_kind": "final",
                    "answer_text": "这轮我已经用完了工具预算，所以没法再刷新画板确认结果。为了不留下错误图形，我可能已经回滚/清理了本次新增对象。你可以再发一次同样的需求，我会换一种更稳的作图方法。",
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            ok, _issues = verify_canvas(state)
            if ok and state.get("did_draw") is True:
                if ui_debug:
                    return {
                        **_emit_phase_update(
                            state,
                            "Finalize",
                            summary="验证通过（调试模式：跳过长讲解生成）。",
                            result="OK",
                            next_step="你可以关闭开发模式以获取更完整的讲解。",
                        ),
                        "next_step_kind": "final",
                        "answer_text": "（调试模式）我已经完成作图并通过了基础验证。你可以关闭开发模式以获取更完整的讲解。",
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

                can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
                if can_use_llm:
                    model_calls_used += 1
                    answer = generate_final_answer(
                        user_text=user_text,
                        tool_calls_used=tool_calls_used,
                        tool_calls_limit=tool_calls_limit,
                        tool_results=state.get("tool_results"),
                        memory_summary=state.get("memory_summary") or None,
                        recent_messages=state.get("memory_messages") or None,
                        run_id=run_id,
                        ui_debug=ui_debug,
                    )
                    if answer:
                        return {
                            **_emit_phase_update(
                                state,
                                "Finalize",
                                summary="验证通过，准备输出讲解。",
                                result="OK",
                                next_step="",
                            ),
                            "next_step_kind": "final",
                            "answer_text": answer,
                            "model_calls_used": model_calls_used,
                            "model_calls_limit": model_calls_limit,
                        }

                return {
                    **_emit_phase_update(
                        state,
                        "Finalize",
                        summary="验证通过，但当前无法生成讲解。",
                        result="OK（讲解不可用）",
                        next_step="",
                    ),
                    "next_step_kind": "final",
                    "answer_text": llm_unavailable_text(state),
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            return {
                **_emit_phase_update(
                    state,
                    "Finalize",
                    summary="工具预算已用完，但还没画对。",
                    result="Failed",
                    next_step="可以重试同一题目，我会换一种更稳的作图方法。",
                ),
                "next_step_kind": "final",
                "answer_text": "我这次没能把图形画对（工具预算已用完）。你可以再发一次同样的需求，我会换一种更稳的作图方法。",
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

        can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
        if can_use_llm:
            model_calls_used += 1
            answer = generate_final_answer(
                user_text=user_text,
                tool_calls_used=tool_calls_used,
                tool_calls_limit=tool_calls_limit,
                tool_results=state.get("tool_results"),
                memory_summary=state.get("memory_summary") or None,
                recent_messages=state.get("memory_messages") or None,
                run_id=run_id,
                ui_debug=ui_debug,
            )
            if answer:
                return {
                    **_emit_phase_update(
                        state,
                        "Finalize",
                        summary="已生成最终回答。",
                        result="OK",
                        next_step="",
                    ),
                    "next_step_kind": "final",
                    "answer_text": answer,
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

        return {
            **_emit_phase_update(
                state,
                "Finalize",
                summary="当前无法生成最终回答。",
                result="Failed",
                next_step="请检查服务端模型配置后重试。",
            ),
            "next_step_kind": "final",
            "answer_text": llm_unavailable_text(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # First step is deterministic: always inspect the canvas before doing anything else.
    if tool_calls_used == 0:
        return {
            **_emit_phase_update(
                state,
                "Understand",
                summary="先看看画板上现在有什么对象，确认起点。",
                verification="读取画板状态",
                next_step="读取画板对象列表，确认目前状态。",
            ),
            "next_step_kind": "tool",
            "next_tool_name": "get_canvas_state",
            "next_tool_call_id": str(uuid.uuid4()),
            "next_tool_input": {"include": ["objects"]},
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    pending_delete = state.get("pending_delete_objects")
    if isinstance(pending_delete, list) and pending_delete and remaining >= 1:
        objects = [x for x in pending_delete if isinstance(x, str) and x.strip()]
        if objects:
            return {
                **_emit_phase_update(
                    state,
                    "Revise",
                    summary="先把刚才失败分支新增的对象清理掉。",
                    verification="清理对象",
                    next_step="清理后换一种作图方法，再重新验证。",
                ),
                "pending_delete_objects": [],
                "next_step_kind": "tool",
                "next_tool_name": "delete_objects",
                "next_tool_call_id": str(uuid.uuid4()),
                "next_tool_input": {"objects": objects[:200]},
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

    # If we executed draw commands, ensure we refresh the canvas state before finishing (tool budget permitting).
    if state.get("needs_canvas_refresh") and remaining >= 1:
        return {
            **_emit_phase_update(
                state,
                "Verify",
                summary="刷新画板状态，准备检查结果是否满足题目要求。",
                verification="读取画板状态",
                next_step="刷新对象列表后进行验证。",
            ),
            "next_step_kind": "tool",
            "next_tool_name": "get_canvas_state",
            "next_tool_call_id": str(uuid.uuid4()),
            "next_tool_input": {"include": ["objects"]},
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    if state.get("give_up_after_cleanup") and remaining >= 0:
        return {
            **_emit_phase_update(
                state,
                "Finalize",
                summary="清理完成，结束本次尝试。",
                result="Failed",
                next_step="可以重试同一题目，我会换一种更稳的作图方法。",
            ),
            "give_up_after_cleanup": False,
            "next_step_kind": "final",
            "answer_text": render_draw_failure_answer(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # Safety/UX guard: if the user explicitly forbids drawing, finish with a text answer.
    if tool_calls_used == 1 and intent_flags["forbids_drawing"]:
        can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
        if can_use_llm:
            model_calls_used += 1
            answer = generate_final_answer(
                user_text=user_text,
                tool_calls_used=tool_calls_used,
                tool_calls_limit=tool_calls_limit,
                tool_results=state.get("tool_results"),
                memory_summary=state.get("memory_summary") or None,
                recent_messages=state.get("memory_messages") or None,
                run_id=run_id,
                ui_debug=ui_debug,
            )
            if answer:
                return {
                    **_emit_phase_update(
                        state,
                        "Finalize",
                        summary="按你的要求不在画板上作图，直接给出文字回答。",
                        result="OK",
                        next_step="",
                    ),
                    "next_step_kind": "final",
                    "answer_text": answer,
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

        return {
            **_emit_phase_update(
                state,
                "Finalize",
                summary="按你的要求不作图，但当前无法生成文字回答。",
                result="Failed",
                next_step="请检查服务端模型配置后重试。",
            ),
            "next_step_kind": "final",
            "answer_text": llm_unavailable_text(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # If a repair was requested and we refreshed the canvas, regenerate commands.
    if state.get("regen_needed") and remaining >= 1 and not state.get("needs_canvas_refresh"):
        can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
        if can_use_llm:
            model_calls_used += 1
            commands = generate_geogebra_commands(
                user_text=user_text,
                tool_calls_used=tool_calls_used,
                tool_calls_limit=tool_calls_limit,
                tool_results=state.get("tool_results"),
                runtime_feedback=state.get("repair_feedback") or None,
                memory_summary=state.get("memory_summary") or None,
                recent_messages=state.get("memory_messages") or None,
                run_id=run_id,
                ui_debug=ui_debug,
            )
            if commands:
                return {
                    **_emit_phase_update(
                        state,
                        "Revise",
                        summary="根据刚才的验证反馈，调整作图方法再试一次。",
                        hypothesis="换一种构造思路，应该能满足题目条件。",
                        verification="执行作图步骤",
                        next_step="执行新的一组作图步骤，然后重新验证。",
                    ),
                    "regen_needed": False,
                    "give_up_after_cleanup": False,
                    "attempt": attempt + 1,
                    "did_draw": True,
                    "needs_canvas_refresh": True,
                    "next_step_kind": "tool",
                    "next_tool_name": "exec_geogebra_commands",
                    "next_tool_call_id": str(uuid.uuid4()),
                    "next_tool_input": {"commands": commands},
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

        return {
            **_emit_phase_update(
                state,
                "Finalize",
                summary="无法进行修复：当前模型不可用。",
                result="Failed",
                next_step="请检查服务端模型配置后重试。",
            ),
            "next_step_kind": "final",
            "answer_text": llm_unavailable_text(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # Main draw path: generate commands once, execute, refresh, then verify.
    if is_draw_request:
        if not state.get("did_draw") and remaining >= 1:
            can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
            if can_use_llm:
                model_calls_used += 1
                commands = generate_geogebra_commands(
                    user_text=user_text,
                    tool_calls_used=tool_calls_used,
                    tool_calls_limit=tool_calls_limit,
                    tool_results=state.get("tool_results"),
                    runtime_feedback=None,
                    memory_summary=state.get("memory_summary") or None,
                    recent_messages=state.get("memory_messages") or None,
                    run_id=run_id,
                    ui_debug=ui_debug,
                )
                if commands:
                    return {
                        **_emit_phase_update(
                            state,
                            "Act",
                            summary="生成作图步骤并执行。",
                            hypothesis="按这组构造步骤，应该能满足题目要求。",
                            verification="执行作图步骤",
                            next_step="先执行作图步骤，然后刷新画板并验证结果。",
                        ),
                        "attempt": attempt + 1,
                        "did_draw": True,
                        "needs_canvas_refresh": True,
                        "next_step_kind": "tool",
                        "next_tool_name": "exec_geogebra_commands",
                        "next_tool_call_id": str(uuid.uuid4()),
                        "next_tool_input": {"commands": commands},
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

            return {
                **_emit_phase_update(
                    state,
                    "Finalize",
                    summary="无法生成作图步骤：当前模型不可用。",
                    result="Failed",
                    next_step="请检查服务端模型配置后重试。",
                ),
                "next_step_kind": "final",
                "answer_text": llm_unavailable_text(state),
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

        ok, issues = verify_canvas(state)
        if ok:
            if ui_debug:
                return {
                    **_emit_phase_update(
                        state,
                        "Verify",
                        summary="验证通过（调试模式：跳过长讲解生成）。",
                        result="OK",
                        next_step="你可以关闭开发模式以获取更完整的讲解。",
                    ),
                    "last_verify_issues": [],
                    "next_step_kind": "final",
                    "answer_text": "（调试模式）我已经完成作图并通过了基础验证。你可以关闭开发模式以获取更完整的讲解。",
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
            if can_use_llm:
                model_calls_used += 1
                answer = generate_final_answer(
                    user_text=user_text,
                    tool_calls_used=tool_calls_used,
                    tool_calls_limit=tool_calls_limit,
                    tool_results=state.get("tool_results"),
                    memory_summary=state.get("memory_summary") or None,
                    recent_messages=state.get("memory_messages") or None,
                    run_id=run_id,
                    ui_debug=ui_debug,
                )
                if answer:
                    return {
                        **_emit_phase_update(
                            state,
                            "Verify",
                            summary="验证通过，准备输出讲解。",
                            result="OK",
                            next_step="完成并输出讲解。",
                        ),
                        "last_verify_issues": [],
                        "next_step_kind": "final",
                        "answer_text": answer,
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

            return {
                **_emit_phase_update(
                    state,
                    "Verify",
                    summary="验证通过，但当前无法生成讲解。",
                    result="OK（讲解不可用）",
                    next_step="",
                ),
                "last_verify_issues": [],
                "next_step_kind": "final",
                "answer_text": llm_unavailable_text(state),
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

        # If triangle semantics are required but cannot be verified from canvas snapshot alone,
        # do a small numeric check before deciding it's wrong.
        if (
            (("missing_right_triangle" in issues) or ("missing_obtuse_triangle" in issues))
            and state.get("numeric_verified") is not True
            and remaining >= 1
        ):
            objects_latest = extract_latest_canvas_objects(state.get("tool_results"))
            triangles = list_triangle_candidates(objects_latest)
            unknown = [
                t
                for t in triangles
                if isinstance(t, dict)
                and t.get("kind") == "unknown"
                and isinstance(t.get("vertices"), list)
                and len(t.get("vertices")) == 3
                and all(isinstance(v, str) and v.strip() for v in t.get("vertices"))
            ]
            if unknown:
                want_both = ("missing_right_triangle" in issues) and ("missing_obtuse_triangle" in issues)
                max_triangles = 2 if want_both else 1
                selected = unknown[:max_triangles]
                tri_vertices: list[list[str]] = []
                exprs: list[str] = []
                for t in selected:
                    vs = [v.strip() for v in t.get("vertices")[:3]]
                    tri_vertices.append(vs)
                    a, b, c = vs[0], vs[1], vs[2]
                    exprs.extend([f"Distance({a},{b})^2", f"Distance({b},{c})^2", f"Distance({c},{a})^2"])
                if exprs:
                    return {
                        **_emit_phase_update(
                            state,
                            "Verify",
                            summary="从画板信息还不能确定三角形类型，先做一次数值验证。",
                            verification="数值检查",
                            next_step="计算边长平方，判断是否为直角/钝角三角形。",
                        ),
                        "pending_numeric_eval": {"triangles": tri_vertices, "group_size": 3},
                        "next_step_kind": "tool",
                        "next_tool_name": "eval_numeric",
                        "next_tool_call_id": str(uuid.uuid4()),
                        "next_tool_input": {"expressions": exprs},
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

        # Failed verification: rollback and repair if budget permits.
        feedback = build_runtime_feedback(state, issues)
        created = state.get("last_exec_created_objects") or []
        objects = [x for x in created if isinstance(x, str) and x.strip()]
        if attempt < max_attempts and remaining >= 4 and objects:
            return {
                **_emit_phase_update(
                    state,
                    "Revise",
                    summary="验证没通过：先清理新增对象，再根据反馈改进作图方法。",
                    result="验证未通过",
                    next_step="清理后生成“修复版”作图步骤，并再次验证。",
                ),
                "last_verify_issues": issues,
                "repair_feedback": feedback,
                "regen_needed": True,
                "give_up_after_cleanup": False,
                "pending_delete_objects": [],
                "next_step_kind": "tool",
                "next_tool_name": "delete_objects",
                "next_tool_call_id": str(uuid.uuid4()),
                "next_tool_input": {"objects": objects[:200]},
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

        # No more attempts/budget: try to keep canvas clean if possible, then finish.
        if remaining >= 1 and objects:
            return {
                **_emit_phase_update(
                    state,
                    "Revise",
                    summary="验证没通过，但剩余预算不足以再修复：先清理再结束。",
                    result="验证未通过",
                    next_step="清理失败对象并结束本次尝试。",
                ),
                "last_verify_issues": issues,
                "repair_feedback": feedback,
                "regen_needed": False,
                "give_up_after_cleanup": True,
                "pending_delete_objects": [],
                "next_step_kind": "tool",
                "next_tool_name": "delete_objects",
                "next_tool_call_id": str(uuid.uuid4()),
                "next_tool_input": {"objects": objects[:200]},
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

        return {
            **_emit_phase_update(
                state,
                "Finalize",
                summary="验证没通过，且没有剩余预算可修复/清理。",
                result="Failed",
                next_step="可以重试同一题目，我会换一种更稳的作图方法。",
            ),
            "last_verify_issues": issues,
            "next_step_kind": "final",
            "answer_text": "我这次没能把图形画对（已记录排障信息）。你可以再发一次同样的需求，我会换一种更稳的作图方法。",
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # Explanation-only path.
    if ui_debug:
        return {
            **_emit_phase_update(
                state,
                "Answer",
                summary="调试模式：跳过长文本生成。",
                result="OK",
                next_step="关闭开发模式以获取更完整的回答。",
            ),
            "next_step_kind": "final",
            "answer_text": "（调试模式）我可以继续执行作图/验证流程，但我会跳过长文本讲解生成以减少不稳定因素。你可以关闭开发模式以获取更完整的回答。",
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    can_use_llm = load_llm_config() is not None and model_calls_used < model_calls_limit
    if can_use_llm:
        model_calls_used += 1
        answer = generate_final_answer(
            user_text=user_text,
            tool_calls_used=tool_calls_used,
            tool_calls_limit=tool_calls_limit,
            tool_results=state.get("tool_results"),
            memory_summary=state.get("memory_summary") or None,
            recent_messages=state.get("memory_messages") or None,
            run_id=run_id,
            ui_debug=ui_debug,
        )
        if answer:
            return {
                **_emit_phase_update(
                    state,
                    "Answer",
                    summary="生成文字回答。",
                    result="OK",
                    next_step="输出答案。",
                ),
                "next_step_kind": "final",
                "answer_text": answer,
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

    return {
        **_emit_phase_update(
            state,
            "Finalize",
            summary="当前无法生成文字回答。",
            result="Failed",
            next_step="请检查服务端模型配置后重试。",
        ),
        "next_step_kind": "final",
        "answer_text": llm_unavailable_text(state),
        "model_calls_used": model_calls_used,
        "model_calls_limit": model_calls_limit,
    }


def finalize_node(state: GraphState) -> dict:
    answer_text = (state.get("answer_text") or "").strip()
    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))

    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))

    max_messages = read_int_env("V2_MEMORY_MAX_MESSAGES", 12, min_value=4, max_value=60)
    keep_last = read_int_env("V2_MEMORY_KEEP_LAST", 8, min_value=2, max_value=max_messages)

    memory_messages = compact_memory_messages(state.get("memory_messages"))
    if answer_text:
        memory_messages.append({"role": "assistant", "text": answer_text[:2000]})

    memory_summary = (state.get("memory_summary") or "").strip()
    if len(memory_messages) > max_messages:
        to_summarize = memory_messages[: max(0, len(memory_messages) - keep_last)]
        keep = memory_messages[-keep_last:]
        can_use_llm = load_llm_config(role=os.getenv("V2_LLM_SUMMARY_ROLE") or "fast") is not None
        if can_use_llm and model_calls_used < model_calls_limit:
            model_calls_used += 1
            summary = summarize_memory(
                previous_summary=memory_summary or None,
                messages=to_summarize,
                run_id=run_id,
                ui_debug=ui_debug,
            )
            if isinstance(summary, str) and summary.strip():
                memory_summary = summary.strip()
        memory_messages = keep

    return {
        "memory_messages": memory_messages,
        "memory_summary": memory_summary,
        "model_calls_used": model_calls_used,
        "model_calls_limit": model_calls_limit,
    }


def frontend_tool_node(state: GraphState) -> dict:
    tool_name = state["next_tool_name"]
    tool_call_id = state["next_tool_call_id"]
    tool_input = state.get("next_tool_input", {})
    run_id = state.get("run_id")

    resume_value = interrupt(
        {
            "kind": "frontend_tool",
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": tool_input,
        }
    )

    tool_calls_used = int(state.get("tool_calls_used", 0)) + 1
    prev_results = state.get("tool_results", [])
    next_results = list(prev_results) + [
        {
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": tool_input,
            "resume": resume_value,
        }
    ]
    if len(next_results) > 30:
        next_results = next_results[-30:]

    updates: dict[str, Any] = {
        "tool_calls_used": tool_calls_used,
        "tool_results": next_results,
    }
    if tool_name == "get_canvas_state":
        updates["needs_canvas_refresh"] = False
        if isinstance(resume_value, dict) and resume_value.get("ok") is True:
            output = resume_value.get("output")
            if isinstance(output, dict) and isinstance(output.get("objects"), list):
                updates["canvas_diagnostics"] = compute_canvas_diagnostics(output.get("objects"))

    if tool_name == "exec_geogebra_commands":
        created_objects: list[str] = []
        dialogs: list[str] = []
        had_failure = False
        if isinstance(resume_value, dict) and resume_value.get("ok") is True:
            output = resume_value.get("output")
            if isinstance(output, dict):
                created = output.get("created_objects")
                if isinstance(created, list):
                    created_objects = [str(x) for x in created if isinstance(x, str) and x.strip()]
                ds = output.get("dialogs")
                if isinstance(ds, list):
                    dialogs = [str(x) for x in ds if isinstance(x, str) and x.strip()]
                results = output.get("results")
                if isinstance(results, list):
                    had_failure = any(isinstance(r, dict) and r.get("ok") is False for r in results)
        updates["last_exec_created_objects"] = created_objects
        updates["last_exec_dialogs"] = dialogs
        updates["last_exec_had_failure"] = had_failure

    if tool_name == "eval_numeric":
        measured_prev = state.get("measured_triangle_kinds")
        measured: dict[str, str] = dict(measured_prev) if isinstance(measured_prev, dict) else {}
        pending = state.get("pending_numeric_eval")

        if isinstance(resume_value, dict) and resume_value.get("ok") is True:
            output = resume_value.get("output")
            if isinstance(output, dict) and isinstance(output.get("results"), list):
                values: list[float | None] = []
                for r in output.get("results")[:60]:
                    if not isinstance(r, dict):
                        values.append(None)
                        continue
                    ok = r.get("ok") is True
                    v = r.get("value")
                    if ok and isinstance(v, (int, float)):
                        values.append(float(v))
                    else:
                        values.append(None)

                if isinstance(pending, dict):
                    tris = pending.get("triangles")
                    group_size = pending.get("group_size", 3)
                    try:
                        group_size_i = int(group_size)
                    except Exception:
                        group_size_i = 3
                    if isinstance(tris, list) and group_size_i >= 3:
                        for i, verts in enumerate(tris[:8]):
                            if not (isinstance(verts, list) and len(verts) == 3):
                                continue
                            if not all(isinstance(v2, str) and v2.strip() for v2 in verts):
                                continue
                            idx = i * group_size_i
                            if idx + 2 >= len(values):
                                continue
                            a2, b2, c2 = values[idx], values[idx + 1], values[idx + 2]
                            if a2 is None or b2 is None or c2 is None:
                                continue
                            kind = triangle_kind_from_sides2(a2, b2, c2)
                            measured[",".join([v2.strip() for v2 in verts])] = kind

        updates["measured_triangle_kinds"] = measured
        updates["pending_numeric_eval"] = {}
        updates["numeric_verified"] = True

    if tool_name == "delete_objects":
        # After deletion/rollback, refresh canvas state before regenerating commands.
        updates["needs_canvas_refresh"] = True

    return updates
