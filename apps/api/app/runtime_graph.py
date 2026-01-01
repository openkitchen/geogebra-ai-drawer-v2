import uuid
import math
import re
import os
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from .llm_decider import generate_final_answer, generate_geogebra_commands, generate_plan, load_llm_config, summarize_memory
from .canvas_diagnostics import compute_canvas_diagnostics

class GraphState(TypedDict, total=False):
    run_id: str
    ui_debug: bool
    plan_mode: bool
    plan: list[dict[str, Any]]
    user_text: str
    memory_summary: str
    memory_messages: list[dict[str, Any]]
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


def _wants_draw(user_text: str) -> bool:
    lowered = user_text.lower()
    return (
        ("画" in user_text)
        or ("画图" in user_text)
        or ("作图" in user_text)
        or ("绘制" in user_text)
        or ("画出" in user_text)
        or ("draw" in lowered)
    )


def _user_forbids_drawing(user_text: str) -> bool:
    lowered = user_text.lower()
    if "不要画" in user_text or "不用画" in user_text or "不需要画" in user_text or "不画" in user_text:
        return True
    if "don't draw" in lowered or "do not draw" in lowered or "no drawing" in lowered:
        return True
    return False


def _read_int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(min_value, min(max_value, value))


def _compact_memory_messages(messages: Any) -> list[dict[str, Any]]:
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


def ingest_node(state: GraphState) -> dict:
    user_text = (state.get("user_text") or "").strip()
    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))

    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))

    max_attempts = _read_int_env("V2_MAX_ATTEMPTS", 2, min_value=0, max_value=6)
    max_messages = _read_int_env("V2_MEMORY_MAX_MESSAGES", 12, min_value=4, max_value=60)
    keep_last = _read_int_env("V2_MEMORY_KEEP_LAST", 8, min_value=2, max_value=max_messages)

    memory_messages = _compact_memory_messages(state.get("memory_messages"))
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
    return {"plan": plan, "model_calls_used": model_calls_used, "model_calls_limit": model_calls_limit}


def _wants_circle(user_text: str) -> bool:
    lowered = user_text.lower()
    return ("圆" in user_text) or ("circle" in lowered)


def _wants_triangle(user_text: str) -> bool:
    lowered = user_text.lower()
    return ("三角形" in user_text) or ("triangle" in lowered)


def _llm_unavailable_text(state: GraphState) -> str:
    run_id = state.get("run_id") or ""
    if state.get("ui_debug") and run_id:
        return (
            "我这次没能调用语言模型来回答你的问题（可能是模型繁忙或配置缺失）。\n"
            f"run_id: {run_id}\n"
            "你可以稍后重试；或在本目录 `.env.local` 调整 `LLM_ROLE_BINDINGS_JSON` 把 main/fast 绑定到其他模型。"
        )
    return "我这次没能回答上来，你可以稍后再试一次。"


def _fallback_text_without_llm(state: GraphState) -> str:
    return _llm_unavailable_text(state)


def _extract_latest_canvas_objects(state: GraphState) -> list[dict[str, Any]]:
    tool_results = state.get("tool_results", [])
    for entry in reversed(tool_results):
        if entry.get("tool_name") != "get_canvas_state":
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict) or resume.get("ok") is not True:
            continue
        output = resume.get("output")
        if not isinstance(output, dict):
            continue
        objects = output.get("objects")
        if isinstance(objects, list):
            return [x for x in objects if isinstance(x, dict)]
    return []


def _count_object_types(objects: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in objects:
        typ = obj.get("type")
        if not isinstance(typ, str) or not typ.strip():
            continue
        key = typ.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _extract_triangle_vertices(objects: list[dict[str, Any]]) -> list[str]:
    tri_obj: dict[str, Any] | None = None
    for obj in objects:
        typ = obj.get("type")
        if isinstance(typ, str) and typ.strip().lower() in {"triangle", "polygon"}:
            tri_obj = obj
            break
    if tri_obj is None:
        return []

    point_names: set[str] = set()
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        typ = obj.get("type")
        if isinstance(typ, str) and typ.strip().lower() == "point":
            point_names.add(name.strip())

    text = tri_obj.get("commandString") if isinstance(tri_obj.get("commandString"), str) else tri_obj.get("definitionString")
    if not isinstance(text, str) or not text.strip():
        return []

    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", text)
    uniq: list[str] = []
    for t in tokens:
        if t in point_names and t not in uniq:
            uniq.append(t)
    return uniq[:3]


_POINT_RE = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)"
)


