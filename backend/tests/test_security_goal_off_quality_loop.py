"""Goal OFF emits no quality-loop events even when F1/F2/F7 hooks are still attached.

`with_goal_mode(False)` clearing hooks is already covered by test_goal_hooks.py.
This file locks the loop: goal_mode false means zero Turn Goal inject, checkpoint,
and exploration converge. It does not enable auto_compress and does not install
transform_context (C6/C7/N2 stay untouched).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from agent_window.agent.checkpoint import CHECKPOINT_MARKER
from agent_window.agent.exploration import EXPLORATION_CONVERGE_MARKER
from agent_window.agent.goal import GOAL_MARKER
from agent_window.config import settings
from agent_window.core.loop_config import LoopConfig
from agent_window.services.agent_settings import load_agent_settings


_QUALITY_MARKERS = (GOAL_MARKER, CHECKPOINT_MARKER, EXPLORATION_CONVERGE_MARKER)


def test_goal_off_with_quality_hooks_emits_no_quality_loop(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three exploration tool calls must not inject goal, checkpoint, or converge text."""
    monkeypatch.setattr(settings, "app_data_dir", str(tmp_path))
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        str(tmp_path),
    )
    assert load_agent_settings()["auto_compress"] is False

    enabled = LoopConfig.default().with_goal_mode(True)
    if (
        enabled.on_turn_start is None
        or enabled.after_tool_call is None
        or enabled.after_tool_batch is None
    ):
        pytest.skip(
            "Goal quality hooks are not installed on LoopConfig; "
            "there is no quality loop to force off."
        )
    off = replace(enabled, goal_mode=False)
    if off.on_turn_start is None or off.after_tool_batch is None or off.after_tool_call is None:
        pytest.skip(
            "Quality hooks are cleared whenever goal_mode is false; "
            "no stale-hook path to assert."
        )
    assert off.goal_mode is False
    assert off.transform_context is None
    assert off.goal_mode is not True

    monkeypatch.setattr(
        "agent_window.agent.loop.load_agent_settings",
        lambda: {
            "disabled_tools": [],
            "max_tool_iters": 8,
            "checkpoint_every_n_tools": 2,
            "exploration_repeat_threshold": 3,
            "auto_compress": False,
        },
    )
    captured: list[list[dict]] = []
    chat_calls = 0

    async def fake_chat(working, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        captured.append(list(working))
        if chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc2", "name": "list_dir", "arguments": "{}"},
                    {"id": "tc3", "name": "list_dir", "arguments": "{}"},
                ],
            }
        return {"content": "目录看过了。", "tool_calls": []}

    async def fake_tool(name, raw_args):
        return json.dumps({"ok": True, "name": name})

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_tool)

    from agent_window.agent.loop import run_agent_loop

    async def collect() -> list[dict]:
        events: list[dict] = []
        async for event in run_agent_loop(
            [{"role": "user", "content": "看看仓库里有什么"}],
            goal="ship the notes",
            config=off,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())
    event_blob = json.dumps(events, ensure_ascii=False)
    prompt_blob = json.dumps(captured, ensure_ascii=False)
    quality_events = [
        event
        for event in events
        if event.get("type") in {"turn_goal", "progress_checkpoint"}
    ]
    leaked_markers = [marker for marker in _QUALITY_MARKERS if marker in event_blob or marker in prompt_blob]
    assert quality_events == []
    assert leaked_markers == []
    assert chat_calls >= 1
    assert any(event.get("type") == "token" for event in events)
    assert any(event.get("type") == "done" for event in events)
    assert not any(event.get("type") == "error" for event in events)
    assert load_agent_settings()["auto_compress"] is False
