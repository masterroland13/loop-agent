#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
PYTHONPATH=src .venv/bin/python -c "
import asyncio
from agent_window.tools.builtin import get_weather_tool
print(asyncio.run(get_weather_tool({'city':'合肥'})))
"
