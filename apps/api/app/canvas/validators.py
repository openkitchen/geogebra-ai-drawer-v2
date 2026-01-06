from __future__ import annotations

from typing import Any, Mapping

from .analyzers import list_triangle_candidates
from .extractors import count_object_types, extract_latest_canvas_objects


def verify_canvas(state: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Best-effort deterministic validation.

    Intention detection should come from the intent classifier (cheap model),
    and be passed in via `state["intent"]`.
    """

    issues: list[str] = []
    intent = state.get("intent")
    intent_d: dict[str, Any] = intent if isinstance(intent, dict) else {}

    if state.get("last_exec_had_failure") is True:
        rolled_back = state.get("last_exec_rolled_back_objects")
        if isinstance(rolled_back, list) and rolled_back:
            issues.append("exec_geogebra_commands_failed:rolled_back")
        else:
            issues.append("exec_geogebra_commands_failed")

    diag = state.get("canvas_diagnostics")
    if isinstance(diag, dict) and diag.get("ok") is False:
        if diag.get("zero_length_segments"):
            issues.append(f"zero_length_segments={diag.get('zero_length_segments')}")
        if diag.get("zero_area_polygons"):
            issues.append(f"zero_area_polygons={diag.get('zero_area_polygons')}")
        if diag.get("duplicate_points"):
            issues.append("duplicate_points=true")

    objects = extract_latest_canvas_objects(state.get("tool_results"))
    type_counts = count_object_types(objects)

    wants_circle = bool(intent_d.get("wants_circle"))
    wants_triangle = bool(intent_d.get("wants_triangle"))

    if wants_circle and type_counts.get("circle", 0) <= 0:
        issues.append("missing_circle")
    if wants_triangle and (type_counts.get("triangle", 0) + type_counts.get("polygon", 0)) <= 0:
        issues.append("missing_triangle")

    # Semantic checks (best-effort, deterministic) for common geometry requests.
    wants_right = bool(intent_d.get("wants_right_triangle"))
    wants_obtuse = bool(intent_d.get("wants_obtuse_triangle"))
    wants_inscribed = bool(intent_d.get("wants_inscribed_triangle"))

    triangles = list_triangle_candidates(objects)
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

