"""Gate 深拆 Step 3: prepare (propose) → before settle → execute skipped for gate tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_window.core.loop_config import LoopConfig
from agent_window.services.patches import PatchStatus
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY


def _await_payload(patch_id: str = "p_s3") -> str:
    return json.dumps(
        {
            AWAIT_PATCH_KEY: True,
            "patch": {
                "id": patch_id,
                "path": "x.py",
                "unified_diff": "diff",
                "is_new_file": True,
                "is_delete": False,
            },
        },
        ensure_ascii=False,
    )


def test_gate_prepare_then_settle_yolo_calls_handler_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propose_* runs once in prepare; settle auto-applies; no second execute."""
    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.provider import provider

    handler_calls: List[str] = []
    order: List[str] = []

    async def fake_chat(messages, tools=None, model=None):
        if not getattr(fake_chat, "n", 0):
            fake_chat.n = 1  # type: ignore[attr-defined]
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_s3",
                        "name": "propose_edit",
                        "arguments": {"path": "x.py", "content": "hi"},
                    }
                ],
            }
        return {"content": "ok", "tool_calls": []}

    async def fake_handle(name: str, arguments: Any) -> str:
        handler_calls.append(name)
        order.append("prepare")
        return _await_payload("p_s3")

    applied = MagicMock()
    applied.path = "x.py"
    applied.unified_diff = "diff"
    applied.is_new_file = True
    applied.is_delete = False
    applied.status = PatchStatus.APPLIED
    applied.error = None
    applied.applied_hunks = None

    async def fake_decide(patch_id: str, decision: str):
        order.append("settle")
        assert decision == "apply"
        assert "prepare" in order
        return applied

    wait = AsyncMock(side_effect=AssertionError("YOLO must not wait"))

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_patch", fake_decide)
    monkeypatch.setattr(gate_hooks, "wait_for_decision", wait)
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

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "写"}],
            config=LoopConfig.default().with_preset("yolo"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert handler_calls == ["propose_edit"]
    assert handler_calls != ["propose_edit", "propose_edit"]
    assert order == ["prepare", "settle"]
    assert not any(e.get("type") == "await_approval" for e in events)
    assert any(e.get("type") == "diff" and e.get("status") == "applied" for e in events)
    wait.assert_not_awaited()


def test_block_after_prepare_abandons_without_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare creates pending; block abandons (reject); decide apply never runs."""
    from dataclasses import replace

    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.provider import provider

    handler_calls: List[str] = []
    decide_calls: List[tuple[str, str]] = []

    async def blocker(**kwargs: Any) -> dict:
        return {"action": "block", "reason": "policy denies after prepare"}

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_blk",
                    "name": "propose_edit",
                    "arguments": {"path": "x.py", "content": "hi"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        handler_calls.append(name)
        return _await_payload("p_blk")

    rejected = MagicMock()
    rejected.path = "x.py"
    rejected.unified_diff = "diff"
    rejected.is_new_file = True
    rejected.is_delete = False
    rejected.status = PatchStatus.REJECTED
    rejected.error = None
    rejected.applied_hunks = None

    async def fake_decide(patch_id: str, decision: str):
        decide_calls.append((patch_id, decision))
        if decision == "apply":
            raise AssertionError("block must not apply")
        return rejected

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_patch", fake_decide)
    monkeypatch.setattr(gate_hooks, "wait_for_decision", AsyncMock())
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
    cfg = replace(LoopConfig.default().with_preset("yolo"), before_tool_call=blocker)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "写"}],
            config=cfg,
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert handler_calls == ["propose_edit"]  # prepare once
    assert decide_calls == [("p_blk", "reject")]  # abandon only
    assert ("p_blk", "apply") not in decide_calls
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results
    body = json.loads(tool_results[0]["content"])
    assert body.get("blocked") is True
    assert body.get("status") == "blocked"
    assert body.get("status") != "applied"
    assert not any(e.get("type") == "await_approval" for e in events)


def test_non_gate_tool_still_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        if not getattr(fake_chat, "n", 0):
            fake_chat.n = 1  # type: ignore[attr-defined]
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_r",
                        "name": "read_file",
                        "arguments": {"path": "a.txt"},
                    }
                ],
            }
        return {"content": "done", "tool_calls": []}

    async def fake_handle(name: str, arguments: Any) -> str:
        assert name == "read_file"
        return json.dumps({"content": "hello"}, ensure_ascii=False)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
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
                    "function": {"name": "read_file", "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "读"}],
            config=LoopConfig.default().with_preset("yolo"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results
    assert "hello" in tool_results[0]["content"]
    assert not any(e.get("type") == "await_approval" for e in events)
