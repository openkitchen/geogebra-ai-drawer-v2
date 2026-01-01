#!/usr/bin/env bash
set -euo pipefail

# Start LangGraph Studio (LangGraph API server in dev mode) for v2.
# Note: Studio is hosted on LangSmith web UI; this script starts a local server that Studio connects to.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
CONFIG_PATH="$API_DIR/langgraph.json"
GEN_CONFIG_SCRIPT="$ROOT_DIR/scripts/v2_generate_langgraph_json.py"

PORT="${LANGGRAPH_PORT:-2024}"
HOST="${LANGGRAPH_HOST:-127.0.0.1}"

REGEN_CONFIG="false"
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --regen-config)
      REGEN_CONFIG="true"
      ;;
    --tunnel)
      EXTRA_ARGS+=("--tunnel")
      ;;
    --no-browser)
      EXTRA_ARGS+=("--no-browser")
      ;;
    *)
      EXTRA_ARGS+=("$arg")
      ;;
  esac
done

if [[ "$REGEN_CONFIG" == "true" || ! -f "$CONFIG_PATH" ]]; then
  echo "[studio] Generating LangGraph config…"
  python3 "$GEN_CONFIG_SCRIPT"
fi

echo "[studio] Starting LangGraph dev server…"
echo "[studio] config=$CONFIG_PATH"
echo "[studio] host=$HOST port=$PORT"
echo "[studio] Tip: pass --tunnel if your browser blocks localhost."

cd "$API_DIR"

# We intentionally run the CLI via `uv tool run` so you don't need to add langgraph-cli to project deps.
# Use the [inmem] extra to avoid requiring external infrastructure for local dev.
exec uv tool run --from "langgraph-cli[inmem]" langgraph dev \
  --config "$CONFIG_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  "${EXTRA_ARGS[@]}"
