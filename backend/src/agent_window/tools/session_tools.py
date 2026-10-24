"""search_session — recover folded transcript / spill excerpts (C4)."""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_window.models import get_sessionmaker
from agent_window.services.attachment_context import get_attachment_session_id
from agent_window.services.session_search import SessionSearchError, search_session_records
from agent_window.services.storage import get_session
from agent_window.tools.registry import registry


def _ok(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, code: str) -> str:
    return json.dumps({"error": message, "code": code}, ensure_ascii=False)


async def search_session_tool(args: Dict[str, Any]) -> str:
    bound = get_attachment_session_id()
    if not bound:
        return _err(
            "no session context; search_session only works during a chat turn",
            "NO_SESSION_CONTEXT",
        )
    requested = str(args.get("session_id") or "").strip()
    if requested and requested != bound:
        return _err("cannot search another session", "SESSION_FORBIDDEN")

    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query is required", "INVALID_ARGS")

    db = get_sessionmaker()()
    try:
        session = get_session(db, bound)
        if not session:
            return _err("session not found", "SESSION_NOT_FOUND")
        try:
            max_hits = int(args.get("max_hits") or 8)
        except (TypeError, ValueError):
            return _err("max_hits must be an integer", "INVALID_ARGS")
        path = str(args.get("path") or "").strip() or None
        result = search_session_records(session, query, max_hits=max_hits, path=path)
        return _ok(result)
    except SessionSearchError as exc:
        return _err(str(exc), exc.code)
    finally:
        db.close()


def register_session_tools() -> None:
    if registry.get("search_session"):
        return
    registry.register(
        name="search_session",
        description=(
            "Search this session's pre-compression transcript and spilled tool "
            "outputs for a keyword. Returns short excerpts with line numbers. "
            "Use when a compaction summary omitted a path, quote, or tool detail. "
            "Cannot search other sessions, the workspace, or .env."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to find (all terms must match)",
                },
                "max_hits": {
                    "type": "integer",
                    "description": "Max excerpts to return (default 8, max 12)",
                },
                "path": {
                    "type": "string",
                    "description": "Optional transcript.jsonl or turns/... path inside this session only",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=search_session_tool,
    )


register_session_tools()
