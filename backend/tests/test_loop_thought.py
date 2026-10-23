"""Loop emits thought SSE when provider returns reasoning_content."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agent_window.agent.loop import run_agent_loop
from agent_window.core.loop_config import LoopConfig
from agent_window.services.provider import provider


def test_loop_yields_thought_before_token(monkeypatch):
    async def fake_chat(
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "content": "hello",
            "tool_calls": [],
            "finish_reason": "stop",
            "tools_fallback": False,
            "reasoning_content": "I should greet the user.",
            "reasoning_source": "reasoning_content",
            "reasoning_duration_ms": 1500,
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
    thoughts = [e for e in events if e.get("type") == "thought"]
    assert len(thoughts) == 1
    assert thoughts[0]["text"] == "I should greet the user."
    assert thoughts[0]["phase"] == "end"
    assert thoughts[0]["duration_ms"] == 1500
    types = [e.get("type") for e in events]
    assert "token" in types
    assert types.index("thought") < types.index("token")


def test_loop_no_thought_when_provider_silent(monkeypatch):
    async def fake_chat(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "content": "plain reply",
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
    assert not any(e.get("type") == "thought" for e in events)
    assert any(e.get("type") == "token" and e.get("content") == "plain reply" for e in events)
