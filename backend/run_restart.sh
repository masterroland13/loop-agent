#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/caapap/agent window"
sed -i 's/\r$//' "$ROOT/scripts/restart-loop.sh"
bash "$ROOT/scripts/restart-loop.sh"
sleep 8
echo "=== VERIFY AFTER 8s ==="
ss -ltnp 2>/dev/null | grep 8000 || true
ss -ltnp 2>/dev/null | grep 5173 || true
curl -sS --max-time 3 http://127.0.0.1:8000/health || true
echo
curl -sS -o /dev/null -w "frontend=%{http_code}\n" --max-time 3 http://127.0.0.1:5173/ || true
cat "$ROOT/logs/loop-restart-report.txt"
