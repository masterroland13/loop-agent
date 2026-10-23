"""read_attachment tool — session attachments via ContextVar."""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_window.models import get_sessionmaker
from agent_window.services.attachment_context import get_attachment_session_id
from agent_window.services.attachments import AttachmentError, read_attachment_text
from agent_window.services.storage import get_session
from agent_window.tools.registry import registry


def _ok(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, code: str) -> str:
    return json.dumps({"error": message, "code": code}, ensure_ascii=False)


async def read_attachment_tool(args: Dict[str, Any]) -> str:
    session_id = get_attachment_session_id()
    if not session_id:
        return _err(
            "no attachment session context; read_attachment only works during a chat turn",
            "NO_SESSION_CONTEXT",
        )
    attachment_id = (args.get("attachment_id") or "").strip()
    if not attachment_id:
        return _err("attachment_id is required", "INVALID_ARGS")

    db = get_sessionmaker()()
    try:
        session = get_session(db, session_id)
        if not session:
            return _err("session not found", "SESSION_NOT_FOUND")
        offset = int(args.get("offset") or 1)
        limit = int(args.get("limit") or 200)
        try:
            result = read_attachment_text(session, attachment_id, offset=offset, limit=limit)
        except AttachmentError as e:
            return _err(str(e), e.code)
        return _ok(result)
    finally:
        db.close()


def register_attachment_tools() -> None:
    if registry.get("read_attachment"):
        return
    registry.register(
        name="read_attachment",
        description=(
            "Read a text chat attachment by attachment_id from the [附件] block. "
            "Do not use for images (pixels are already injected as vision input) or PDF "
            "(not extracted yet). Returns numbered text lines; binary/image/PDF return NOT_TEXT."
        ),
        parameters={
            "type": "object",
            "properties": {
                "attachment_id": {
                    "type": "string",
                    "description": "Attachment id from the user message [附件] block",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-based start line (default 1)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to return (default 200, max 500)",
                },
            },
            "required": ["attachment_id"],
            "additionalProperties": False,
        },
        handler=read_attachment_tool,
    )


register_attachment_tools()
