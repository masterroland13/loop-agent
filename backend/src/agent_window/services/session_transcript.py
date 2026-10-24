"""Append-only session transcript (C0). Lives under session.data_path in APP_DATA_DIR."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agent_window.config import settings

logger = logging.getLogger(__name__)

TRANSCRIPT_NAME = "transcript.jsonl"

_SECRET_KEY_RE = re.compile(
    r"^(x-api-key|api[_-]?key|llm_api_key|authorization|password|secret(_?key)?"
    r"|private_key|access_token|refresh_token|token)$",
    re.IGNORECASE,
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|password|secret)\s*[:=]\s*\S+",
)
_SK_TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def _resolved_transcript_path(session: Any) -> Path | None:
    """JSONL lives under APP_DATA_DIR / session.data_path. Refuse escape."""
    rel = getattr(session, "data_path", None) or ""
    if not rel or Path(rel).is_absolute():
        return None
    base = Path(settings.app_data_dir).resolve()
    dest = (base / rel / TRANSCRIPT_NAME).resolve()
    try:
        dest.relative_to(base)
    except ValueError:
        return None
    return dest


def transcript_path(session: Any) -> Path:
    resolved = _resolved_transcript_path(session)
    if resolved is not None:
        return resolved
    rel = getattr(session, "data_path", None) or "_invalid"
    return Path(settings.app_data_dir) / Path(rel).name / TRANSCRIPT_NAME


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY_RE.match(str(key)):
                out[str(key)] = "[redacted]"
            else:
                out[str(key)] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        text = _SECRET_ASSIGN_RE.sub(r"\1=[redacted]", value)
        return _SK_TOKEN_RE.sub("[redacted]", text)
    return value


def _slim_attachments(raw: str | None) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    slim: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        slim.append({"id": item.get("id"), "filename": item.get("filename")})
    return slim


def append_transcript_event(
    session: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one JSON line. Never truncates. Failures do not raise."""
    try:
        path = _resolved_transcript_path(session)
        if path is None or not path.parent.is_dir():
            return
        body = redact_value(dict(payload or {}))
        if not isinstance(body, dict):
            body = {"payload": body}
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **body,
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        logger.exception("session transcript append failed")


def append_message_event(session: Any, message: Any) -> None:
    role = getattr(message, "role", None)
    role_value = role.value if hasattr(role, "value") else str(role or "")
    entry = getattr(message, "entry_type", None) or "message"
    content = getattr(message, "content", None) or ""
    if role_value == "assistant" and entry == "message" and not str(content).strip():
        return
    if entry == "compaction_summary":
        event_type = "compact"
    elif role_value in ("user", "assistant"):
        event_type = role_value
    else:
        event_type = "message"
    append_transcript_event(
        session,
        event_type,
        {
            "id": getattr(message, "id", None),
            "role": role_value,
            "entry_type": entry,
            "content": content,
            "attachments": _slim_attachments(getattr(message, "attachments", None)),
        },
    )


def append_sse_event(session: Any, event: dict[str, Any]) -> None:
    etype = event.get("type")
    if etype in ("tool_start", "tool_result"):
        content = event.get("summary") if etype == "tool_result" else event.get("content")
        if content is None:
            content = event.get("arguments") if etype == "tool_start" else event.get("content")
        append_transcript_event(
            session,
            "tool",
            {
                "phase": "start" if etype == "tool_start" else "result",
                "name": event.get("name"),
                "tool_call_id": event.get("tool_call_id"),
                "content": content,
                "full_ref": event.get("full_ref"),
            },
        )
        return
    if etype == "await_approval":
        append_transcript_event(
            session,
            "gate",
            {
                "gate": event.get("kind") or event.get("gate") or event.get("name"),
                "status": event.get("status") or "pending",
                "content": event.get("content") or event.get("message"),
            },
        )
        return
    # YOLO / apply-now skips await_approval; still record the gate settle.
    if etype in ("diff", "shell", "memory"):
        append_transcript_event(
            session,
            "gate",
            {
                "gate": etype,
                "status": event.get("status"),
                "path": event.get("path"),
                "command": event.get("command"),
                "memory_id": event.get("memory_id"),
            },
        )


def append_compact_event(
    session: Any,
    *,
    method: str | None = None,
    older_count: int | None = None,
    preview: str | None = None,
) -> None:
    append_transcript_event(
        session,
        "compact",
        {
            "method": method,
            "older_count": older_count,
            "preview": preview,
        },
    )


def read_transcript_events(session: Any) -> list[dict[str, Any]]:
    path = _resolved_transcript_path(session)
    if path is None or not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("session transcript skipped a corrupt line")
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def iter_transcript_lines(session: Any) -> Iterable[str]:
    path = _resolved_transcript_path(session)
    if path is None or not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()
