from __future__ import annotations

import math
import re
from typing import Any

_POINT_RE = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)"
)


def parse_point_coords(value: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(value)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except Exception:
        return None


def extract_point_coords(objects: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
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
        xy = parse_point_coords(value)
        if xy is None:
            continue
        coords[name.strip()] = xy
    return coords


def extract_triangle_vertices(objects: list[dict[str, Any]]) -> list[str]:
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


def triangle_kind(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> str:
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


def triangle_kind_from_sides2(s1: float, s2: float, s3: float) -> str:
    sides = sorted([s1, s2, s3])
    if sides[0] <= 1e-12:
        return "degenerate"
    tol = max(1e-6, 1e-3 * sides[2])
    if abs((sides[0] + sides[1]) - sides[2]) <= tol:
        return "right"
    if (sides[0] + sides[1]) < (sides[2] - tol):
        return "obtuse"
    return "acute"


def list_triangle_candidates(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coords = extract_point_coords(objects)
    center = coords.get("O")

    candidates: list[dict[str, Any]] = []
    for obj in objects:
        typ = obj.get("type")
        if not (isinstance(typ, str) and typ.strip().lower() in {"triangle", "polygon"}):
            continue

        name = obj.get("name")
        name_s = name.strip() if isinstance(name, str) else ""
        vertices = extract_triangle_vertices([obj] + objects)
        if len(vertices) != 3:
            continue

        if not all(v in coords for v in vertices):
            candidates.append({"name": name_s, "vertices": vertices, "kind": "unknown", "inscribed_ok": None})
            continue

        a, b, c = (coords[vertices[0]], coords[vertices[1]], coords[vertices[2]])
        kind = triangle_kind(a, b, c)

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


