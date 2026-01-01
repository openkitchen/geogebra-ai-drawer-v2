#!/usr/bin/env bash
set -euo pipefail

# Run v2 web + api together (recommended).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
exec npm run dev:v2

