"""F2 progress checkpoint: helpers + loop integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_window.agent.checkpoint import (
    CHECKPOINT_MARKER,
    checkpoint_interval_from_settings,
    format_checkpoint_user_message,
    should_checkpoint,
)


def test_checkpoint_message_contains_marker_and_goal() -> None:
    msg = format_checkpoint_user_message("列出 src 目录")
    assert CHECKPOINT_MARKER in msg
    assert "列出 src 目录" in msg
    assert "收工" in msg
    assert "换手段" in msg


def test_should_checkpoint_interval() -> None:
    assert should_checkpoint(4, False, 4) == "interval"
    assert should_checkpoint(3, False, 4) is None
    assert should_checkpoint(0, False, 4) is None


def test_should_checkpoint_gate() -> None:
    assert should_checkpoint(1, True, 4) == "gate"
    assert should_checkpoint(0, True, 0) == "gate"


def test_checkpoint_interval_clamp() -> None:
    assert checkpoint_interval_from_settings(0) == 0
    assert checkpoint_interval_from_settings(1) == 2
    assert checkpoint_interval_from_settings(99) == 16
    assert checkpoint_interval_from_settings("nope") == 4


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    return tmp_path


def test_checkpoint_every_n_tools_settings(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings

    loaded = load_agent_settings()
    assert loaded["checkpoint_every_n_tools"] == 4

    saved = save_agent_settings({"checkpoint_every_n_tools": 1})
    assert saved["checkpoint_every_n_tools"] == 2
    assert load_agent_settings()["checkpoint_every_n_tools"] != 1

    saved = save_agent_settings({"checkpoint_every_n_tools": 0})
    assert saved["checkpoint_every_n_tools"] == 0
    assert load_agent_settings()["checkpoint_every_n_tools"] == 0


def test_loop_emits_checkpoint_after_n_tools(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    import asyncio

    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings({"checkpoint_every_n_tools": 2})

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
                ],
            }
        if n == 2:
            return {"content": "对照目标已完成探索。", "tool_calls": []}
        return {"content": "fallback", "tool_calls": []}

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

    checkpoint_events = [e for e in events if e.get("type") == "progress_checkpoint"]
    assert len(checkpoint_events) == 2
    assert checkpoint_events[0]["reason"] == "interval"
    assert checkpoint_events[0]["tools_since_last"] == 2
    # Opening event has no reply; final-only answer settles without duplicating into the bar.
    assert not checkpoint_events[0].get("reply")
    assert checkpoint_events[1].get("settled") is True
    assert not checkpoint_events[1].get("reply")

    assert len(chat_calls) >= 2
    second_working = chat_calls[1]
    checkpoint_msgs = [
        m
        for m in second_working
        if m.get("role") == "user"
        and isinstance(m.get("content"), str)
        and CHECKPOINT_MARKER in m["content"]
    ]
    assert len(checkpoint_msgs) == 1

    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1


def test_loop_emits_checkpoint_reply_when_continuing_tools(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    """After checkpoint, mid-loop narration + more tools must surface as reply."""
    import asyncio

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
        if chat_calls == 2:
            return {
                "content": "进度：已 list 两处目录，无阻塞；下一步继续 grep 后收工。",
                "tool_calls": [
                    {"id": "tc3", "name": "grep", "arguments": '{"pattern":"x"}'},
                ],
            }
        return {"content": "对照目标收工：结构已看清。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)
    monkeypatch.setattr(
        "agent_window.agent.loop.registry",
        type(
            "_R",
            (),
            {
                "get_openai_tools": lambda self: [
                    {
                        "type": "function",
                        "function": {"name": "list_dir", "parameters": {"type": "object"}},
                    },
                    {
                        "type": "function",
                        "function": {"name": "grep", "parameters": {"type": "object"}},
                    },
                ]
            },
        )(),
    )

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
    cps = [e for e in events if e.get("type") == "progress_checkpoint"]
    assert len(cps) >= 2
    assert cps[0].get("reply") in (None, "")
    assert cps[1].get("reply")
    assert "无阻塞" in cps[1]["reply"]
    assert "收工" in cps[1]["reply"] or "grep" in cps[1]["reply"]

    tokens = "".join(e.get("content") or "" for e in events if e.get("type") == "token")
    assert "对照目标收工" in tokens
    # Mid-loop narration must not be the only final token dump duplicate requirement:
    # final answer is separate; reply is on checkpoint.
    assert "已 list 两处" not in tokens or "对照目标收工" in tokens


def test_loop_settles_checkpoint_when_model_skips_narration(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    """After checkpoint, tools-only (no content) must settle UI waiting state."""
    import asyncio

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
        if chat_calls == 2:
            # Skip narration: continue tools with empty content.
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc3", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "对照目标收工。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)
    monkeypatch.setattr(
        "agent_window.agent.loop.registry",
        type(
            "_R",
            (),
            {
                "get_openai_tools": lambda self: [
                    {
                        "type": "function",
                        "function": {"name": "list_dir", "parameters": {"type": "object"}},
                    },
                ]
            },
        )(),
    )

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
    cps = [e for e in events if e.get("type") == "progress_checkpoint"]
    assert any(e.get("settled") for e in cps)
    assert not any((e.get("reply") or "").strip() for e in cps)


def test_clip_checkpoint_reply() -> None:
    from agent_window.agent.checkpoint import clip_checkpoint_reply

    assert "进度" in clip_checkpoint_reply("进度：ok")
    assert CHECKPOINT_MARKER not in clip_checkpoint_reply(
        f"{CHECKPOINT_MARKER}\n进度：已完成两步"
    )
    assert clip_checkpoint_reply("") == ""
    long = "字" * 900
    clipped = clip_checkpoint_reply(long)
    assert len(clipped) <= 800
    assert clipped.endswith("…")
