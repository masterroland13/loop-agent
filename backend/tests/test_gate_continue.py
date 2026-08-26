"""Gate policy: Reject ends; timeout/failed soft-continue once then end."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import pytest


def test_gate_status_sets() -> None:
    from agent_window.agent.loop import (
        _GATE_CONTINUE_STATUSES,
        _GATE_END_STATUSES,
        _GATE_RETRY_STATUSES,
        _GATE_STOP_STATUSES,
        _GATE_SUCCESS_STATUSES,
    )

    assert "rejected" in _GATE_END_STATUSES
    assert "partial" in _GATE_END_STATUSES
    assert "rejected" not in _GATE_RETRY_STATUSES
    assert _GATE_CONTINUE_STATUSES == _GATE_RETRY_STATUSES
    assert "failed" in _GATE_RETRY_STATUSES
    assert "timeout" in _GATE_RETRY_STATUSES
    assert "cancelled" in _GATE_STOP_STATUSES
    assert "applied" in _GATE_SUCCESS_STATUSES
    assert "rejected" not in _GATE_SUCCESS_STATUSES


def test_enrich_only_for_retry_statuses() -> None:
    from agent_window.agent.loop import _enrich_gate_result_for_continue

    out = _enrich_gate_result_for_continue(
        "{}",
        "shell",
        {"status": "failed", "command": "python x.py", "error": "not found"},
        goal="跑通脚本",
    )
    data = json.loads(out)
    assert data["loop_continue"] is True
    assert "唯一一次" in data["continue_hint"] or "自动续环" in data["continue_hint"]
    assert "跑通脚本" in data["continue_hint"]
    assert "python x.py" in data["continue_hint"]
    assert "不要结束本轮：请换手段" not in data["continue_hint"]


def test_after_retry_message_mentions_retry() -> None:
    from agent_window.agent.loop import _gate_user_message

    msg = _gate_user_message(
        "shell",
        {"status": "failed", "command": "pwd", "error": "boom"},
        after_retry=True,
    )
    assert "重试仍" in msg or "自动换手段重试" in msg
    assert "pwd" in msg
    assert "已拒绝" not in msg


def _patch_loop_basics(monkeypatch: pytest.MonkeyPatch, loop_mod: Any, tool_name: str) -> None:
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8},
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


def test_reject_ends_with_template(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    calls: List[Any] = []

    async def fake_chat(messages, tools=None, model=None):
        calls.append(1)
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_r1",
                    "name": "propose_edit",
                    "arguments": {"path": "x.py", "content": "hi"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {"status": "rejected", "patch_id": "p1", "path": "x.py"},
            ensure_ascii=False,
        )

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    _patch_loop_basics(monkeypatch, loop_mod, "propose_edit")

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "改 x.py"}],
            goal="修好 x.py",
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert len(calls) == 1  # no second LLM beat
    tokens = [e.get("content", "") for e in events if e.get("type") == "token"]
    assert any("已拒绝修改" in t for t in tokens)
    assert any(e.get("type") == "done" for e in events)
    assert not any(e.get("loop_continue") for e in events)


def test_failed_continues_once_then_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    calls: List[Dict[str, Any]] = []
    fail_count = {"n": 0}

    async def fake_chat(messages, tools=None, model=None):
        calls.append({"n": len(calls) + 1, "messages": messages})
        if len(calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_f1",
                        "name": "propose_shell",
                        "arguments": {"argv": ["ls"]},
                    }
                ],
            }
        # After first continue_hint, model tries again
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs
        body = json.loads(tool_msgs[-1]["content"])
        assert body.get("loop_continue") is True
        assert "continue_hint" in body
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_f2",
                    "name": "propose_shell",
                    "arguments": {"argv": ["pwd"]},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        fail_count["n"] += 1
        return json.dumps(
            {
                "status": "failed",
                "shell_id": f"s{fail_count['n']}",
                "command": "ls" if fail_count["n"] == 1 else "pwd",
                "error": "boom",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    _patch_loop_basics(monkeypatch, loop_mod, "propose_shell")

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop([{"role": "user", "content": "列目录"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert len(calls) == 2
    assert fail_count["n"] == 2
    assert any(e.get("loop_continue") for e in events)
    tokens = [e.get("content", "") for e in events if e.get("type") == "token"]
    assert any("重试仍" in t or "自动换手段重试" in t for t in tokens)
    assert any(e.get("type") == "done" for e in events)
    # Must not keep calling LLM forever
    assert len(calls) < 3


def test_loop_stops_on_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_c1",
                    "name": "propose_shell",
                    "arguments": {"argv": ["pwd"]},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {"status": "cancelled", "shell_id": "s1", "command": "pwd"},
            ensure_ascii=False,
        )

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    _patch_loop_basics(monkeypatch, loop_mod, "propose_shell")

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop([{"role": "user", "content": "跑 pwd"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert any(e.get("code") == "TURN_CANCELLED" for e in events)
    assert not any(e.get("type") == "done" for e in events)
