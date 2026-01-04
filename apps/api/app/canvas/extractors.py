from __future__ import annotations

from typing import Any


def extract_latest_canvas_objects(tool_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return latest `get_canvas_state.output.objects` from tool_results (best-effort)."""

    if not tool_results:
        return []
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


def count_object_types(objects: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in objects:
        typ = obj.get("type")
        if not isinstance(typ, str) or not typ.strip():
            continue
        key = typ.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


