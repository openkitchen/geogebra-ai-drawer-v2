#!/usr/bin/env bash
set -euo pipefail

# Run web + api together (recommended).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API_PORT="${API_PORT:-3002}"
export API_PORT

api_pid=""
web_pid=""
studio_pid=""

cleanup() {
  if [[ -n "${api_pid}" ]]; then kill "${api_pid}" >/dev/null 2>&1 || true; fi
  if [[ -n "${web_pid}" ]]; then kill "${web_pid}" >/dev/null 2>&1 || true; fi
  if [[ -n "${studio_pid}" ]]; then kill "${studio_pid}" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

"$ROOT_DIR/scripts/v2_api_dev.sh" &
api_pid="$!"

"$ROOT_DIR/scripts/v2_web_dev.sh" &
web_pid="$!"

WITH_STUDIO="${V2_WITH_STUDIO:-}"
if [[ -n "$WITH_STUDIO" && "$WITH_STUDIO" != "0" && "$WITH_STUDIO" != "false" ]]; then
  # Start Studio server without opening a browser by default (LangSmith hosts the UI).
  "$ROOT_DIR/scripts/v2_langgraph_studio.sh" --no-browser &
  studio_pid="$!"
fi

wait "$api_pid"
wait "$web_pid"
