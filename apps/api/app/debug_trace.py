from __future__ import annotations

import json
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Any

_logger = logging.getLogger("v2.debug_trace")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _repo_root() -> Path:
    # apps/api/app/debug_trace.py -> repo root
    return Path(__file__).resolve().parents[3]


def _parse_bool_env(key: str, *, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _trace_dir(ui_debug: bool) -> Path | None:
    # Enable trace by default when ui_debug=true (dev UX).
    enabled = _parse_bool_env("V2_TRACE_ENABLED", default=ui_debug)
    if not enabled:
        return None

    raw_dir = (os.getenv("V2_TRACE_DIR") or "").strip()
    if raw_dir:
        return Path(raw_dir)

    return _repo_root() / "logs" / "v2"


def trace_line(*, run_id: str, ui_debug: bool, kind: str, payload: dict[str, Any]) -> None:
    trace_dir = _trace_dir(ui_debug)
    if trace_dir is None:
        return

    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / f"run-{run_id}.jsonl"
        entry = {"ts_ms": _now_ms(), "run_id": run_id, "kind": kind, **payload}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Debug trace must never break the API.
        return


def trace_sse(*, run_id: str, ui_debug: bool, event: str, data: Any) -> None:
    trace_line(run_id=run_id, ui_debug=ui_debug, kind="sse", payload={"event": event, "data": data})


def trace_http(*, run_id: str, ui_debug: bool, name: str, data: Any) -> None:
    trace_line(run_id=run_id, ui_debug=ui_debug, kind="http", payload={"name": name, "data": data})


def trace_exception(*, run_id: str, ui_debug: bool, where: str, exc: BaseException) -> None:
    trace_line(
        run_id=run_id,
        ui_debug=ui_debug,
        kind="exception",
        payload={
            "where": where,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    )

    # Also surface exceptions to standard logs in dev/debug mode so they don't get lost in JSONL traces.
    try:
        if _trace_dir(ui_debug) is None:
            return
        msg = str(exc).replace("\r", " ").replace("\n", " ").strip()
        if len(msg) > 240:
            msg = msg[:240] + "…"
        _logger.warning("run_id=%s where=%s exc=%s: %s", run_id, where, type(exc).__name__, msg)
    except Exception:
        return
