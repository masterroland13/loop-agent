"""Final reply appends an honesty note when finish_reason is length."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agent_window.agent.loop import _MAX_TOKENS_TRUNCATED_NOTE, run_agent_loop
from agent_window.core.loop_config import LoopConfig
from agent_window.services.provider import provider


def test_loop_appends_note_when_finish_reason_length(monkeypatch):
    async def fake_chat(
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "content": "若 cut <= 0 且 `len(rest) <=",
            "tool_calls": [],
            "finish_reason": "length",
            "tools_fallback": False,
            "reasoning_content": "",
            "reasoning_source": "none",
            "reasoning_duration_ms": None,
        }

    monkeypatch.setattr(provider, "chat_complete", fake_chat)

    async def _collect():
        out = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "hi"}],
            config=LoopConfig.default(),
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    tokens = [e for e in events if e.get("type") == "token"]
    assert len(tokens) == 1
    body = tokens[0]["content"]
    assert "若 cut <= 0" in body
    assert _MAX_TOKENS_TRUNCATED_NOTE in body
    assert "压缩无关" in body


def test_loop_no_length_note_on_normal_stop(monkeypatch):
    async def fake_chat(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "content": "完整短答",
            "tool_calls": [],
            "finish_reason": "stop",
            "tools_fallback": False,
            "reasoning_content": "",
            "reasoning_source": "none",
            "reasoning_duration_ms": None,
        }

    monkeypatch.setattr(provider, "chat_complete", fake_chat)

    async def _collect():
        out = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "hi"}],
            config=LoopConfig.default(),
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    tokens = [e for e in events if e.get("type") == "token"]
    assert len(tokens) == 1
    assert tokens[0]["content"] == "完整短答"
    assert _MAX_TOKENS_TRUNCATED_NOTE not in tokens[0]["content"]
