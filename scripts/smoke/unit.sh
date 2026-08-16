#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
export PYTHONPATH=src
PY="$ROOT/backend/.venv/bin/python"

echo "=== UNIT SMOKE ==="
"$PY" <<PY
import asyncio
from agent_window.services.shell import create_shell_proposal, decide_shell
from agent_window.services.workspace import WorkspaceError

root = r"""$ROOT"""
p = create_shell_proposal(["pwd"])
print("pwd proposal id:", p.id, "status:", p.status)
r = asyncio.run(decide_shell(p.id, "apply"))
print("pwd status:", r.status, "exit_code:", r.exit_code)
print("pwd stdout snippet:", repr(r.stdout)[:300])
print("pwd path ok:", root in (r.stdout or ""))

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
