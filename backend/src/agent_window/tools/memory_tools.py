"""Memory tools — propose USER.md updates (approval-gated in agent loop)."""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_window.services.memory import create_memory_proposal, memory_to_public
from agent_window.services.workspace import WorkspaceError
from agent_window.tools.registry import registry

AWAIT_MEMORY_KEY = "__await_memory__"


def _err(e: Exception) -> str:
    if isinstance(e, WorkspaceError):
        return json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False)
    return json.dumps({"error": str(e), "code": "TOOL_ERROR"}, ensure_ascii=False)


async def propose_memory_tool(args: Dict[str, Any]) -> str:
    try:
        content = args.get("content")
        if content is None or str(content).strip() == "":
            raise WorkspaceError("content is required", "INVALID")
        mode = (args.get("mode") or "replace").strip().lower()
        item = create_memory_proposal(str(content), mode=mode)
        return json.dumps(
            {
                AWAIT_MEMORY_KEY: True,
                "memory": memory_to_public(item),
                "message": "Memory update proposed; waiting for user Apply/Reject.",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _err(e)


def register_memory_tools() -> None:
    if registry.get("propose_memory"):
        return

    registry.register(
        name="propose_memory",
        description=(
            "Propose an update to the long-term USER.md memory file. "
            "Does NOT write until the user approves (unless confirm_memory is disabled). "
            "Use when the user asks to remember preferences, facts about themselves, or durable notes. "
            "mode=replace overwrites USER.md; mode=append adds a new section."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Markdown content to store in USER.md",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append"],
                    "description": "replace (default) or append",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        handler=propose_memory_tool,
    )


register_memory_tools()
