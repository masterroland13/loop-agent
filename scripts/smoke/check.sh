#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || { echo "cd root failed"; exit 1; }
echo "=== VENV SEARCH ==="
for p in .venv venv backend/.venv backend/venv; do
  if [ -d "$p" ]; then
    echo "FOUND_VENV=$p"
    ls -la "$p/bin/python" "$p/bin/python3" 2>&1 || true
  fi
done
echo "=== PROCESSES ==="
ps aux | grep -E 'uvicorn|vite' | grep -v grep || true
echo "EXIT_PS=$?"
echo "=== IMPORT LOOP ==="
cd "$ROOT/backend" || { echo "cd backend failed"; exit 1; }
PY=python3
if [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
elif [ -x "$ROOT/backend/venv/bin/python" ]; then
  PY="$ROOT/backend/venv/bin/python"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
  PY="$ROOT/venv/bin/python"
fi
echo "Using PY=$PY"
set +e
PYTHONPATH=src "$PY" -c "from agent_window.agent.loop import run_agent_loop; from agent_window.tools import registry; print('tools:', registry.list_names()); print('ok')"
echo "EXIT1=$?"
echo "=== IMPORT ROUTES ==="
PYTHONPATH=src "$PY" -c "import agent_window.api.routes; print('routes ok')"
echo "EXIT_ROUTES=$?"
