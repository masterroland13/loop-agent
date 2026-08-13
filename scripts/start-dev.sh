#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/caapap/agent window"
BACKEND="$ROOT/backend"

fuser -k 8000/tcp 5173/tcp 2>/dev/null || true

cd "$BACKEND"
nohup uv run uvicorn agent_window.main:app --host 0.0.0.0 --port 8000 > /tmp/agent-backend.log 2>&1 &
echo "Backend PID: $!"

cd "$ROOT"
# Vite dev server exits when started via nohup from a short-lived shell.
# Use Windows preview server instead (see below) or run vite in a dedicated terminal:
#   cd "/home/caapap/agent window" && npm run dev -- --host 0.0.0.0 --port 5173
echo "Frontend (prefer a dedicated terminal with HMR):"
echo "  cd \"$ROOT\" && npm run dev -- --host 0.0.0.0 --port 5173"
echo "Or Windows preview after build:"
echo "  node scripts/preview-server.mjs"
echo "  -> http://localhost:5173/"
echo
sleep 2
echo "=== backend health ==="
curl -s http://127.0.0.1:8000/health || echo "backend not ready"
echo
