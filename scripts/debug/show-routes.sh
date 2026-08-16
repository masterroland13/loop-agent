#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
sed -n '48,230p' "$ROOT/backend/src/agent_window/api/routes.py"
