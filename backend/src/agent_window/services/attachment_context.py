"""ContextVar for session-scoped tools (attachments + gate proposals)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "attachment_session_id", default=None
)


@contextmanager
def use_attachment_session(session_id: str) -> Iterator[None]:
    """Bind the active turn's session_id for tools that create pending gates."""
    token = _current_session_id.set(session_id)
    try:
        yield
    finally:
        _current_session_id.reset(token)


def get_attachment_session_id() -> str | None:
    return _current_session_id.get()


def get_turn_session_id() -> str | None:
    """Session id for the in-flight agent turn (same ContextVar as attachments)."""
    return _current_session_id.get()