def _parse_point_coords(value: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(value)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except Exception:
        return None


def _extract_point_coords(objects: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for obj in objects:
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        typ = obj.get("type")
        if not (isinstance(typ, str) and typ.strip().lower() == "point"):
            continue
        value = obj.get("valueString")
        if not isinstance(value, str) or not value.strip():
            continue
        xy = _parse_point_coords(value)
        if xy is None:
            continue
        coords[name.strip()] = xy
    return coords


def _is_right_triangle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    def d2(p: tuple[float, float], q: tuple[float, float]) -> float:
        dx = p[0] - q[0]
        dy = p[1] - q[1]
        return dx * dx + dy * dy

    ab = d2(a, b)
    bc = d2(b, c)
    ca = d2(c, a)
    sides = sorted([ab, bc, ca])
    if sides[0] <= 1e-12:
        return False
    # Pythagorean check with relative tolerance (GeoGebra coords are often decimals).
    return abs((sides[0] + sides[1]) - sides[2]) <= max(1e-6, 1e-3 * sides[2])


def _triangle_kind(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> str:
    def d2(p: tuple[float, float], q: tuple[float, float]) -> float:
        dx = p[0] - q[0]
        dy = p[1] - q[1]
        return dx * dx + dy * dy

    ab = d2(a, b)
    bc = d2(b, c)
    ca = d2(c, a)
    sides = sorted([ab, bc, ca])
    if sides[0] <= 1e-12:
        return "degenerate"

    tol = max(1e-6, 1e-3 * sides[2])
    if abs((sides[0] + sides[1]) - sides[2]) <= tol:
        return "right"
    if (sides[0] + sides[1]) < (sides[2] - tol):
        return "obtuse"
    return "acute"


def _triangle_kind_from_sides2(s1: float, s2: float, s3: float) -> str:
    sides = sorted([s1, s2, s3])
    if sides[0] <= 1e-12:
        return "degenerate"
    tol = max(1e-6, 1e-3 * sides[2])
    if abs((sides[0] + sides[1]) - sides[2]) <= tol:
        return "right"
    if (sides[0] + sides[1]) < (sides[2] - tol):
        return "obtuse"
    return "acute"


def _list_triangle_candidates(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coords = _extract_point_coords(objects)
    center = coords.get("O")

    candidates: list[dict[str, Any]] = []
    for obj in objects:
        typ = obj.get("type")
        if not (isinstance(typ, str) and typ.strip().lower() in {"triangle", "polygon"}):
            continue

        name = obj.get("name")
        name_s = name.strip() if isinstance(name, str) else ""
        vertices = _extract_triangle_vertices([obj] + objects)
        if len(vertices) != 3:
            continue

        if not all(v in coords for v in vertices):
            candidates.append({"name": name_s, "vertices": vertices, "kind": "unknown", "inscribed_ok": None})
            continue

        a, b, c = (coords[vertices[0]], coords[vertices[1]], coords[vertices[2]])
        kind = _triangle_kind(a, b, c)

        inscribed_ok: bool | None = None
        if center is not None:
            dists = [math.dist(center, coords[v]) for v in vertices]
            if min(dists) <= 1e-6:
                inscribed_ok = False
            else:
                spread = max(dists) - min(dists)
                inscribed_ok = spread <= max(1e-6, 1e-3 * max(dists))

        candidates.append({"name": name_s, "vertices": vertices, "kind": kind, "inscribed_ok": inscribed_ok})

    return candidates


def _verify_canvas(state: GraphState) -> tuple[bool, list[str]]:
    issues: list[str] = []
    user_text = state.get("user_text") or ""

    diag = state.get("canvas_diagnostics")
    if isinstance(diag, dict) and diag.get("ok") is False:
        if diag.get("zero_length_segments"):
            issues.append(f"zero_length_segments={diag.get('zero_length_segments')}")
        if diag.get("zero_area_polygons"):
            issues.append(f"zero_area_polygons={diag.get('zero_area_polygons')}")
        if diag.get("duplicate_points"):
            issues.append("duplicate_points=true")

    objects = _extract_latest_canvas_objects(state)
    type_counts = _count_object_types(objects)

    if _wants_circle(user_text) and type_counts.get("circle", 0) <= 0:
        issues.append("missing_circle")
    if _wants_triangle(user_text) and (type_counts.get("triangle", 0) + type_counts.get("polygon", 0)) <= 0:
        issues.append("missing_triangle")

    # Semantic checks (best-effort, deterministic) for common geometry requests.
    lowered = user_text.lower()
    wants_right = ("直角" in user_text) or ("right" in lowered)
    wants_obtuse = ("钝角" in user_text) or ("obtuse" in lowered)
    wants_inscribed = "内接" in user_text

    triangles = _list_triangle_candidates(objects)
    measured = state.get("measured_triangle_kinds")
    if isinstance(measured, dict) and measured:
        for t in triangles:
            if not isinstance(t, dict):
                continue
            if t.get("kind") != "unknown":
                continue
            vertices = t.get("vertices")
            if not (isinstance(vertices, list) and len(vertices) == 3 and all(isinstance(v, str) for v in vertices)):
                continue
            key = ",".join(vertices)
            kind = measured.get(key)
            if isinstance(kind, str) and kind.strip():
                t["kind"] = kind.strip()

    def ok_inscribed(t: dict[str, Any]) -> bool:
        if not wants_inscribed:
            return True
        v = t.get("inscribed_ok")
        return v is not False  # True or None(unknown) are acceptable for MVP.

    if wants_right and wants_obtuse:
        if len(triangles) < 2:
            issues.append("need_two_triangles")
        has_right = any(t.get("kind") == "right" and ok_inscribed(t) for t in triangles)
        has_obtuse = any(t.get("kind") == "obtuse" and ok_inscribed(t) for t in triangles)
        if not has_right:
            issues.append("missing_right_triangle")
        if not has_obtuse:
            issues.append("missing_obtuse_triangle")
    else:
        if wants_right:
            has_right = any(t.get("kind") == "right" and ok_inscribed(t) for t in triangles)
            if not has_right:
                issues.append("missing_right_triangle")
        if wants_obtuse:
            has_obtuse = any(t.get("kind") == "obtuse" and ok_inscribed(t) for t in triangles)
            if not has_obtuse:
                issues.append("missing_obtuse_triangle")

    # If "内接" is requested, make sure at least one triangle seems inscribed (when we can verify).
    if wants_inscribed and triangles:
        known = [t for t in triangles if t.get("inscribed_ok") is not None]
        if known and not any(t.get("inscribed_ok") is True for t in known):
            issues.append("inscribed_triangle:vertices_not_on_same_circle")

    return (len(issues) == 0), issues


def _build_runtime_feedback(state: GraphState, issues: list[str]) -> str:
    lines: list[str] = []
    if issues:
        lines.append("Canvas verification failed:")
        for issue in issues[:12]:
            lines.append(f"- {issue}")

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

    current = _extract_latest_canvas_objects(state)
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


def _summarize_last_delete(state: GraphState) -> str | None:
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


def _render_draw_failure_answer(state: GraphState) -> str:
    # Child-first UX by default; include debug details only when ui_debug is enabled.
    base = "我这次没能把图形画对，但我已经把画板清理干净了。你可以再发一次同样的需求，我会换一种更稳的作图方法。"
    if not bool(state.get("ui_debug")):
        return base

    lines: list[str] = [base]
    issues = state.get("last_verify_issues")
    if isinstance(issues, list) and issues:
        lines.append("")
        lines.append("失败原因（调试信息）：")
        for issue in [x for x in issues if isinstance(x, str) and x.strip()][:8]:
            lines.append(f"- {issue.strip()}")

    cleanup = _summarize_last_delete(state)
    if cleanup:
        lines.append(f"- {cleanup}")

    run_id = (state.get("run_id") or "").strip()
    if run_id:
        lines.append(f"- run_id: {run_id}")

    return "\n".join(lines).strip()


def _act_node_stub(state: GraphState) -> dict:
    tool_calls_used = int(state.get("tool_calls_used", 0))
    tool_calls_limit = int(state.get("tool_calls_limit", 3))
    user_text = state.get("user_text") or ""
    remaining = max(0, tool_calls_limit - tool_calls_used)

    if tool_calls_used >= tool_calls_limit:
        return {
            "next_step_kind": "final",
            "answer_text": _fallback_text_without_llm(state),
        }

    if state.get("needs_canvas_refresh") and remaining >= 1:
        return {
            "next_step_kind": "tool",
            "next_tool_name": "get_canvas_state",
            "next_tool_call_id": str(uuid.uuid4()),
            "next_tool_input": {"include": ["objects"]},
        }

    if tool_calls_used == 0:
        return {
            "next_step_kind": "tool",
            "next_tool_name": "get_canvas_state",
            "next_tool_call_id": str(uuid.uuid4()),
            "next_tool_input": {"include": ["objects"]},
        }

    if tool_calls_used == 1:
        if _wants_draw(user_text):
            run_id = state.get("run_id") or "demo"
            suffix = run_id.split("-")[0]
            point_name = f"A_{suffix}"
            circle_name = f"c_{suffix}"
            commands = [
                f"{point_name} = (0, 0)",
                f"{circle_name} = Circle({point_name}, 1)",
            ]
            return {
                "did_draw": True,
                "needs_canvas_refresh": True,
                "next_step_kind": "tool",
                "next_tool_name": "exec_geogebra_commands",
                "next_tool_call_id": str(uuid.uuid4()),
                "next_tool_input": {"commands": commands},
            }

        return {
            "next_step_kind": "final",
            "answer_text": _fallback_text_without_llm(state),
        }

    return {
        "next_step_kind": "final",
        "answer_text": _fallback_text_without_llm(state),
    }


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

    if tool_calls_used >= tool_calls_limit:
        is_draw_request = _wants_draw(user_text) and not _user_forbids_drawing(user_text)
        if is_draw_request:
            if state.get("give_up_after_cleanup") is True:
                return {
                    "give_up_after_cleanup": False,
                    "next_step_kind": "final",
                    "answer_text": _render_draw_failure_answer(state),
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            # If we just deleted objects, our latest canvas snapshot may be stale.
            if state.get("needs_canvas_refresh") is True:
                return {
                    "next_step_kind": "final",
                    "answer_text": "这轮我已经用完了工具预算，所以没法再刷新画板确认结果。为了不留下错误图形，我可能已经回滚/清理了本次新增对象。你可以再发一次同样的需求，我会换一种更稳的作图方法。",
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            ok, _issues = _verify_canvas(state)
            if ok and state.get("did_draw") is True:
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
                            "next_step_kind": "final",
                            "answer_text": answer,
                            "model_calls_used": model_calls_used,
                            "model_calls_limit": model_calls_limit,
                        }

                return {
                    "next_step_kind": "final",
                    "answer_text": "图已经画在画板上了，但我这次没能生成文字说明。你可以稍后重试。",
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

            return {
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
                    "next_step_kind": "final",
                    "answer_text": answer,
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

        return {
            "next_step_kind": "final",
            "answer_text": _fallback_text_without_llm(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # First step is deterministic: always inspect the canvas before doing anything else.
    if tool_calls_used == 0:
        return {
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
            "next_step_kind": "tool",
            "next_tool_name": "get_canvas_state",
            "next_tool_call_id": str(uuid.uuid4()),
            "next_tool_input": {"include": ["objects"]},
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    if state.get("give_up_after_cleanup") and remaining >= 0:
        return {
            "give_up_after_cleanup": False,
            "next_step_kind": "final",
            "answer_text": _render_draw_failure_answer(state),
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # Safety/UX guard: if the user explicitly forbids drawing, finish with a text answer.
    if tool_calls_used == 1 and _user_forbids_drawing(user_text):
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
                    "next_step_kind": "final",
                    "answer_text": answer,
                    "model_calls_used": model_calls_used,
                    "model_calls_limit": model_calls_limit,
                }

        return {
            "next_step_kind": "final",
            "answer_text": _fallback_text_without_llm(state),
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

        stub = _act_node_stub(state)
        stub["regen_needed"] = False
        stub["model_calls_used"] = model_calls_used
        stub["model_calls_limit"] = model_calls_limit
        return stub

    # Main draw path: generate commands once, execute, refresh, then verify.
    if _wants_draw(user_text) and not _user_forbids_drawing(user_text):
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

            stub = _act_node_stub(state)
            stub["model_calls_used"] = model_calls_used
            stub["model_calls_limit"] = model_calls_limit
            return stub

        ok, issues = _verify_canvas(state)
        if ok:
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
                        "last_verify_issues": [],
                        "next_step_kind": "final",
                        "answer_text": answer,
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

            return {
                "last_verify_issues": [],
                "next_step_kind": "final",
                "answer_text": "图已经画在画板上了，但我这次没能生成文字说明。你可以稍后重试。",
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
            objects_latest = _extract_latest_canvas_objects(state)
            triangles = _list_triangle_candidates(objects_latest)
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
                        "pending_numeric_eval": {"triangles": tri_vertices, "group_size": 3},
                        "next_step_kind": "tool",
                        "next_tool_name": "eval_numeric",
                        "next_tool_call_id": str(uuid.uuid4()),
                        "next_tool_input": {"expressions": exprs},
                        "model_calls_used": model_calls_used,
                        "model_calls_limit": model_calls_limit,
                    }

        # Failed verification: rollback and repair if budget permits.
        feedback = _build_runtime_feedback(state, issues)
        created = state.get("last_exec_created_objects") or []
        objects = [x for x in created if isinstance(x, str) and x.strip()]
        if attempt < max_attempts and remaining >= 4 and objects:
            return {
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
            "last_verify_issues": issues,
            "next_step_kind": "final",
            "answer_text": "我这次没能把图形画对（已记录排障信息）。你可以再发一次同样的需求，我会换一种更稳的作图方法。",
            "model_calls_used": model_calls_used,
            "model_calls_limit": model_calls_limit,
        }

    # Explanation-only path.
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
                "next_step_kind": "final",
                "answer_text": answer,
                "model_calls_used": model_calls_used,
                "model_calls_limit": model_calls_limit,
            }

    return {
        "next_step_kind": "final",
        "answer_text": _fallback_text_without_llm(state),
        "model_calls_used": model_calls_used,
        "model_calls_limit": model_calls_limit,
    }


def finalize_node(state: GraphState) -> dict:
    answer_text = (state.get("answer_text") or "").strip()
    run_id = state.get("run_id")
    ui_debug = bool(state.get("ui_debug"))

    model_calls_used = int(state.get("model_calls_used", 0))
    model_calls_limit = int(state.get("model_calls_limit", 6))

    max_messages = _read_int_env("V2_MEMORY_MAX_MESSAGES", 12, min_value=4, max_value=60)
    keep_last = _read_int_env("V2_MEMORY_KEEP_LAST", 8, min_value=2, max_value=max_messages)

    memory_messages = _compact_memory_messages(state.get("memory_messages"))
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
                            kind = _triangle_kind_from_sides2(a2, b2, c2)
                            measured[",".join([v2.strip() for v2 in verts])] = kind

        updates["measured_triangle_kinds"] = measured
        updates["pending_numeric_eval"] = {}
        updates["numeric_verified"] = True

    if tool_name == "delete_objects":
        # After deletion/rollback, refresh canvas state before regenerating commands.
        updates["needs_canvas_refresh"] = True

    return updates


_checkpointer = InMemorySaver()

_builder = StateGraph(GraphState)
_builder.add_node("ingest_node", ingest_node)
_builder.add_node("plan_node", plan_node)
_builder.add_node("act_node", act_node)
_builder.add_node("finalize_node", finalize_node)
_builder.add_node("frontend_tool_node", frontend_tool_node)
_builder.add_conditional_edges(
    "act_node",
    lambda state: state["next_step_kind"],
    {
        "tool": "frontend_tool_node",
        "final": "finalize_node",
    },
)
_builder.add_edge(START, "ingest_node")
_builder.add_edge("ingest_node", "plan_node")
_builder.add_edge("plan_node", "act_node")
_builder.add_edge("frontend_tool_node", "act_node")
_builder.add_edge("finalize_node", END)

# `graph` is the entrypoint used by LangGraph Studio (langgraph dev). The runtime platform
# provides persistence automatically, so we must not attach a custom checkpointer here.
graph = _builder.compile()

# Our in-app FastAPI server uses an in-memory checkpointer so that interrupt/resume and
# /state endpoints work in local dev.
graph_local = _builder.compile(checkpointer=_checkpointer)
