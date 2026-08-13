"""Local filesystem tools (read-only) — register on import."""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_window.services.workspace import (
    WorkspaceError,
    grep_search,
    list_directory,
    read_file,
)
from agent_window.tools.registry import registry


def _ok(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(e: Exception) -> str:
    if isinstance(e, WorkspaceError):
        return json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False)
    return json.dumps({"error": str(e), "code": "TOOL_ERROR"}, ensure_ascii=False)


async def list_dir_tool(args: Dict[str, Any]) -> str:
    try:
        return _ok(list_directory(path=args.get("path") or "."))
    except Exception as e:
        return _err(e)


async def read_file_tool(args: Dict[str, Any]) -> str:
    try:
        path = (args.get("path") or "").strip()
        if not path:
            raise WorkspaceError("path is required", "INVALID_PATH")
        offset = int(args.get("offset") or 1)
        limit = int(args.get("limit") or 200)
        return _ok(read_file(path=path, offset=offset, limit=limit))
    except Exception as e:
        return _err(e)


async def grep_tool(args: Dict[str, Any]) -> str:
    try:
        pattern = (args.get("pattern") or "").strip()
        return _ok(
            grep_search(
                pattern=pattern,
                path=args.get("path") or ".",
                glob=args.get("glob") or "*",
                case_insensitive=bool(args.get("case_insensitive") or False),
            )
        )
    except Exception as e:
        return _err(e)


def register_fs_tools() -> None:
    if registry.get("list_dir"):
        return

    registry.register(
        name="list_dir",
        description=(
            "List files and directories under the workspace. "
            "Paths are relative to the workspace root. Use '.' for root."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path (default '.')",
                },
            },
            "additionalProperties": False,
        },
        handler=list_dir_tool,
    )

    registry.register(
        name="read_file",
        description=(
            "Read a text file from the workspace with optional line window. "
            "Returns numbered lines. Prefer small limits; re-call with offset to page."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace root"},
                "offset": {
                    "type": "integer",
                    "description": "1-based start line (default 1)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to return (default 200, max 500)",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=read_file_tool,
    )

    registry.register(
        name="grep",
        description=(
            "Search file contents in the workspace with a regex pattern. "
            "Optional glob filter like '*.py'. Returns matching lines with paths."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search"},
                "path": {
                    "type": "string",
                    "description": "Relative file or directory to search (default '.')",
                },
                "glob": {
                    "type": "string",
                    "description": "Filename glob filter, e.g. '*.ts' (default '*')",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive match (default false)",
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        handler=grep_tool,
    )


register_fs_tools()
