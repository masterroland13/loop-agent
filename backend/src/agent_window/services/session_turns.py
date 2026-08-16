"""Per-session turn lock + cooperative cancellation."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, List, Optional

BOOT_ID = str(uuid.uuid4())
STARTED_AT = time.time()

# session_id -> cancel Event for the active turn
_active: Dict[str, asyncio.Event] = {}


class SessionBusyError(Exception):
    """Raised when a session already has an in-flight agent turn."""


class TurnCancelled(Exception):
    """Raised when the active turn is cancelled (client abort / stop)."""


def try_begin_turn(session_id: str) -> asyncio.Event:
    if session_id in _active:
        raise SessionBusyError(session_id)
    cancel_event = asyncio.Event()
    _active[session_id] = cancel_event
    return cancel_event


def end_turn(session_id: str) -> None:
    _active.pop(session_id, None)


def cancel_turn(session_id: str) -> bool:
    """Signal cancel for an active turn and force-wake any pending approvals."""
    from agent_window.services.memory import cancel_pending_memories
    from agent_window.services.patches import cancel_pending_patches
    from agent_window.services.shell import cancel_pending_shells

    ev = _active.get(session_id)
    if ev:
        ev.set()
    # Always clear pending gates so a missed cancel_event cannot leave the loop hung.
    n = cancel_pending_patches() + cancel_pending_shells() + cancel_pending_memories()
    return ev is not None or n > 0


def is_session_busy(session_id: str) -> bool:
    return session_id in _active


def runtime_info() -> dict:
    return {
        "boot_id": BOOT_ID,
        "started_at": STARTED_AT,
        "active_sessions": list(_active.keys()),
    }


async def wait_or_cancel(
    decision_event: asyncio.Event,
    cancel_event: Optional[asyncio.Event],
    timeout: float,
) -> str:
    """
    Wait until decision_event, cancel_event, or timeout.
    Returns: 'done' | 'cancelled' | 'timeout'
    """
    if cancel_event is not None and cancel_event.is_set():
        return "cancelled"

    decision_task = asyncio.create_task(decision_event.wait())
    tasks: List[asyncio.Task] = [decision_task]
    cancel_task: Optional[asyncio.Task] = None
    if cancel_event is not None:
        cancel_task = asyncio.create_task(cancel_event.wait())
        tasks.append(cancel_task)

    try:
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if not done:
            return "timeout"
        if cancel_task is not None and cancel_task in done and cancel_event is not None and cancel_event.is_set():
            return "cancelled"
        return "done"
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


async def race_with_cancel(coro, cancel_event: Optional[asyncio.Event]):
    """
    Run coro until complete, or raise TurnCancelled if cancel_event fires first.
    """
    if cancel_event is None:
        return await coro
    if cancel_event.is_set():
        raise TurnCancelled()

    task = asyncio.create_task(coro)
    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        done, pending = await asyncio.wait(
            {task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done and cancel_event.is_set():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise TurnCancelled()
        cancel_task.cancel()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
        if not cancel_task.done():
            cancel_task.cancel()


async def watch_disconnect(request, cancel_event: asyncio.Event, interval: float = 0.4) -> None:
    """Set cancel_event when the client disconnects from an SSE stream."""
    try:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return
