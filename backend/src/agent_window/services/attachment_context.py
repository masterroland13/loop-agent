"""ContextVar for session-scoped attachment tools."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "attachment_session_id", default=None
)


@contextmanager
def use_attachment_session(session_id: str) -> Iterator[None]:
    token = _current_session_id.set(session_id)
    try:
        yield
    finally:
        _current_session_id.reset(token)


def get_attachment_session_id() -> str | None:
    return _current_session_id.get()
