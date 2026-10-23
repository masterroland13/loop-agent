#!/bin/bash
set -e
cd "/home/caapap/agent window/backend"
export PYTHONPATH=src
.venv/bin/python scripts/cleanup_empty_messages.py
pids=$(pgrep -f "uvicorn agent_window.main:app" || true)
echo "old_pids=$pids"
if [ -n "$pids" ]; then
  kill $pids || true
  sleep 1
fi
nohup .venv/bin/uvicorn agent_window.main:app --host 0.0.0.0 --port 8000 > /tmp/loop-agent-api.log 2>&1 &
sleep 2
curl -s http://127.0.0.1:8000/health
echo
