#!/usr/bin/env bash
set -euo pipefail

# Minimal acceptance gate for v2 API:
# - /healthz reachable
# - /api/schema/v2 has protocol_version
# - thread/run SSE + interrupt/resume works (via v2_smoke_test.py)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API_PORT="${API_PORT:-3002}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${API_PORT}}"
BASE_URL="${BASE_URL%/}"

echo "v2 acceptance (api): base_url=${BASE_URL}"

BASE_URL="$BASE_URL" python3 - <<'PY'
import json
import sys
import os
import urllib.request

base_url = str(os.environ.get("BASE_URL") or "").rstrip("/")
if not base_url:
    print("ERR: BASE_URL is empty", file=sys.stderr)
    raise SystemExit(2)

def get(path: str, *, accept: str = "application/json", timeout_s: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url=f"{base_url}{path}",
        headers={"Accept": accept},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.status, resp.read().decode("utf-8")

try:
    status, _ = get("/healthz")
except Exception as e:
    print(f"ERR: cannot reach API at {base_url}: {type(e).__name__}: {e}", file=sys.stderr)
    raise SystemExit(2)
if status != 200:
    print(f"ERR: GET /healthz status={status}", file=sys.stderr)
    raise SystemExit(2)
print("OK: GET /healthz")

status, raw = get("/api/schema/v2")
if status != 200:
    print(f"ERR: GET /api/schema/v2 status={status}", file=sys.stderr)
    raise SystemExit(2)

try:
    payload = json.loads(raw) if raw else None
except Exception:
    print("ERR: /api/schema/v2 did not return JSON", file=sys.stderr)
    raise SystemExit(2)

protocol_version = payload.get("protocol_version") if isinstance(payload, dict) else None
if not protocol_version:
    print("ERR: /api/schema/v2 missing protocol_version", file=sys.stderr)
    raise SystemExit(2)
print(f"OK: GET /api/schema/v2 protocol_version={protocol_version}")
PY

echo "== smoke: SSE + interrupt/resume (+ repair once) =="
FAIL_ON_EXCEPTION="${V2_ACCEPTANCE_FAIL_ON_EXCEPTION:-1}"
if [[ "$FAIL_ON_EXCEPTION" != "0" && "$FAIL_ON_EXCEPTION" != "false" ]]; then
  python3 "$ROOT_DIR/scripts/v2_smoke_test.py" \
    --base-url "$BASE_URL" \
    --turn "画一个圆" \
    --turn "再画一个三角形ABC" \
    --require-tool exec_geogebra_commands \
    --fail-on-exception \
    --force-repair-once
else
  python3 "$ROOT_DIR/scripts/v2_smoke_test.py" \
    --base-url "$BASE_URL" \
    --turn "画一个圆" \
    --turn "再画一个三角形ABC" \
    --require-tool exec_geogebra_commands \
    --force-repair-once
fi

echo "== smoke: hard-mode signals (difficulty_update + phase_update) =="
if [[ "$FAIL_ON_EXCEPTION" != "0" && "$FAIL_ON_EXCEPTION" != "false" ]]; then
  python3 "$ROOT_DIR/scripts/v2_smoke_test.py" \
    --base-url "$BASE_URL" \
    --user-text "画一个圆" \
    --force-hard-mode \
    --require-tool exec_geogebra_commands \
    --require-plan-update \
    --require-difficulty hard \
    --require-phase Plan \
    --require-phase Understand \
    --require-phase Verify \
    --fail-on-exception
else
  python3 "$ROOT_DIR/scripts/v2_smoke_test.py" \
    --base-url "$BASE_URL" \
    --user-text "画一个圆" \
    --force-hard-mode \
    --require-tool exec_geogebra_commands \
    --require-plan-update \
    --require-difficulty hard \
    --require-phase Plan \
    --require-phase Understand \
    --require-phase Verify
fi

echo "== smoke: reasoning trace helper (no LLM) =="
ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os
import pathlib
import tempfile
import sys

root_dir = pathlib.Path(os.environ["ROOT_DIR"]).resolve()
api_dir = root_dir / "apps" / "api"
sys.path.insert(0, str(api_dir))

from app.debug_trace import trace_reasoning_to_file  # type: ignore

with tempfile.TemporaryDirectory() as td:
    os.environ["V2_TRACE_DIR"] = td

    # Disabled by default
    os.environ.pop("V2_TRACE_REASONING", None)
    assert trace_reasoning_to_file(run_id="r0", op="op", role="role", text="abc") is None

    # Enabled + truncation behavior
    os.environ["V2_TRACE_REASONING"] = "1"
    os.environ["V2_TRACE_REASONING_MAX_CHARS"] = "10000"
    meta = trace_reasoning_to_file(run_id="r1", op="op", role="role", text=("a" * 10050))
    assert isinstance(meta, dict) and meta.get("reasoning_file"), meta
    p = pathlib.Path(str(meta["reasoning_file"]))
    assert p.exists(), p
    saved = p.read_text(encoding="utf-8")
    assert len(saved) == 10000, len(saved)
    assert meta.get("reasoning_truncated") is True, meta

print("OK: reasoning trace helper smoke passed.")
PY

echo "OK: v2 acceptance (api) passed."
echo "NOTE: This script validates ai-api only. Full acceptance still requires a browser run for ai-web (see docs/self-test.md)."
