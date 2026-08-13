"""Dispatch model tool_calls to registered handlers."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Dict

from agent_window.tools.registry import registry

logger = logging.getLogger(__name__)


async def handle_function_call(name: str, arguments: Dict[str, Any] | str) -> str:
    spec = registry.get(name)
    if not spec:
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)

    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": arguments}
    else:
        args = arguments or {}

    try:
        result = spec.handler(args)
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except Exception as e:
        logger.exception("tool %s failed", name)
        return json.dumps({"error": str(e), "tool": name}, ensure_ascii=False)
