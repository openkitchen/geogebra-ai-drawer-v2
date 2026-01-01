#!/usr/bin/env bash
set -euo pipefail

# Run v2 Web UI (React/Vite) only.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/apps/web"

if [[ ! -d node_modules ]]; then
  echo "[web] node_modules not found. Installing dependencies…"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
fi

exec npm run dev
