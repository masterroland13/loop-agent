#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
export PYTHONPATH=src
PY="$ROOT/backend/.venv/bin/python"

echo "=== IMPORT CHECK ==="
"$PY" -c 'from agent_window.tools import registry; names=registry.list_names(); print("list_names:", names); print("has_propose_shell:", "propose_shell" in names)'

echo "=== PUT WORKSPACE ==="
curl -s -X PUT http://127.0.0.1:8000/api/workspace -H "Content-Type: application/json" -d "{\"root\":\"$ROOT\"}"
echo
curl -s http://127.0.0.1:8000/api/workspace
echo

echo "=== UNIT SMOKE ==="
"$PY" <<'PY'
import asyncio
from agent_window.services.shell import create_shell_proposal, decide_shell
from agent_window.services.workspace import WorkspaceError

p = create_shell_proposal(["pwd"])
print("pwd proposal id:", p.id, "status:", p.status)
r = asyncio.run(decide_shell(p.id, "apply"))
print("pwd status:", r.status, "exit_code:", r.exit_code)
print("pwd stdout snippet:", repr(r.stdout)[:300])

try:
    create_shell_proposal(["rm", "-rf", "/"])
    print("rm_rf: UNEXPECTED SUCCESS")
except WorkspaceError as e:
    print("rm_rf WorkspaceError code:", e.code, "msg:", e)

try:
    create_shell_proposal(["git", "push"])
    print("git_push: UNEXPECTED SUCCESS")
except WorkspaceError as e:
    print("git_push WorkspaceError code:", e.code, "msg:", e)
PY
