"""F9 Foundation dogfood — scripted two-turn scenario + loop integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from agent_window.dogfood.f9_scenario import (
    F9_USER_TURN1,
    F9_USER_TURN2,
    assert_f9_turn2_outcome,
    assistant_has_conclusion,
    extract_f9_turn2_goal,
    goal_covers_f9_intent,
    trace_has_tool_activity,
)


def test_f9_turn2_goal_inherits_turn1() -> None:
    goal = extract_f9_turn2_goal([F9_USER_TURN1])
    assert goal_covers_f9_intent(goal)
    assert "好的" not in goal or "ImportError" in goal or "pytest" in goal


def test_f9_goal_without_prior_is_not_valid() -> None:
    from agent_window.agent.goal import extract_turn_goal

    lone = extract_turn_goal(F9_USER_TURN2, [])
    assert not goal_covers_f9_intent(lone)


def test_f9_assistant_conclusion_heuristic() -> None:
    goal = extract_f9_turn2_goal([F9_USER_TURN1])
    ok = (
        "对照目标收工：ImportError 多半是 PYTHONPATH 未包含 backend/src。"
        "已用 list_dir 确认包在 src/agent_window；建议在 backend 目录设置 PYTHONPATH=src 再跑 pytest。"
    )
    assert assistant_has_conclusion(ok, goal)
    assert not assistant_has_conclusion("好的", goal)
    assert not assistant_has_conclusion("", goal)


def test_f9_scripted_turn2_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked agent loop for turn 2: Goal + tools + goal-aligned conclusion."""
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    goal = extract_f9_turn2_goal([F9_USER_TURN1])
    chat_calls: list[int] = []

    async def fake_chat(messages, tools=None, model=None):
        chat_calls.append(len(messages))
        n = len(chat_calls)
        if n == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": '{"path":"backend"}'},
                    {"id": "tc2", "name": "grep", "arguments": '{"pattern":"PYTHONPATH"}'},
                ],
            }
        return {
            "content": (
                "对照目标收工：ImportError 因未把 backend/src 加入 PYTHONPATH。"
                "list_dir 看到 src/agent_window；grep 未见现成 env 配置。"
                "请在 backend 下执行 PYTHONPATH=src python -m pytest tests/。"
            ),
            "tool_calls": [],
        }

    async def fake_tool(name: str, raw_args: Any) -> str:
        if name == "list_dir":
            return json.dumps({"entries": ["src", "tests", "pyproject.toml"]}, ensure_ascii=False)
        return json.dumps({"match_count": 0, "pattern": "PYTHONPATH"}, ensure_ascii=False)

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
                },
                {
                    "type": "function",
                    "function": {"name": "grep", "parameters": {"type": "object"}},
                },
            ]

    monkeypatch.setattr(loop_mod, "registry", _Reg())

    history = [
        {"role": "user", "content": F9_USER_TURN1},
        {
            "role": "assistant",
            "content": "可能是 PYTHONPATH 未包含 src；排查：确认 backend 目录、查看 pyproject 与 .venv。",
        },
        {"role": "user", "content": F9_USER_TURN2},
    ]

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        final = ""
        async for ev in loop_mod.run_agent_loop(
            history,
            goal=goal,
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                final += ev.get("content") or ""
            if ev.get("type") == "done" and ev.get("content"):
                final = ev["content"]
        return events, final.strip()

    events, assistant_text = asyncio.run(_run())

    assert len(chat_calls) == 2
    assert_f9_turn2_outcome(events, assistant_text, goal)
    assert trace_has_tool_activity(events, min_results=2)


def test_f9_no_blank_assistant_on_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """F6: loop must finish with non-empty assistant content on happy path."""
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        return {
            "content": "对照目标收工：已确认 backend/src 布局，请设置 PYTHONPATH=src 后重跑 pytest。",
            "tool_calls": [],
        }

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 4},
    )
    monkeypatch.setattr(
        loop_mod,
        "registry",
        type("_R", (), {"get_openai_tools": lambda self: []})(),
    )

    goal = extract_f9_turn2_goal([F9_USER_TURN1])

    async def _run() -> str:
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": F9_USER_TURN2}],
            goal=goal,
            config=LoopConfig.default().with_goal_mode(True),
        ):
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return text.strip()

    out = asyncio.run(_run())
    assert len(out) >= 20
    assert assistant_has_conclusion(out, goal)
