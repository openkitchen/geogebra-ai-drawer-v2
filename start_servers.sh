#!/bin/bash
# start_servers.v2.sh
export PATH=$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
(cd apps/api && uv run uvicorn app.main:app --host 127.0.0.1 --port 3002 > ../../logs/api_background.log 2>&1) &
(cd apps/web && npm run dev -- --port 3000 --host 127.0.0.1 > ../../logs/web_background.log 2>&1) &
disown