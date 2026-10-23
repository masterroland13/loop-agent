"""Preset before_tool_call policy — YOLO / Trusted / Strict."""

from __future__ import annotations

import asyncio
import json
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_window.core.loop_config import LoopConfig, LoopPreset
from agent_window.core.preset_hooks import (
    decide_gate_preset,
    memory_will_auto_apply,
    resolve_gate_decision,
)
from agent_window.tools.memory_tools import AWAIT_MEMORY_KEY


def test_decide_gate_preset_matrix() -> None:
    yolo = decide_gate_preset(LoopPreset.YOLO)
    assert yolo.auto_apply is True
    assert yolo.force_confirm_memory is False
    assert yolo.action == "allow"

    trusted = decide_gate_preset("trusted")
    assert trusted.auto_apply is False
    assert trusted.force_confirm_memory is False
    assert trusted.action == "wait"

    strict = decide_gate_preset(LoopPreset.STRICT)
    assert strict.auto_apply is False
    assert strict.force_confirm_memory is True
    assert strict.action == "wait"
    assert strict.action != "allow"


def test_memory_will_auto_apply_strict_ignores_confirm_off() -> None:
    strict = decide_gate_preset(LoopPreset.STRICT)
    assert memory_will_auto_apply(strict, confirm_memory=False) is False
    assert memory_will_auto_apply(strict, confirm_memory=True) is False

    trusted = decide_gate_preset(LoopPreset.TRUSTED)
    assert memory_will_auto_apply(trusted, confirm_memory=False) is True
    assert memory_will_auto_apply(trusted, confirm_memory=True) is False

    yolo = decide_gate_preset(LoopPreset.YOLO)
    assert memory_will_auto_apply(yolo, confirm_memory=True) is True


def test_with_preset_installs_before_tool_call() -> None:
    cfg = LoopConfig.default().with_preset("strict")
    assert cfg.before_tool_call is not None
    decision = asyncio.run(resolve_gate_decision(cfg))
    assert decision.force_confirm_memory is True
    assert decision.auto_apply is False


def test_strict_memory_awaits_even_when_confirm_memory_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.memory import MemoryStatus
    from agent_window.services.provider import provider

    settings = {
        "disabled_tools": [],
        "max_tool_iters": 8,
        "confirm_memory": False,
    }
    monkeypatch.setattr(loop_mod, "load_agent_settings", lambda: settings)
    monkeypatch.setattr(gate_hooks, "load_agent_settings", lambda: settings)

    class _Reg:
        def get_openai_tools(self):
            return [
                {
                    "type": "function",
                    "function": {"name": "propose_memory", "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_m1",
                    "name": "propose_memory",
                    "arguments": {"content": "remember this"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {
                AWAIT_MEMORY_KEY: True,
                "memory": {
                    "id": "mem1",
                    "mode": "append",
                    "preview": "remember this",
                    "content": "remember this",
                },
            },
            ensure_ascii=False,
        )

    mem = MagicMock()
    mem.id = "mem1"
    mem.mode = "append"
    mem.preview = "remember this"
    mem.content = "remember this"
    mem.target = "user"
    mem.status = MemoryStatus.REJECTED
    mem.error = None

    decide = AsyncMock(side_effect=AssertionError("Strict must await memory"))
    wait = AsyncMock(return_value=mem)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_memory", decide)
    monkeypatch.setattr(gate_hooks, "wait_for_memory_decision", wait)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "记住这个"}],
            config=LoopConfig.default().with_preset("strict"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert any(e.get("type") == "await_approval" and e.get("kind") == "memory" for e in events)
    decide.assert_not_awaited()
    wait.assert_awaited()


def test_trusted_memory_auto_when_confirm_memory_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.provider import provider
    from agent_window.services.memory import MemoryStatus

    settings = {
        "disabled_tools": [],
        "max_tool_iters": 8,
        "confirm_memory": False,
    }
    monkeypatch.setattr(loop_mod, "load_agent_settings", lambda: settings)
    monkeypatch.setattr(gate_hooks, "load_agent_settings", lambda: settings)

    class _Reg:
        def get_openai_tools(self):
            return [
                {
                    "type": "function",
                    "function": {"name": "propose_memory", "parameters": {"type": "object"}},
                }
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())

    calls: List[Any] = []

    async def fake_chat(messages, tools=None, model=None):
        calls.append(1)
        if len(calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_m2",
                        "name": "propose_memory",
                        "arguments": {"content": "note"},
                    }
                ],
            }
        return {"content": "已记住。", "tool_calls": []}

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {
                AWAIT_MEMORY_KEY: True,
                "memory": {
                    "id": "mem2",
                    "mode": "append",
                    "preview": "note",
                    "content": "note",
                },
            },
            ensure_ascii=False,
        )

    mem = MagicMock()
    mem.id = "mem2"
    mem.mode = "append"
    mem.preview = "note"
    mem.content = "note"
    mem.target = "user"
    mem.status = MemoryStatus.APPLIED
    mem.error = None

    decide = AsyncMock(return_value=mem)
    wait = AsyncMock(side_effect=AssertionError("Trusted+confirm_off must auto"))

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_memory", decide)
    monkeypatch.setattr(gate_hooks, "wait_for_memory_decision", wait)

    async def _run():
        events = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "记住"}],
            config=LoopConfig.default().with_preset("trusted"),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert not any(e.get("type") == "await_approval" for e in events)
    decide.assert_awaited_once_with("mem2", "apply")
    wait.assert_not_awaited()
