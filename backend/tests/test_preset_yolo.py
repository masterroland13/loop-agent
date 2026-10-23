"""A1c: YOLO auto-applies write gates; Trusted keeps await_approval."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_window.core.loop_config import LoopConfig, LoopPreset
from agent_window.services.patches import PatchStatus
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY


def _patch_basics(monkeypatch: pytest.MonkeyPatch, loop_mod: Any) -> None:
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "confirm_memory": True},
    )

    class _Reg:
        def get_openai_tools(self):
            return [
                {
                    "type": "function",
                    "function": {"name": "propose_edit", "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())


def _await_payload(patch_id: str = "p_yolo") -> str:
    return json.dumps(
        {
            AWAIT_PATCH_KEY: True,
            "patch": {
                "id": patch_id,
                "path": "x.py",
                "unified_diff": "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+hi\n",
                "is_new_file": True,
                "is_delete": False,
                "status": "pending",
            },
            "message": "waiting",
        },
        ensure_ascii=False,
    )


def _applied_patch(patch_id: str = "p_yolo") -> MagicMock:
    p = MagicMock()
    p.id = patch_id
    p.path = "x.py"
    p.unified_diff = "diff"
    p.is_new_file = True
    p.is_delete = False
    p.status = PatchStatus.APPLIED
    p.error = None
    p.applied_hunks = None
    return p


def _rejected_patch(patch_id: str = "p_trusted") -> MagicMock:
    p = MagicMock()
    p.id = patch_id
    p.path = "x.py"
    p.unified_diff = "diff"
    p.is_new_file = True
    p.is_delete = False
    p.status = PatchStatus.REJECTED
    p.error = None
    p.applied_hunks = None
    return p


def test_yolo_propose_edit_skips_await_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """YOLO: no pending/await_approval flash; applied; chat continues."""
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    calls: List[Any] = []

    async def fake_chat(messages, tools=None, model=None):
        calls.append(1)
        if len(calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_y1",
                        "name": "propose_edit",
                        "arguments": {"path": "x.py", "content": "hi"},
                    }
                ],
            }
        return {"content": "已写入 x.py。", "tool_calls": []}

    async def fake_handle(name: str, arguments: Any) -> str:
        assert name == "propose_edit"
        return _await_payload("p_yolo")

    decide = AsyncMock(return_value=_applied_patch("p_yolo"))
    wait = AsyncMock(side_effect=AssertionError("YOLO must not wait for approval"))

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    import agent_window.agent.gate_hooks as gate_hooks

    monkeypatch.setattr(gate_hooks, "decide_patch", decide)
    monkeypatch.setattr(gate_hooks, "wait_for_decision", wait)
    _patch_basics(monkeypatch, loop_mod)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "写 x.py"}],
            config=LoopConfig.default().with_preset("yolo"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert not any(e.get("type") == "await_approval" for e in events)
    diffs = [e for e in events if e.get("type") == "diff"]
    assert not any(e.get("status") == "pending" for e in diffs)
    assert any(e.get("status") == "applied" for e in diffs)
    assert not any(e.get("status") == "rejected" for e in diffs)
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results
    body = json.loads(tool_results[0]["content"])
    assert body.get("status") == "applied"
    assert body.get("status") != "rejected"
    decide.assert_awaited_once_with("p_yolo", "apply")
    wait.assert_not_awaited()
    assert len(calls) == 2  # continued after apply
    assert any(e.get("type") == "done" for e in events)
    assert LoopConfig.default().preset == LoopPreset.YOLO


def test_trusted_propose_edit_yields_await_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trusted: still emits await_approval and waits (reject ends turn)."""
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    calls: List[Any] = []

    async def fake_chat(messages, tools=None, model=None):
        calls.append(1)
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_t1",
                    "name": "propose_edit",
                    "arguments": {"path": "x.py", "content": "hi"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return _await_payload("p_trusted")

    decide = AsyncMock(side_effect=AssertionError("Trusted must wait, not auto decide"))
    wait = AsyncMock(return_value=_rejected_patch("p_trusted"))

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    import agent_window.agent.gate_hooks as gate_hooks

    monkeypatch.setattr(gate_hooks, "decide_patch", decide)
    monkeypatch.setattr(gate_hooks, "wait_for_decision", wait)
    _patch_basics(monkeypatch, loop_mod)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "写 x.py"}],
            config=LoopConfig.default().with_preset("trusted"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert any(
        e.get("type") == "await_approval" and e.get("kind") == "patch" for e in events
    )
    assert not any(
        e.get("type") == "await_approval" and e.get("kind") == "shell" for e in events
    )
    wait.assert_awaited()
    decide.assert_not_awaited()
    assert len(calls) == 1  # reject ends; no second LLM beat
    tokens = [e.get("content", "") for e in events if e.get("type") == "token"]
    assert any("已拒绝修改" in t for t in tokens)
    assert any(e.get("type") == "done" for e in events)


def test_strict_same_as_trusted_for_a1c(monkeypatch: pytest.MonkeyPatch) -> None:
    """A1c: Strict treated like Trusted (still awaits approval)."""
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_s1",
                    "name": "propose_edit",
                    "arguments": {"path": "x.py", "content": "hi"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return _await_payload("p_strict")

    wait = AsyncMock(return_value=_rejected_patch("p_strict"))
    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    import agent_window.agent.gate_hooks as gate_hooks

    monkeypatch.setattr(gate_hooks, "wait_for_decision", wait)
    monkeypatch.setattr(
        gate_hooks,
        "decide_patch",
        AsyncMock(side_effect=AssertionError("strict must not auto-apply")),
    )
    _patch_basics(monkeypatch, loop_mod)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "写"}],
            config=LoopConfig.default().with_preset("strict"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert any(e.get("type") == "await_approval" for e in events)
    assert not any(
        e.get("type") == "diff" and e.get("status") == "applied" for e in events
    )


def test_invalid_preset_falls_back_to_yolo() -> None:
    cfg = LoopConfig.default().with_preset("nope")
    assert cfg.preset == LoopPreset.YOLO
    assert cfg.preset != LoopPreset.TRUSTED
    cfg2 = LoopConfig.from_settings(goal_mode=True, preset="trusted")
    assert cfg2.goal_mode is True
    assert cfg2.preset == LoopPreset.TRUSTED
