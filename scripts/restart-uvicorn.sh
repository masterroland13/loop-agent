#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fuser -k 8000/tcp 2>/dev/null || true
sleep 1
cd "$ROOT/backend"
PYTHONPATH=src nohup .venv/bin/uvicorn agent_window.main:app --host 0.0.0.0 --port 8000 > /tmp/hal-agent-uvicorn.log 2>&1 &
echo "PID $!"
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then
    echo "health ok ($code)"
    curl -s http://127.0.0.1:8000/health
    echo
    exit 0
  fi
  sleep 1
done
echo "health fail"
tail -30 /tmp/hal-agent-uvicorn.log
exit 1
