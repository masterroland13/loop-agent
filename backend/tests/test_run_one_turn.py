"""Characterisation of _run_one_turn via public run_agent_loop (A0 strangler)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, List

import pytest


def _patch_loop_basics(monkeypatch: pytest.MonkeyPatch, loop_mod: Any, tool_name: str = "list_dir") -> None:
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
                    "function": {"name": tool_name, "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())


def test_text_only_reply_one_chat_token_done_no_tool_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    chat_calls = 0

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        return {"content": "你好，这是纯文本回复。", "tool_calls": []}

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(
        loop_mod,
        "handle_function_call",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("tool should not run")),
    )
    _patch_loop_basics(monkeypatch, loop_mod)

    async def _run() -> List[dict]:
        events: List[dict] = []
        async for ev in loop_mod.run_agent_loop([{"role": "user", "content": "hi"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    assert chat_calls == 1
    assert any(ev.get("type") == "token" for ev in events)
    assert any(ev.get("type") == "done" for ev in events)
    # reverse
    assert not any(ev.get("type") == "tool_start" for ev in events)
    assert chat_calls != 2


def test_tool_then_text_continue_two_chats(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    chat_calls = 0

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": '{"path":"."}'},
                ],
            }
        return {"content": "目录已列出。", "tool_calls": []}

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"entries": ["a"]}, ensure_ascii=False)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_tool)
    _patch_loop_basics(monkeypatch, loop_mod)

    async def _run() -> List[dict]:
        events: List[dict] = []
        async for ev in loop_mod.run_agent_loop([{"role": "user", "content": "列出目录"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    assert chat_calls == 2
    assert any(ev.get("type") == "tool_start" and ev.get("name") == "list_dir" for ev in events)
    assert any(ev.get("type") == "token" for ev in events)
    assert any(ev.get("type") == "done" for ev in events)
    # reverse: not a single-shot text path
    assert chat_calls != 1
    assert not all(ev.get("type") != "tool_start" for ev in events)


def test_run_agent_loop_accepts_config_same_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    chat_calls = 0

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        return {"content": "with config ok", "tool_calls": []}

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    _patch_loop_basics(monkeypatch, loop_mod)

    async def _run() -> List[dict]:
        events: List[dict] = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "hi"}],
            config=LoopConfig.default(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    assert chat_calls == 1
    assert any(ev.get("type") == "token" and "with config ok" in (ev.get("content") or "") for ev in events)
    assert any(ev.get("type") == "done" for ev in events)
    # reverse
    assert not any(ev.get("type") == "tool_start" for ev in events)
    assert not any(ev.get("type") == "error" for ev in events)
