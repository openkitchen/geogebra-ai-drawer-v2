#!/usr/bin/env bash
set -euo pipefail

# Build/compile v2 (web + api).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[v2] building web…"
cd "$ROOT_DIR/apps/web"
npm run build

echo "[v2] compiling api…"
cd "$ROOT_DIR/apps/api"
uv run python -m compileall app >/dev/null

echo "[v2] OK"

