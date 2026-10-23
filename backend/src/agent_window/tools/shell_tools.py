"""Shell tools — prepare only; settle/run is tool_pipeline before_tool_call (Gate Step 3)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from agent_window.services.shell import create_shell_proposal, shell_to_public
from agent_window.services.workspace import WorkspaceError
from agent_window.tools.registry import registry

AWAIT_SHELL_KEY = "__await_shell__"


def _err(e: Exception) -> str:
    if isinstance(e, WorkspaceError):
        return json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False)
    return json.dumps({"error": str(e), "code": "TOOL_ERROR"}, ensure_ascii=False)


async def propose_shell_tool(args: Dict[str, Any]) -> str:
    try:
        argv = args.get("argv")
        if isinstance(argv, str):
            # allow accidental string; reject — require list
            raise WorkspaceError("argv must be a JSON array of strings, e.g. [\"pytest\",\"-q\"]", "INVALID_ARGV")
        if not isinstance(argv, list):
            raise WorkspaceError("argv is required (array of strings)", "INVALID_ARGV")

        cwd = (args.get("cwd") or ".").strip() or "."
        item = create_shell_proposal([str(x) for x in argv], cwd=cwd)
        public = shell_to_public(item)
        return json.dumps(
            {
                AWAIT_SHELL_KEY: True,
                "shell": public,
                "message": "Command proposed; waiting for user Apply/Reject.",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _err(e)


def register_shell_tools() -> None:
    if registry.get("propose_shell"):
        return

    registry.register(
        name="propose_shell",
        description=(
            "Propose a whitelisted command to run in the workspace. Does NOT execute until the user approves. "
            "Pass argv as an array (no shell piping). Examples: [\"pytest\",\"-q\"], [\"npm\",\"test\"], "
            "[\"git\",\"status\"], [\"ls\",\"-la\"]. Optional cwd is relative to workspace root. "
            "Use after edits to verify tests."
        ),
        parameters={
            "type": "object",
            "properties": {
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command and arguments as separate strings (no shell syntax)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory relative to workspace (default '.')",
                },
            },
            "required": ["argv"],
            "additionalProperties": False,
        },
        handler=propose_shell_tool,
    )


register_shell_tools()
