#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def _iter_kind(entries: Iterable[dict[str, Any]], kind: str) -> Iterable[dict[str, Any]]:
    for e in entries:
        if e.get("kind") == kind:
            yield e


def _first_http(entries: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for e in _iter_kind(entries, "http"):
        if e.get("name") == name and isinstance(e.get("data"), dict):
            return e["data"]
    return None


def _first_sse(entries: list[dict[str, Any]], event: str) -> Any | None:
    for e in _iter_kind(entries, "sse"):
        if e.get("event") == event:
            return e.get("data")
    return None


def _all_sse(entries: list[dict[str, Any]], event: str) -> list[Any]:
    out: list[Any] = []
    for e in _iter_kind(entries, "sse"):
        if e.get("event") == event:
            out.append(e.get("data"))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect v2 run trace (logs/v2/run-<run_id>.jsonl).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", help="Run id shown in UI Timeline run_start.")
    g.add_argument("--trace-file", help="Path to logs/v2/run-<run_id>.jsonl")
    p.add_argument("--trace-dir", default="logs/v2", help="Trace directory (default: logs/v2)")
    args = p.parse_args()

    trace_path: Path
    if args.trace_file:
        trace_path = Path(args.trace_file).expanduser().resolve()
    else:
        trace_dir = Path(args.trace_dir).expanduser().resolve()
        trace_path = trace_dir / f"run-{args.run_id}.jsonl"

    if not trace_path.exists():
        print(f"ERR: trace file not found: {trace_path}")
        return 2

    entries = _load_jsonl(trace_path)
    if not entries:
        print(f"ERR: empty/invalid trace: {trace_path}")
        return 2

    run_id = str(entries[0].get("run_id") or "")
    print(f"trace: {trace_path}")
    if run_id:
        print(f"run_id: {run_id}")

    req = _first_http(entries, "runs_stream.request") or {}
    if isinstance(req, dict) and req:
        user_text = req.get("user_text")
        print(f"user_text: {user_text!r}")
        ui_context = req.get("ui_context")
        if isinstance(ui_context, dict):
            debug = ui_context.get("debug")
            plan_mode = ui_context.get("plan_mode")
            print(f"ui_context: debug={debug} plan_mode={plan_mode}")

    diff = _first_sse(entries, "difficulty_update")
    if isinstance(diff, dict):
        print("\n[difficulty_update]")
        print(f"difficulty: {diff.get('difficulty')} hard_mode={diff.get('hard_mode')} confidence={diff.get('confidence')}")
        reasons = diff.get("reasons")
        if isinstance(reasons, list) and reasons:
            print("reasons:")
            for r in reasons[:12]:
                if isinstance(r, str) and r.strip():
                    print(f"- {r.strip()}")

    phases = _all_sse(entries, "phase_update")
    if phases:
        print("\n[phase_update]")
        for p2 in phases[-20:]:
            if not isinstance(p2, dict):
                continue
            seq = p2.get("seq")
            phase = p2.get("phase")
            summary = p2.get("summary")
            result = p2.get("result")
            nxt = p2.get("next")
            line = f"#{seq} {phase}"
            if isinstance(summary, str) and summary.strip():
                line += f" · {summary.strip()}"
            if isinstance(result, str) and result.strip():
                line += f" · result={result.strip()}"
            if isinstance(nxt, str) and nxt.strip():
                line += f" · next={nxt.strip()}"
            print(line)

    exceptions: list[dict[str, Any]] = []
    for e in _iter_kind(entries, "exception"):
        exceptions.append(e)
    if exceptions:
        print("\n[exceptions]")
        for ex in exceptions[-5:]:
            where = ex.get("where")
            typ = ex.get("type")
            msg = ex.get("message")
            print(f"- where={where} type={typ} message={msg}")

    tools = _all_sse(entries, "tool_start")
    if tools:
        by_name: dict[str, int] = {}
        for t in tools:
            if not isinstance(t, dict):
                continue
            name = t.get("tool_name")
            if not isinstance(name, str) or not name:
                continue
            by_name[name] = by_name.get(name, 0) + 1
        if by_name:
            print("\n[tools]")
            for k in sorted(by_name.keys()):
                print(f"- {k}: {by_name[k]}")

    final = _first_sse(entries, "final")
    if isinstance(final, dict):
        answer = final.get("answer")
        if isinstance(answer, dict):
            expl = answer.get("explanation")
            if isinstance(expl, str):
                preview = expl.strip().replace("\n", " ")
                if len(preview) > 120:
                    preview = preview[:120] + "…"
                print(f"\n[final] {preview}")

    print("\nOK: trace inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

