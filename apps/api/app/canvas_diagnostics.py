from __future__ import annotations

import math
import re
from typing import Any


_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_POINT_RE = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)"
)


def _parse_last_number(value: str) -> float | None:
    matches = list(_NUM_RE.finditer(value))
    if not matches:
        return None
    try:
        return float(matches[-1].group(0))
    except Exception:
        return None


def _parse_point_coords(value: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(value)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except Exception:
        return None


def compute_canvas_diagnostics(objects: list[dict[str, Any]] | None) -> dict[str, Any]:
    objs = objects if isinstance(objects, list) else []
    point_coords: dict[str, tuple[float, float]] = {}
    zero_length_segments: list[str] = []
    zero_area_polygons: list[str] = []

    for obj in objs:
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        if not isinstance(name, str) or not name:
            continue
        typ = obj.get("type")
        typ_s = str(typ).lower() if isinstance(typ, str) else ""
        value = obj.get("valueString")
        value_s = value if isinstance(value, str) else ""

        if typ_s == "point" and value_s:
            coords = _parse_point_coords(value_s)
            if coords is not None:
                point_coords[name] = coords
            continue

        if typ_s == "segment" and value_s:
            length = _parse_last_number(value_s)
            if length is not None and abs(length) <= 1e-9:
                zero_length_segments.append(name)
            continue

        if typ_s in {"triangle", "polygon"} and value_s:
            area = _parse_last_number(value_s)
            if area is not None and abs(area) <= 1e-9:
                zero_area_polygons.append(name)
            continue

    duplicates: list[dict[str, Any]] = []
    names = list(point_coords.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = names[i]
            b = names[j]
            ax, ay = point_coords[a]
            bx, by = point_coords[b]
            if math.isfinite(ax) and math.isfinite(ay) and math.isfinite(bx) and math.isfinite(by):
                if abs(ax - bx) <= 1e-9 and abs(ay - by) <= 1e-9:
                    duplicates.append({"a": a, "b": b, "xy": [ax, ay]})

    # Duplicate points can be intentional (e.g. reusing a vertex across shapes) and do not
    # necessarily indicate a broken diagram. Treat them as warnings only; hard-fail only on
    # clearly degenerate geometry like zero-length segments or zero-area polygons.
    ok = not zero_length_segments and not zero_area_polygons

    return {
        "ok": ok,
        "objects_count": len(objs),
        "zero_length_segments": zero_length_segments,
        "zero_area_polygons": zero_area_polygons,
        "duplicate_points": duplicates,
    }
