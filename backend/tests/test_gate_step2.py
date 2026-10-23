"""Gate 深拆 Step 2: before_tool_call action allow|wait|block + pipeline await."""

from __future__ import annotations

import asyncio
import json
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_window.core.loop_config import LoopConfig, LoopPreset
from agent_window.core.preset_hooks import (
    GatePresetDecision,
    decide_gate_preset,
    normalize_gate_decision,
    resolve_gate_decision,
)
from agent_window.services.patches import PatchStatus
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY


def test_decide_gate_preset_actions() -> None:
    assert decide_gate_preset(LoopPreset.YOLO).action == "allow"
    assert decide_gate_preset(LoopPreset.TRUSTED).action == "wait"
    assert decide_gate_preset(LoopPreset.STRICT).action == "wait"
    assert decide_gate_preset(LoopPreset.YOLO).action != "wait"
    assert decide_gate_preset(LoopPreset.STRICT).force_confirm_memory is True


def test_normalize_gate_decision_block_and_allow_dict() -> None:
    blocked = normalize_gate_decision({"action": "block", "reason": "nope"})
    assert blocked.action == "block"
    assert blocked.auto_apply is False
    assert blocked.reason == "nope"
    assert blocked.action != "allow"

    allowed = normalize_gate_decision({"action": "allow"})
    assert allowed.action == "allow"
    assert allowed.auto_apply is True
    assert allowed.action != "wait"

    waited = normalize_gate_decision({"action": "wait", "force_confirm_memory": True})
    assert waited.action == "wait"
    assert waited.force_confirm_memory is True
    assert waited.auto_apply is False


def test_before_tool_call_block_skips_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 3: prepare may run; block abandons pending; settle must not apply."""
    from dataclasses import replace

    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.patches import PatchStatus
    from agent_window.services.provider import provider
    from agent_window.tools.edit_tools import AWAIT_PATCH_KEY

    decide_calls: List[tuple[str, str]] = []

    async def blocker(**kwargs: Any) -> dict:
        return {"action": "block", "reason": "policy denies propose_edit"}

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc_block",
                    "name": "propose_edit",
                    "arguments": {"path": "x.py", "content": "hi"},
                }
            ],
        }

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {
                AWAIT_PATCH_KEY: True,
                "patch": {
                    "id": "p_block",
                    "path": "x.py",
                    "unified_diff": "diff",
                    "is_new_file": True,
                    "is_delete": False,
                },
            },
            ensure_ascii=False,
        )

    rejected = MagicMock()
    rejected.status = PatchStatus.REJECTED
    rejected.path = "x.py"
    rejected.unified_diff = "diff"
    rejected.is_new_file = True
    rejected.is_delete = False
    rejected.error = None
    rejected.applied_hunks = None

    async def fake_decide(patch_id: str, decision: str):
        decide_calls.append((patch_id, decision))
        if decision == "apply":
            raise AssertionError("execute/settle must not apply when blocked")
        return rejected

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_patch", fake_decide)
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
    assert ("p_block", "apply") not in decide_calls
    assert decide_calls == [("p_block", "reject")]
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results
    body = json.loads(tool_results[0]["content"])
    assert body.get("status") == "blocked"
    assert "policy denies" in (body.get("error") or "")
    assert body.get("blocked") is True
    assert not any(e.get("type") == "await_approval" for e in events)


def test_pipeline_await_gate_yolo_via_before_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Await resolution runs inside tool_pipeline under before_tool_call allow."""
    from agent_window.agent import loop as loop_mod
    import agent_window.agent.gate_hooks as gate_hooks
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        if not getattr(fake_chat, "n", 0):
            fake_chat.n = 1  # type: ignore[attr-defined]
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_p2",
                        "name": "propose_edit",
                        "arguments": {"path": "x.py", "content": "hi"},
                    }
                ],
            }
        return {"content": "ok", "tool_calls": []}

    async def fake_handle(name: str, arguments: Any) -> str:
        return json.dumps(
            {
                AWAIT_PATCH_KEY: True,
                "patch": {
                    "id": "p_s2",
                    "path": "x.py",
                    "unified_diff": "diff",
                    "is_new_file": True,
                    "is_delete": False,
                },
            },
            ensure_ascii=False,
        )

    applied = MagicMock()
    applied.path = "x.py"
    applied.unified_diff = "diff"
    applied.is_new_file = True
    applied.is_delete = False
    applied.status = PatchStatus.APPLIED
    applied.error = None
    applied.applied_hunks = None

    decide = AsyncMock(return_value=applied)
    wait = AsyncMock(side_effect=AssertionError("YOLO must not wait"))

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_handle)
    monkeypatch.setattr(gate_hooks, "decide_patch", decide)
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
    assert not any(e.get("type") == "await_approval" for e in events)
    assert any(e.get("type") == "diff" and e.get("status") == "applied" for e in events)
    decide.assert_awaited_once()
    wait.assert_not_awaited()


def test_resolve_gate_decision_passes_phase() -> None:
    seen: dict[str, Any] = {}

    async def hook(**kwargs: Any) -> GatePresetDecision:
        seen["phase"] = kwargs.get("phase")
        seen["await_payload"] = kwargs.get("await_payload")
        return GatePresetDecision(auto_apply=False, action="wait")

    cfg = LoopConfig(goal_mode=False, preset=LoopPreset.TRUSTED, before_tool_call=hook)
    decision = asyncio.run(
        resolve_gate_decision(
            cfg,
            name="propose_edit",
            phase="await_gate",
            await_payload={AWAIT_PATCH_KEY: True},
        )
    )
    assert decision.action == "wait"
    assert seen["phase"] == "await_gate"
    assert seen["await_payload"] == {AWAIT_PATCH_KEY: True}
    assert seen["phase"] != "pre"
