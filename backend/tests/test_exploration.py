"""F7 exploration convergence: helpers + loop integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_window.agent.exploration import (
    EXPLORATION_CONVERGE_MARKER,
    exploration_repeat_threshold_from_settings,
    format_exploration_converge_message,
    should_converge_exploration,
    update_exploration_streak,
)


def test_exploration_threshold_clamp() -> None:
    assert exploration_repeat_threshold_from_settings(0) == 0
    assert exploration_repeat_threshold_from_settings(1) == 3
    assert exploration_repeat_threshold_from_settings(99) == 12
    assert exploration_repeat_threshold_from_settings("nope") == 6


def test_exploration_message_contains_marker_goal_tool() -> None:
    msg = format_exploration_converge_message("列出 src 目录", "list_dir", 3)
    assert EXPLORATION_CONVERGE_MARKER in msg
    assert "列出 src 目录" in msg
    assert "list_dir" in msg
    assert "3" in msg
    assert "禁止" in msg
    assert "收工" in msg


def test_exploration_streak_logic() -> None:
    tool, streak = update_exploration_streak(None, 0, "list_dir")
    assert tool == "list_dir"
    assert streak == 1

    tool, streak = update_exploration_streak(tool, streak, "list_dir")
    assert tool == "list_dir"
    assert streak == 2

    tool, streak = update_exploration_streak(tool, streak, "grep")
    assert tool == "grep"
    assert streak == 1

    tool, streak = update_exploration_streak(tool, streak, "propose_edit")
    assert tool is None
    assert streak == 0


def test_should_converge_exploration() -> None:
    assert should_converge_exploration(3, 3) is True
    assert should_converge_exploration(2, 3) is False
    assert should_converge_exploration(5, 0) is False


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    return tmp_path


def test_exploration_repeat_threshold_settings(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings

    loaded = load_agent_settings()
    assert loaded["exploration_repeat_threshold"] == 6

    saved = save_agent_settings({"exploration_repeat_threshold": 1})
    assert saved["exploration_repeat_threshold"] == 3
    assert load_agent_settings()["exploration_repeat_threshold"] == 3

    saved = save_agent_settings({"exploration_repeat_threshold": 0})
    assert saved["exploration_repeat_threshold"] == 0
    assert load_agent_settings()["exploration_repeat_threshold"] == 0


def test_loop_injects_exploration_converge_after_repeated_tool(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    import asyncio

    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings(
        {
            "exploration_repeat_threshold": 3,
            "checkpoint_every_n_tools": 0,
        }
    )

    chat_calls: list[list[dict]] = []

    async def fake_chat(working, tools=None, model=None):
        chat_calls.append(list(working))
        n = len(chat_calls)
        if n == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc2", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc3", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "对照目标已总结探索结果。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop
    from agent_window.core.loop_config import LoopConfig

    async def collect_events() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "explore repo"}],
            goal="explore repo",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect_events())

    converge_events = [
        e
        for e in events
        if e.get("type") == "progress_checkpoint" and e.get("reason") == "exploration"
    ]
    assert len(converge_events) == 1
    assert converge_events[0]["tool"] == "list_dir"
    assert converge_events[0]["streak"] == 3
    assert converge_events[0]["goal"] == "explore repo"

    assert len(chat_calls) >= 2
    second_working = chat_calls[1]
    converge_msgs = [
        m
        for m in second_working
        if m.get("role") == "user"
        and isinstance(m.get("content"), str)
        and EXPLORATION_CONVERGE_MARKER in m["content"]
    ]
    assert len(converge_msgs) == 1
    # Converge user msg must not sit between assistant.tool_calls and its tool results.
    _assert_tool_call_pairs_intact(second_working)


def _assert_tool_call_pairs_intact(messages: list[dict]) -> None:
    """Every assistant tool_calls id must be answered by tool msgs before the next non-tool role."""
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            ids = [tc["id"] for tc in m["tool_calls"]]
            j = i + 1
            seen: set[str] = set()
            while j < len(messages) and messages[j].get("role") == "tool":
                tid = messages[j].get("tool_call_id")
                if isinstance(tid, str):
                    seen.add(tid)
                j += 1
            missing = [tid for tid in ids if tid not in seen]
            assert not missing, f"tool results missing or interrupted for {missing}; slice={messages[i:j+1]}"
            i = j
            continue
        i += 1


def test_loop_exploration_converge_not_between_tool_results(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    """Regression: threshold hit mid-batch must not inject user before remaining tool msgs."""
    import asyncio

    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings(
        {
            "exploration_repeat_threshold": 3,
            "checkpoint_every_n_tools": 0,
        }
    )

    chat_calls: list[list[dict]] = []

    async def fake_chat(working, tools=None, model=None):
        chat_calls.append(list(working))
        n = len(chat_calls)
        if n == 1:
            # Two tools — streak becomes 2, no converge yet.
            return {
                "content": "",
                "tool_calls": [
                    {"id": "a1", "name": "list_dir", "arguments": "{}"},
                    {"id": "a2", "name": "list_dir", "arguments": "{}"},
                ],
            }
        if n == 2:
            # Two more — streak hits 3 after first of this batch; must still answer both tools
            # before injecting 【探索收敛】.
            return {
                "content": "",
                "tool_calls": [
                    {"id": "b1", "name": "list_dir", "arguments": "{}"},
                    {"id": "b2", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "收敛后的总结。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop
    from agent_window.core.loop_config import LoopConfig

    async def collect() -> list[dict]:
        out: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "browse"}],
            goal="browse workspace",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            out.append(ev)
        return out

    events = asyncio.run(collect())
    assert any(
        e.get("type") == "progress_checkpoint" and e.get("reason") == "exploration"
        for e in events
    )
    assert len(chat_calls) >= 3
    third = chat_calls[2]
    _assert_tool_call_pairs_intact(third)
    # Find assistant with b1/b2 then ensure next two are tools then user converge.
    for idx, m in enumerate(third):
        if m.get("role") == "assistant" and any(
            tc.get("id") == "b1" for tc in (m.get("tool_calls") or [])
        ):
            assert third[idx + 1]["role"] == "tool"
            assert third[idx + 2]["role"] == "tool"
            assert third[idx + 1]["tool_call_id"] == "b1"
            assert third[idx + 2]["tool_call_id"] == "b2"
            assert third[idx + 3]["role"] == "user"
            assert EXPLORATION_CONVERGE_MARKER in third[idx + 3]["content"]
            break
    else:
        raise AssertionError("assistant batch with b1/b2 not found in third chat working")


def test_append_missing_tool_results_fills_gaps() -> None:
    from agent_window.agent.loop import _append_missing_tool_results

    msgs: list[dict] = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "x1", "type": "function", "function": {"name": "list_dir", "arguments": "{}"}},
                {"id": "x2", "type": "function", "function": {"name": "list_dir", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "x1", "content": "{}"},
    ]
    _append_missing_tool_results(
        msgs,
        [
            {"id": "x1", "name": "list_dir"},
            {"id": "x2", "name": "list_dir"},
        ],
        answered={"x1": "{}"},
        stub_content='{"status":"skipped"}',
    )
    assert msgs[-1]["tool_call_id"] == "x2"
    assert "skipped" in msgs[-1]["content"]
    # x1 not duplicated
    assert sum(1 for m in msgs if m.get("tool_call_id") == "x1") == 1


def test_loop_exploration_no_converge_when_action_tool_resets_streak(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    import asyncio

    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings(
        {
            "exploration_repeat_threshold": 3,
            "checkpoint_every_n_tools": 0,
        }
    )

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
                    {"id": "tc3", "name": "propose_edit", "arguments": "{}"},
                    {"id": "tc4", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc5", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "done", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop
    from agent_window.core.loop_config import LoopConfig

    async def collect_events() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "explore"}],
            goal="explore",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect_events())
    converge_events = [
        e
        for e in events
        if e.get("type") == "progress_checkpoint" and e.get("reason") == "exploration"
    ]
    assert len(converge_events) == 0


def test_loop_exploration_threshold_zero_no_inject(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    import asyncio

    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings(
        {
            "exploration_repeat_threshold": 0,
            "checkpoint_every_n_tools": 0,
        }
    )

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
                    {"id": "tc3", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "done", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop
    from agent_window.core.loop_config import LoopConfig

    async def collect_events() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop(
            [{"role": "user", "content": "explore"}],
            goal="explore",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect_events())
    converge_events = [
        e
        for e in events
        if e.get("type") == "progress_checkpoint" and e.get("reason") == "exploration"
    ]
    assert len(converge_events) == 0
