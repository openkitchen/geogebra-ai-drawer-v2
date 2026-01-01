#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Optional


@dataclass
class SseEvent:
    event: str
    data_raw: str
    data: Any | None = None


def _json_dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _http_json(
    *,
    method: str,
    url: str,
    body: Any | None = None,
    timeout_s: float = 10.0,
) -> Any:
    data = None if body is None else _json_dumps(body)
    req = urllib.request.Request(
        url=url,
        method=method,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return None
        return json.loads(raw)


def _iter_sse_events(resp) -> Iterator[SseEvent]:
    event_name = "message"
    data_lines: list[str] = []

    while True:
        line_bytes = resp.readline()
        if not line_bytes:
            # EOF
            if data_lines:
                yield SseEvent(event=event_name, data_raw="\n".join(data_lines), data=None)
            return

        try:
            line = line_bytes.decode("utf-8")
        except Exception:
            line = line_bytes.decode("utf-8", errors="replace")

        line = line.rstrip("\n")
        if line.endswith("\r"):
            line = line[:-1]

        if line == "":
            if not data_lines and event_name == "message":
                continue
            data_raw = "\n".join(data_lines)
            ev = SseEvent(event=event_name, data_raw=data_raw, data=None)
            try:
                ev.data = json.loads(data_raw) if data_raw else None
            except Exception:
                ev.data = data_raw
            yield ev
            event_name = "message"
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
            continue


def _http_sse(
    *,
    method: str,
    url: str,
    body: Any | None = None,
    timeout_s: float = 30.0,
) -> Iterable[SseEvent]:
    data = None if body is None else _json_dumps(body)
    req = urllib.request.Request(
        url=url,
        method=method,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    resp = urllib.request.urlopen(req, timeout=timeout_s)
    try:
        yield from _iter_sse_events(resp)
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _extract_assignment_label(command: str) -> str | None:
    if "=" not in command:
        return None
    left, _ = command.split("=", 1)
    label = left.strip()
    if not label:
        return None
    # Avoid returning "Circle(A,1)" etc.
    if any(ch in label for ch in " ()"):
        return None
    return label


def _infer_object_type(command: str) -> str | None:
    t = command.strip()
    rhs = t.split("=", 1)[1].strip() if "=" in t else t
    low = rhs.lower()
    if low.startswith("(") and "," in low and ")" in low:
        return "point"
    if low.startswith("rotate(") or "rotate(" in low:
        return "point"
    if low.startswith("midpoint(") or "midpoint(" in low or "中点(" in rhs:
        return "point"
    if "circle(" in low or low.startswith("circle("):
        return "circle"
    if "polygon(" in low or low.startswith("polygon("):
        return "polygon"
    if "segment(" in low or low.startswith("segment("):
        return "segment"
    return None


_POINT_RE = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)"
)


