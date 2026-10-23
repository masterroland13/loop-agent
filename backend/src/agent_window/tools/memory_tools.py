"""Memory tools — prepare USER.md / MEMORY.md proposals; settle via tool_pipeline."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agent_window.services.memory import create_memory_proposal, memory_to_public, normalize_memory_target
from agent_window.services.workspace import WorkspaceError
from agent_window.tools.registry import registry

AWAIT_MEMORY_KEY = "__await_memory__"


def _err(e: Exception) -> str:
    if isinstance(e, WorkspaceError):
        return json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False)
    return json.dumps({"error": str(e), "code": "TOOL_ERROR"}, ensure_ascii=False)


def _parse_operations(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise WorkspaceError(f"operations must be JSON array: {e}", "INVALID") from e
    if not isinstance(raw, list):
        raise WorkspaceError("operations must be a list of objects", "INVALID")
    return [op for op in raw if isinstance(op, dict)]


async def propose_memory_tool(args: Dict[str, Any]) -> str:
    try:
        target = normalize_memory_target(args.get("target"))
        operations = _parse_operations(args.get("operations"))
        action = args.get("action")
        action_s = str(action).strip().lower() if action is not None else ""
        content = args.get("content")
        content_s = "" if content is None else str(content)
        old_text = args.get("old_text")
        old_s = None if old_text is None else str(old_text)
        mode = (args.get("mode") or "replace").strip().lower()

        if operations is not None:
            item = create_memory_proposal(
                target=target,
                operations=operations,
            )
        elif action_s in ("add", "replace", "remove") or mode == "append":
            # mode=append → action=add (never blank-line paste)
            effective = action_s if action_s in ("add", "replace", "remove") else "add"
            item = create_memory_proposal(
                content_s,
                target=target,
                action=effective,
                old_text=old_s,
            )
        else:
            if content is None or content_s.strip() == "":
                if mode != "replace":
                    raise WorkspaceError(
                        "content is required (or use action=add|replace|remove / operations)",
                        "INVALID",
                    )
            item = create_memory_proposal(content_s, mode="replace", target=target)

        label = "MEMORY.md" if target == "memory" else "USER.md"
        return json.dumps(
            {
                AWAIT_MEMORY_KEY: True,
                "memory": memory_to_public(item),
                "message": f"{label} update proposed; waiting for user Apply/Reject.",
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
            "Propose an update to long-term curated memory. Does NOT write until approved "
            "(unless YOLO / confirm_memory off; Strict always confirms). "
            "target=user (default): USER.md — preferences, habits (~1375 chars). "
            "target=memory: MEMORY.md — workspace conventions, commands, pitfalls (~2200 chars). "
            "REQUIRED habit: use action=add to add one fact; action=replace/remove with old_text "
            "for edits. NEVER use mode=replace to append — that overwrites the entire file. "
            "mode=append is accepted as action=add. Exact duplicates → DUPLICATE error. "
            "Entries are stored separated by §. operations=[...] for atomic multi-edit. "
            "Ephemeral progress → not memory. How-to → Skills. "
            "Applied mid-session writes disk immediately; system snapshot frozen until new session."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Entry body for action=add|replace; for mode=replace only, full file body"
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": ["add", "replace", "remove"],
                    "description": (
                        "Preferred. add=one new entry; replace/remove need unique old_text"
                    ),
                },
                "old_text": {
                    "type": "string",
                    "description": "Unique substring identifying one entry (required for replace/remove)",
                },
                "operations": {
                    "type": "array",
                    "description": "Atomic batch of {action, content?, old_text?} (budget checked once)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["add", "replace", "remove"],
                            },
                            "content": {"type": "string"},
                            "old_text": {"type": "string"},
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append"],
                    "description": (
                        "append aliases action=add. replace overwrites ENTIRE file "
                        "(only to clear/rewrite); do not use replace to add a fact"
                    ),
                },
                "target": {
                    "type": "string",
                    "enum": ["user", "memory"],
                    "description": "user=USER.md preferences; memory=MEMORY.md environment/lessons",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=propose_memory_tool,
    )


register_memory_tools()
