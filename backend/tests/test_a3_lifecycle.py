"""A3 nested lifecycle events from run_agent_loop."""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest


def _patch_loop_basics(monkeypatch: pytest.MonkeyPatch, loop_mod: Any) -> None:
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 4},
    )

    class _Reg:
        def get_openai_tools(self):
            return [
                {
                    "type": "function",
                    "function": {"name": "list_dir", "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())


def test_text_only_lifecycle_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.core.event_sink import EventSink
    from agent_window.services.provider import provider

    sink_types: list[str] = []

    def capture(ev: dict) -> None:
        sink_types.append(str(ev.get("type")))

    sink = EventSink()
    sink.subscribe(capture)

    async def fake_chat(messages, tools=None, model=None):
        return {"content": "纯文本", "tool_calls": []}

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    _patch_loop_basics(monkeypatch, loop_mod)

    async def _run() -> List[dict]:
        events: List[dict] = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "hi"}],
            emit=sink,
            session_id="life-1",
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    types = [ev.get("type") for ev in events]

    assert types[0] == "agent_start"
    assert "turn_start" in types
    assert "token" in types
    assert "done" in types
    assert "turn_end" in types
    assert types[-1] == "agent_end"

    # order: agent_start → turn_start → token → done → turn_end → agent_end
    i_as = types.index("agent_start")
    i_ts = types.index("turn_start")
    i_tok = types.index("token")
    i_done = types.index("done")
    i_te = types.index("turn_end")
    i_ae = types.index("agent_end")
    assert i_as < i_ts < i_tok < i_done < i_te < i_ae

    # reverse: no duplicate agent_start / agent_end
    assert types.count("agent_start") == 1
    assert types.count("agent_end") == 1
    assert types.count("agent_start") != 2

    # Pipe A saw the same lifecycle
    assert sink_types[0] == "agent_start"
    assert sink_types[-1] == "agent_end"
    assert "token" in sink_types
    assert sink_types.count("agent_start") == 1


def test_event_from_sse_lifecycle_lightweight() -> None:
    from agent_window.agent.turn_event import event_from_sse

    start = event_from_sse({"type": "turn_start", "index": 2})
    assert start is not None
    assert start["type"] == "turn_start"
    assert start["index"] == 2
    assert "turn_start" in (start.get("summary") or "")

    end = event_from_sse({"type": "turn_end", "index": 2, "outcome": "done"})
    assert end is not None
    assert end["outcome"] == "done"

    steer = event_from_sse({"type": "steer_inject", "content": "hello"})
    assert steer is not None
    assert "hello" in (steer.get("summary") or "")

    # reverse: unknown still None
    assert event_from_sse({"type": "not_a_real_type"}) is None
