"""Steering queue + loop inject at turn boundary (A3)."""

from __future__ import annotations

import asyncio
import json
from typing import List

import pytest

from agent_window.core.steering import (
    clear_steering,
    drain_steering,
    format_steering_content,
    peek_steering_count,
    push_steering,
)


def test_format_steering_content_idempotent() -> None:
    once = format_steering_content("改用 pytest -q")
    assert once.startswith("【插队指引】")
    assert "改用 pytest -q" in once
    twice = format_steering_content(once)
    assert twice == once
    assert format_steering_content("  ") == ""
    assert format_steering_content("") == ""


def test_push_drain_clear_and_reject_empty() -> None:
    sid = "steer-test-q1"
    clear_steering(sid)

    bad = push_steering(sid, "   ")
    assert bad["ok"] is False
    assert bad["queued"] is False
    assert peek_steering_count(sid) == 0
    # reverse
    assert drain_steering(sid) == []

    ok = push_steering(sid, "  mid-run hint  ")
    assert ok["ok"] is True
    assert ok["queued"] is True
    assert peek_steering_count(sid) == 1

    msgs = drain_steering(sid)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert "mid-run hint" in msgs[0]["content"]
    assert "【插队指引】" in msgs[0]["content"]
    assert "不结束当前任务" in msgs[0]["content"]
    assert peek_steering_count(sid) == 0
    # reverse: drained once
    assert drain_steering(sid) == []

    push_steering(sid, "again")
    assert peek_steering_count(sid) == 1
    clear_steering(sid)
    assert peek_steering_count(sid) == 0
    assert drain_steering(sid) == []


def test_loop_steering_injects_before_second_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    sid = "steer-loop-sess"
    clear_steering(sid)

    chat_calls = 0
    second_msgs: list[dict] = []

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            push_steering(sid, "please also check README")
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": '{"path":"."}'},
                ],
            }
        second_msgs.extend(messages)
        return {"content": "done with steer", "tool_calls": []}

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"entries": ["a"]}, ensure_ascii=False)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_tool)
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

    async def _run() -> List[dict]:
        events: List[dict] = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "list"}],
            session_id=sid,
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    assert chat_calls == 2
    assert any(ev.get("type") == "steer_inject" and "README" in (ev.get("content") or "") for ev in events)
    assert any(
        m.get("role") == "user"
        and "README" in (m.get("content") or "")
        and "【插队指引】" in (m.get("content") or "")
        for m in second_msgs
    )
    # Loop must continue after steer (second LLM call happened); not cancel-only.
    assert chat_calls >= 2
    assert not any(ev.get("type") == "error" and ev.get("code") == "TURN_CANCELLED" for ev in events)
    # reverse: steer not before first turn (first chat had no inject yet)
    steer_idxs = [i for i, ev in enumerate(events) if ev.get("type") == "steer_inject"]
    turn0 = next(i for i, ev in enumerate(events) if ev.get("type") == "turn_start" and ev.get("index") == 0)
    turn1 = next(i for i, ev in enumerate(events) if ev.get("type") == "turn_start" and ev.get("index") == 1)
    assert len(steer_idxs) == 1
    assert turn0 < steer_idxs[0] < turn1
    assert peek_steering_count(sid) == 0
