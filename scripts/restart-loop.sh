#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/caapap/agent window"
REPORT="$ROOT/logs/loop-restart-report.txt"
: > "$REPORT"

log() { echo "$1" | tee -a "$REPORT"; }

log "=== Loop restart $(date) ==="

for port in 8000 5173; do
  if fuser -n tcp "$port" >/dev/null 2>&1; then
    fuser -k -n tcp "$port" >/dev/null 2>&1 || true
    sleep 1
  fi
done
pkill -f 'uvicorn agent_window.main:app' 2>/dev/null || true
pkill -f 'vite.*5173' 2>/dev/null || true
pkill -f 'npm run dev.*5173' 2>/dev/null || true
sleep 1

cd "$ROOT/backend"
setsid env PYTHONPATH=src .venv/bin/uvicorn agent_window.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/loop-backend.log 2>&1 < /dev/null &
BACKEND_PID=$!
log "backend_pid=$BACKEND_PID"

cd "$ROOT"
export NVM_DIR="${HOME}/.nvm"
# shellcheck disable=SC1090
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
# ~/.local/bin/node shims to Windows node.exe and breaks Linux npm
# (Cannot find module '\\wsl.localhost\...\npm'). Force nvm's Linux node first.
NODE_DIR="$(ls -d "${NVM_DIR}"/versions/node/*/bin 2>/dev/null | tail -1 || true)"
export PATH="${NODE_DIR}:/usr/bin:/bin"
hash -r
log "node=$(command -v node)"
log "npm=$(command -v npm)"
setsid env PATH="$PATH" npm run dev -- --host 0.0.0.0 --port 5173 \
  > /tmp/loop-frontend.log 2>&1 < /dev/null &
FRONTEND_PID=$!
log "frontend_pid=$FRONTEND_PID"

sleep 6
log "--- health ---"
curl -sS --max-time 5 http://127.0.0.1:8000/health | tee -a "$REPORT" || log "backend health FAILED"
echo >> "$REPORT"
FRONT_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:5173/ || echo "000")
log "frontend_http=$FRONT_CODE"
log "--- listeners ---"
ss -ltnp 2>/dev/null | grep -E '8000|5173' >> "$REPORT" || true
log "--- backend log tail ---"
tail -15 /tmp/loop-backend.log >> "$REPORT" 2>&1 || true
log "--- frontend log tail ---"
tail -15 /tmp/loop-frontend.log >> "$REPORT" 2>&1 || true
log "=== done ==="
