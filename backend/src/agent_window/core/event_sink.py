"""Pipe A: fire-and-forget event observers (charter §3.2 / M07 / A3)."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Callable

logger = logging.getLogger(__name__)

LIFECYCLE_TYPES = frozenset({"agent_start", "agent_end", "turn_start", "turn_end"})

Subscriber = Callable[[dict], Any]


class EventSink:
    """Pipe A: fire-and-forget observers. Errors in subscribers must not break the loop."""

    def __init__(self) -> None:
        self._subs: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        """Register ``fn``; returns an unsubscribe callable."""
        self._subs.append(fn)

        def unsubscribe() -> None:
            try:
                self._subs.remove(fn)
            except ValueError:
                pass

        return unsubscribe

    def emit(self, event: dict) -> None:
        """Copy ``event`` and call each subscriber; log and swallow subscriber errors."""
        if not self._subs:
            return
        snapshot = deepcopy(event)
        for fn in list(self._subs):
            try:
                fn(snapshot)
            except Exception:
                logger.exception("EventSink subscriber failed type=%s", snapshot.get("type"))
