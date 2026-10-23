"""A1a: config.goal_mode gates Turn Goal inject, checkpoints, exploration converge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_window.agent.goal import GOAL_MARKER
from agent_window.core.loop_config import LoopConfig


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    return tmp_path


def test_goal_mode_off_skips_turn_goal_and_inject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OFF + goal string + text-only → no turn_goal event, no inject marker."""
    from agent_window.agent.loop import run_agent_loop

    captured: list[list[dict]] = []

    async def fake_chat(working, tools=None, model=None):
        captured.append(list(working))
        return {"content": "你好，目录如下。", "tool_calls": []}

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr(
        "agent_window.agent.loop.load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 4},
    )
    monkeypatch.setattr(
        "agent_window.agent.loop.registry",
        type("_R", (), {"get_openai_tools": lambda self: []})(),
    )

    async def collect() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "列出目录"}],
            goal="列出目录",
            config=LoopConfig.default(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect())

    assert not any(e.get("type") == "turn_goal" for e in events)
    assert any(e.get("type") == "token" for e in events)
    assert any(e.get("type") == "done" for e in events)
    assert captured
    for msg in captured[0]:
        content = msg.get("content")
        if isinstance(content, str):
            assert GOAL_MARKER not in content


def test_goal_mode_off_skips_progress_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    """OFF + tools that would hit interval checkpoint → no progress_checkpoint."""
    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings({"checkpoint_every_n_tools": 2})

    chat_calls = 0

    async def fake_chat(working, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc2", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "探索完毕。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop

    async def collect() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "explore repo"}],
            goal="explore repo",
            config=LoopConfig.default(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect())

    assert not any(e.get("type") == "progress_checkpoint" for e in events)
    assert not any(e.get("type") == "turn_goal" for e in events)
    assert any(e.get("type") == "token" for e in events)
    assert any(e.get("type") == "done" for e in events)


def test_goal_mode_on_yields_turn_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ON + goal + text-only → must yield turn_goal."""
    from agent_window.agent.loop import run_agent_loop

    captured: list[list[dict]] = []

    async def fake_chat(working, tools=None, model=None):
        captured.append(list(working))
        return {"content": "已对照目标说明。", "tool_calls": []}

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr(
        "agent_window.agent.loop.load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8},
    )
    monkeypatch.setattr(
        "agent_window.agent.loop.registry",
        type("_R", (), {"get_openai_tools": lambda self: []})(),
    )

    goal = "列出目录"

    async def collect() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "列出目录"}],
            goal=goal,
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect())

    turn_goals = [e for e in events if e.get("type") == "turn_goal"]
    assert len(turn_goals) == 1
    assert turn_goals[0].get("goal") == goal
    assert any(e.get("type") == "token" for e in events)
    assert any(e.get("type") == "done" for e in events)
    assert captured
    assert any(
        isinstance(m.get("content"), str) and GOAL_MARKER in m["content"]
        for m in captured[0]
    )
