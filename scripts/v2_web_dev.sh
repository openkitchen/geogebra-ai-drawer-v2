#!/usr/bin/env bash
set -euo pipefail

# Run v2 Web UI (React/Vite) only.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/apps/web"
exec npm run dev

