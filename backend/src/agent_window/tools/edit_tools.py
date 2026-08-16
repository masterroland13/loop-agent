"""Edit tools — propose only; disk write happens after user approval in the agent loop."""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_window.services.patches import (
    create_patch_from_content,
    create_patch_from_replace,
    patch_to_public,
)
from agent_window.services.workspace import WorkspaceError
from agent_window.tools.registry import registry

# Marker consumed by agent loop — do not write to disk here.
AWAIT_PATCH_KEY = "__await_patch__"


def _err(e: Exception) -> str:
    if isinstance(e, WorkspaceError):
        return json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False)
    return json.dumps({"error": str(e), "code": "TOOL_ERROR"}, ensure_ascii=False)


async def propose_edit_tool(args: Dict[str, Any]) -> str:
    """
    Propose a file edit. Returns a special payload so the agent loop can
    emit a diff SSE event and wait for Apply/Reject before continuing.
    """
    try:
        path = (args.get("path") or "").strip()
        if not path:
            raise WorkspaceError("path is required", "INVALID_PATH")

        old_string = args.get("old_string")
        new_string = args.get("new_string")
        content = args.get("content")

        if content is not None and old_string is None and new_string is None:
            patch = create_patch_from_content(path, str(content))
        elif old_string is not None and new_string is not None:
            patch = create_patch_from_replace(path, str(old_string), str(new_string))
        else:
            raise WorkspaceError(
                "provide either content (full file), or old_string+new_string (search-replace)",
                "INVALID_ARGS",
            )

        public = patch_to_public(patch)
        return json.dumps(
            {
                AWAIT_PATCH_KEY: True,
                "patch": public,
                "message": "Edit proposed; waiting for user Apply/Reject.",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _err(e)


def register_edit_tools() -> None:
    if registry.get("propose_edit"):
        return

    registry.register(
        name="propose_edit",
        description=(
            "Propose a file change in the workspace. Does NOT write until the user approves. "
            "Prefer search-replace: path + old_string + new_string (old_string must be unique). "
            "For new files or full rewrites, pass path + content. "
            "Always read_file first when editing existing files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace root",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to find (search-replace mode)",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text (search-replace mode)",
                },
                "content": {
                    "type": "string",
                    "description": "Full new file contents (create or overwrite mode)",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=propose_edit_tool,
    )


register_edit_tools()
