"""Process-local steering queues keyed by session_id (A3).

Mid-run user text is queued and drained at the next turn boundary as
OpenAI-style user messages. Steering must **not** cancel the agent run —
it redirects the continuing loop (charter M03 getSteeringMessages).
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

from agent_window.core.loop_config import LoopConfig

_lock = threading.Lock()
_queues: dict[str, list[str]] = {}

# Framed so the model continues tool work instead of treating steer as a new
# one-shot question and soft-stopping with a text-only reply.
_STEER_WRAPPER = (
    "【插队指引】以下为用户中途补充，请在**不结束当前任务**的前提下遵从；"
    "继续调用工具推进原目标，不要仅用文字回复就收工。\n\n"
)


def format_steering_content(raw: str) -> str:
    """Wrap raw steer text for injection into the working transcript."""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("【插队指引】"):
        return text
    return f"{_STEER_WRAPPER}{text}"


def push_steering(session_id: str, content: str) -> dict[str, Any]:
    """Enqueue stripped user text. Blank content is rejected (ok=False)."""
    sid = (session_id or "").strip()
    text = (content or "").strip()
    if not sid or not text:
        return {"ok": False, "queued": False, "session_id": sid or session_id}
    with _lock:
        q = _queues.setdefault(sid, [])
        q.append(text)
        count = len(q)
    return {"ok": True, "queued": True, "session_id": sid, "count": count}


def drain_steering(session_id: str) -> list[dict[str, str]]:
    """Return and clear queued messages as ``{"role":"user","content":...}``.

    Content is framed with ``format_steering_content`` so inject keeps the loop alive.
    """
    sid = (session_id or "").strip()
    if not sid:
        return []
    with _lock:
        items = _queues.pop(sid, [])
    out: list[dict[str, str]] = []
    for c in items:
        framed = format_steering_content(c)
        if framed:
            out.append({"role": "user", "content": framed})
    return out


def peek_steering_count(session_id: str) -> int:
    sid = (session_id or "").strip()
    if not sid:
        return 0
    with _lock:
        return len(_queues.get(sid, []))


def clear_steering(session_id: str) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    with _lock:
        _queues.pop(sid, None)


def bind_steering(config: LoopConfig, session_id: str) -> LoopConfig:
    """Wire ``get_steering_messages`` to drain this session's queue."""

    async def _get() -> list[dict[str, str]]:
        return drain_steering(session_id)

    return replace(config, get_steering_messages=_get)
