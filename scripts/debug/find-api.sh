#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
grep -rn "sessions\|stream\|SSE\|EventSource" "$ROOT/backend/src/agent_window" --include="*.py" | head -60
ls "$ROOT/backend/src/agent_window"