def _parse_point_coords(command: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(command)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except Exception:
        return None


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    s = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


_ROTATE_RE = re.compile(
    r"rotate\(\s*([A-Za-z][A-Za-z0-9_]*)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*°\s*,\s*([A-Za-z][A-Za-z0-9_]*)\s*\)",
    re.IGNORECASE,
)


def _try_eval_point(rhs: str, known: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    m = _ROTATE_RE.search(rhs)
    if m:
        src = m.group(1)
        deg = float(m.group(2))
        center = m.group(3)
        if src in known and center in known:
            x, y = known[src]
            cx, cy = known[center]
            dx = x - cx
            dy = y - cy
            rad = math.radians(deg)
            rx = dx * math.cos(rad) - dy * math.sin(rad) + cx
            ry = dx * math.sin(rad) + dy * math.cos(rad) + cy
            return (rx, ry)

    # Midpoint(A, B) / 中点(A, B)
    if "midpoint" in rhs.lower() or "中点" in rhs:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", rhs)
        if len(tokens) >= 3:
            a = tokens[1]
            b = tokens[2]
            if a in known and b in known:
                ax, ay = known[a]
                bx, by = known[b]
                return ((ax + bx) / 2.0, (ay + by) / 2.0)

    return None


_DISTANCE_RE = re.compile(
    r"distance\(\s*([A-Za-z][A-Za-z0-9_]*)\s*,\s*([A-Za-z][A-Za-z0-9_]*)\s*\)\s*(?:\^\s*2\s*)?$",
    re.IGNORECASE,
)


def _try_eval_distance(expr: str, known: dict[str, tuple[float, float]]) -> float | None:
    s = expr.strip()
    m = _DISTANCE_RE.match(s)
    if not m:
        return None
    a = m.group(1)
    b = m.group(2)
    if a not in known or b not in known:
        return None
    ax, ay = known[a]
    bx, by = known[b]
    dx = ax - bx
    dy = ay - by
    d2 = dx * dx + dy * dy
    # Support both Distance(A,B) and Distance(A,B)^2 by inspecting raw text.
    return d2 if "^" in s else math.sqrt(d2)


@dataclass
class FakeCanvas:
    objects: list[dict[str, Any]] = field(default_factory=list)

    def apply_commands(self, commands: list[str]) -> list[str]:
        created: list[str] = []
        # Keep a tiny coord map so we can generate more realistic valueString for verification.
        point_coords: dict[str, tuple[float, float]] = {}
        for obj in self.objects:
            if not isinstance(obj, dict):
                continue
            if str(obj.get("type") or "").lower() != "point":
                continue
            name = obj.get("name")
            if not isinstance(name, str):
                continue
            value = obj.get("valueString")
            if isinstance(value, str):
                xy = _parse_point_coords(value)
                if xy is not None:
                    point_coords[name] = xy

        for cmd in commands:
            label = _extract_assignment_label(cmd)
            if not label:
                continue
            if any(obj.get("name") == label for obj in self.objects):
                continue
            typ = _infer_object_type(cmd)
            value_string = None
            if typ == "point":
                xy = _parse_point_coords(cmd)
                if xy is not None:
                    point_coords[label] = xy
                    value_string = f"{label} = ({xy[0]}, {xy[1]})"
                else:
                    rhs = cmd.split("=", 1)[1].strip() if "=" in cmd else cmd.strip()
                    xy2 = _try_eval_point(rhs, point_coords)
                    if xy2 is not None:
                        point_coords[label] = xy2
                        value_string = f"{label} = ({xy2[0]}, {xy2[1]})"
            if typ in {"polygon", "triangle"}:
                # Try to approximate polygon area if we can resolve vertex coords.
                rhs = cmd.split("=", 1)[1] if "=" in cmd else cmd
                tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", rhs)
                pts: list[tuple[float, float]] = []
                for t in tokens:
                    if t in point_coords:
                        pts.append(point_coords[t])
                if pts:
                    value_string = f"{label} = {_polygon_area(pts)}"
            self.objects.append(
                {
                    "name": label,
                    "type": typ,
                    "visible": True,
                    "valueString": value_string,
                    "definitionString": cmd.strip(),
                    "commandString": cmd.strip(),
                }
            )
            created.append(label)
        return created

    def point_coords(self) -> dict[str, tuple[float, float]]:
        coords: dict[str, tuple[float, float]] = {}
        for obj in self.objects:
            if not isinstance(obj, dict):
                continue
            if str(obj.get("type") or "").lower() != "point":
                continue
            name = obj.get("name")
            if not isinstance(name, str) or not name:
                continue
            value = obj.get("valueString")
            if not isinstance(value, str):
                continue
            xy = _parse_point_coords(value)
            if xy is None:
                continue
            coords[name] = xy
        return coords

    def delete_objects(self, names: list[str]) -> list[str]:
        deleted: list[str] = []
        targets = set(names)
        kept: list[dict[str, Any]] = []
        for obj in self.objects:
            name = obj.get("name") if isinstance(obj, dict) else None
            if isinstance(name, str) and name in targets:
                deleted.append(name)
                continue
            kept.append(obj)
        self.objects = kept
        return deleted


def _make_tool_output(
    *,
    tool_name: str,
    tool_input: Any,
    canvas: FakeCanvas,
    force_repair_once: bool,
    saw_exec: bool,
    forced: bool,
) -> Any:
    if tool_name == "get_canvas_state":
        objects = canvas.objects
        if force_repair_once and saw_exec and not forced and isinstance(objects, list) and len(objects) >= 2:
            injected: list[dict[str, Any]] = []
            for i, obj in enumerate(objects):
                if not isinstance(obj, dict):
                    continue
                copied = dict(obj)
                if copied.get("type") == "point":
                    name = str(copied.get("name") or "")
                    copied["valueString"] = f"{name} = (0, 0)" if i < 2 else f"{name} = (1, 0)"
                if copied.get("type") in {"polygon", "triangle"}:
                    name = str(copied.get("name") or "")
                    copied["valueString"] = f"{name} = 0"
                injected.append(copied)
            # Always add a fake zero-length segment so backend diagnostics can deterministically fail once.
            injected.append(
                {
                    "name": "a",
                    "type": "segment",
                    "visible": True,
                    "valueString": "a = 0",
                    "definitionString": "Segment(A,B)",
                    "commandString": "Segment(A,B)",
                }
            )
            return {"objects": injected, "__forced_repair": True}
        return {"objects": objects}

    if tool_name == "exec_geogebra_commands":
        commands = []
        if isinstance(tool_input, dict) and isinstance(tool_input.get("commands"), list):
            commands = [str(x) for x in tool_input["commands"]]
        created = canvas.apply_commands(commands)
        return {
            "results": [
                {
                    "command": cmd,
                    "ok": True,
                    "labels": None,
                    "error": None,
                }
                for cmd in commands
            ],
            "created_objects": created,
            "deleted_objects": [],
            "rolled_back_objects": None,
            "rollback_errors": None,
            "dialogs": None,
            "preset_applied": "geometry",
            "quality_warnings": None,
        }

    if tool_name == "delete_objects":
        names: list[str] = []
        if isinstance(tool_input, dict) and isinstance(tool_input.get("objects"), list):
            names = [str(x) for x in tool_input.get("objects") or []]
        deleted = canvas.delete_objects(names)
        failed = [n for n in names if n not in deleted]
        return {
            "deleted_objects": deleted,
            "failed_objects": [{"object_name": n, "message": "not found"} for n in failed] if failed else None,
            "dialogs": None,
        }

    if tool_name == "eval_numeric":
        exprs: list[str] = []
        if isinstance(tool_input, dict) and isinstance(tool_input.get("expressions"), list):
            exprs = [str(x) for x in tool_input.get("expressions") or [] if str(x).strip()]
        coords = canvas.point_coords()
        results: list[dict[str, Any]] = []
        for expr in exprs[:24]:
            value = _try_eval_distance(expr, coords)
            if value is None:
                results.append(
                    {
                        "expression": expr,
                        "ok": False,
                        "value": None,
                        "value_string": None,
                        "temp_label": None,
                        "error": {"message": "unsupported expression in smoke stub"},
                    }
                )
            else:
                results.append(
                    {
                        "expression": expr,
                        "ok": True,
                        "value": float(value),
                        "value_string": str(float(value)),
                        "temp_label": None,
                        "error": None,
                    }
                )
        return {"results": results, "dialogs": None}

    return {"stub": True}


def _print_event(ev: SseEvent, *, verbose: bool) -> None:
    if not verbose:
        if ev.event in {"token"}:
            return
        print(f"- {ev.event}")
        return

    print(f"\n== {ev.event} ==")
    if isinstance(ev.data, (dict, list)):
        print(json.dumps(ev.data, ensure_ascii=False, indent=2))
    else:
        print(ev.data_raw)


def run_smoke(
    *,
    base_url: str,
    user_text: str,
    thread_id: str | None = None,
    canvas: FakeCanvas | None = None,
    timeout_s: float,
    verbose: bool,
    force_repair_once: bool,
) -> int:
    if thread_id is None:
        thread = _http_json(method="POST", url=f"{base_url}/api/threads", timeout_s=timeout_s)
        if not isinstance(thread, dict) or "thread_id" not in thread:
            print("ERR: failed to create thread", file=sys.stderr)
            return 2
        thread_id = str(thread["thread_id"])
        print(f"thread_id={thread_id}")
    else:
        print(f"thread_id={thread_id} (reused)")

    run_id: str | None = None
    interrupt: dict[str, Any] | None = None
    saw_protocol_version = False
    saw_budget = False
    canvas = canvas or FakeCanvas()
    saw_exec = False
    forced = False

    body = {"input": {"user_text": user_text}, "ui_context": {"debug": True, "plan_mode": True}}
    for ev in _http_sse(
        method="POST",
        url=f"{base_url}/api/threads/{thread_id}/runs/stream",
        body=body,
        timeout_s=timeout_s,
    ):
        _print_event(ev, verbose=verbose)
        if ev.event == "run_start" and isinstance(ev.data, dict):
            run_id = str(ev.data.get("run_id") or "")
            saw_protocol_version = bool(ev.data.get("protocol_version"))
        if ev.event == "budget":
            saw_budget = True
        if ev.event == "interrupt" and isinstance(ev.data, dict):
            interrupt = ev.data
            break
        if ev.event == "run_end":
            break

    if not run_id:
        print("ERR: did not receive run_start.run_id", file=sys.stderr)
        return 2
    if not saw_protocol_version:
        print("ERR: run_start.protocol_version missing", file=sys.stderr)
        return 2
    if not saw_budget:
        print("ERR: did not receive budget event", file=sys.stderr)
        return 2

    if interrupt is None:
        print("OK: run finished without interrupt (no tool required).")
        return 0

    for step in range(1, 10):
        tool_name = str(interrupt.get("tool_name") or "")
        tool_call_id = str(interrupt.get("tool_call_id") or "")
        tool_input = interrupt.get("input")
        if not tool_name or not tool_call_id:
            print("ERR: interrupt missing tool_name/tool_call_id", file=sys.stderr)
            return 2

        tool_output = _make_tool_output(
            tool_name=tool_name,
            tool_input=tool_input,
            canvas=canvas,
            force_repair_once=force_repair_once,
            saw_exec=saw_exec,
            forced=forced,
        )
        if tool_name == "exec_geogebra_commands":
            saw_exec = True
        if tool_name == "get_canvas_state" and isinstance(tool_output, dict) and tool_output.get("__forced_repair") is True:
            forced = True
            tool_output = {k: v for k, v in tool_output.items() if k != "__forced_repair"}
        resume_body = {
            "command": {
                "resume": {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "ok": True,
                    "output": tool_output,
                }
            }
        }
        interrupt = None
        saw_tool_end = False
        saw_budget = False

        for ev in _http_sse(
            method="POST",
            url=f"{base_url}/api/threads/{thread_id}/runs/{run_id}/resume",
            body=resume_body,
            timeout_s=timeout_s,
        ):
            _print_event(ev, verbose=verbose)
            if ev.event == "tool_end":
                saw_tool_end = True
            if ev.event == "budget":
                saw_budget = True
            if ev.event == "interrupt" and isinstance(ev.data, dict):
                interrupt = ev.data
                break
            if ev.event == "run_end":
                break

        if not saw_tool_end:
            print("ERR: resume did not produce tool_end", file=sys.stderr)
            return 2
        if not saw_budget:
            print("ERR: resume did not produce budget", file=sys.stderr)
            return 2
        if interrupt is None:
            print(f"OK: completed after {step} resume(s). run_id={run_id}")
            return 0

    print("ERR: too many interrupts; aborting", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="v2 API SSE smoke test (thread/run/interrupt/resume).")
    parser.add_argument("--base-url", default="http://127.0.0.1:3002", help="API base URL")
    parser.add_argument("--user-text", default="画一个圆", help="Input user_text for a single run")
    parser.add_argument("--turn", action="append", help="Run multiple turns in the SAME thread (repeatable)")
    parser.add_argument("--thread-id", help="Reuse an existing thread_id (optional)")
    parser.add_argument("--timeout-s", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON payloads")
    parser.add_argument("--force-repair-once", action="store_true", help="Force one verify failure to exercise repair loop")
    args = parser.parse_args(argv)

    try:
        base_url = args.base_url.rstrip("/")
        turns = [t for t in (args.turn or []) if isinstance(t, str) and t.strip()]
        if not turns:
            turns = [args.user_text]

        shared_canvas = FakeCanvas()
        thread_id = str(args.thread_id) if args.thread_id else None
        if thread_id is None:
            thread = _http_json(method="POST", url=f"{base_url}/api/threads", timeout_s=args.timeout_s)
            if not isinstance(thread, dict) or "thread_id" not in thread:
                print("ERR: failed to create thread", file=sys.stderr)
                return 2
            thread_id = str(thread["thread_id"])
            print(f"thread_id={thread_id}")

        for i, text in enumerate(turns, start=1):
            print(f"\n--- turn {i}/{len(turns)} ---")
            code = run_smoke(
                base_url=base_url,
                user_text=str(text),
                thread_id=thread_id,
                canvas=shared_canvas,
                timeout_s=args.timeout_s,
                verbose=args.verbose,
                force_repair_once=bool(args.force_repair_once) and i == 1,
            )
            if code != 0:
                return code

        return 0
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        print(f"HTTPError: {e.code} {e.reason}: {detail}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
