"""Loop exit honesty: EMPTY_RESPONSE, tools-only synthesize, edit-intent nudge."""

from __future__ import annotations

import asyncio
import json

import pytest


def test_intent_detects_edit_not_pure_explore() -> None:
    from agent_window.agent.loop_exit import user_requests_repo_edit

    assert user_requests_repo_edit("列出 backend 目录") is False
    assert user_requests_repo_edit("看看 SettingsPanel 干什么") is False
    assert user_requests_repo_edit("解释这段代码") is False

    assert user_requests_repo_edit("请用 propose_edit 改 SettingsPanel") is True
    assert (
        user_requests_repo_edit(
            "请在本仓库做一件可验收的小改动：改 Settings 面板，用 propose_edit 落地"
        )
        is True
    )
    assert user_requests_repo_edit("实现条目数显示，禁止只读收工") is True
    assert user_requests_repo_edit("把附件保存为 workspace 文件") is True
    assert user_requests_repo_edit("请将附件写入工作区 dogfood_att.txt") is True
    assert user_requests_repo_edit("save the attachment to workspace") is True


def test_synthesize_explore_vs_edit_intent() -> None:
    from agent_window.agent.loop_exit import synthesize_tools_only_reply

    explore = synthesize_tools_only_reply("列出目录", edit_intent=False, write_gate_seen=False)
    assert "查阅" in explore or "看代码" in explore
    assert "任务未完成" not in explore

    missing = synthesize_tools_only_reply(
        "改 Settings",
        edit_intent=True,
        write_gate_seen=False,
        edit_nudge_used=True,
    )
    assert "propose_edit" in missing
    assert "未改" in missing or "任务未完成" in missing
    assert "催促" in missing
    assert "工具调用已完成，但模型未给出文字说明" not in missing


def test_should_nudge_only_once_when_empty_edit_intent() -> None:
    from agent_window.agent.loop_exit import should_nudge_missing_edit

    assert (
        should_nudge_missing_edit(
            edit_intent=True,
            write_gate_seen=False,
            edit_nudge_used=False,
            tools_ran=3,
            has_content=False,
        )
        is True
    )
    assert (
        should_nudge_missing_edit(
            edit_intent=True,
            write_gate_seen=False,
            edit_nudge_used=True,
            tools_ran=3,
            has_content=False,
        )
        is False
    )
    assert (
        should_nudge_missing_edit(
            edit_intent=False,
            write_gate_seen=False,
            edit_nudge_used=False,
            tools_ran=3,
            has_content=False,
        )
        is False
    )
    assert (
        should_nudge_missing_edit(
            edit_intent=True,
            write_gate_seen=True,
            edit_nudge_used=False,
            tools_ran=3,
            has_content=False,
        )
        is False
    )
    assert (
        should_nudge_missing_edit(
            edit_intent=True,
            write_gate_seen=False,
            edit_nudge_used=False,
            tools_ran=3,
            has_content=True,
        )
        is False
    )


def test_explore_then_empty_does_not_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    chat_calls = 0

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "name": "list_dir", "arguments": '{"path":"backend"}'},
                ],
            }
        return {"content": "", "tool_calls": []}

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"entries": ["src"]}, ensure_ascii=False)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_tool)
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 4},
    )
    monkeypatch.setattr(
        loop_mod,
        "registry",
        type(
            "_R",
            (),
            {
                "get_openai_tools": lambda self: [
                    {"type": "function", "function": {"name": "list_dir"}}
                ]
            },
        )(),
    )

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "列出 backend 目录"}],
            goal=None,
            config=LoopConfig.default().with_goal_mode(False),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return events, text.strip()

    events, assistant_text = asyncio.run(_run())
    assert chat_calls == 2
    assert not any(ev.get("type") == "edit_nudge" for ev in events)
    assert not any(ev.get("code") == "EMPTY_RESPONSE" for ev in events)
    assert "查阅" in assistant_text or "看代码" in assistant_text
    assert "任务未完成" not in assistant_text.split("若要改")[0]


def test_edit_intent_empty_gets_nudge_then_honest_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.agent.loop_exit import EDIT_NUDGE_MARKER
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    chat_calls = 0
    saw_nudge_in_messages = False

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls, saw_nudge_in_messages
        chat_calls += 1
        for m in messages:
            if m.get("role") == "user" and EDIT_NUDGE_MARKER in str(m.get("content") or ""):
                saw_nudge_in_messages = True
        if chat_calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "name": "read_file",
                        "arguments": '{"path":"src/components/SettingsPanel.tsx"}',
                    },
                ],
            }
        # After tools: empty stop → nudge → second empty stop → honest synthesize
        return {"content": "", "tool_calls": []}

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"content": "export function SettingsPanel() {}"}, ensure_ascii=False)

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(loop_mod, "handle_function_call", fake_tool)
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 0},
    )
    monkeypatch.setattr(
        loop_mod,
        "registry",
        type(
            "_R",
            (),
            {
                "get_openai_tools": lambda self: [
                    {"type": "function", "function": {"name": "read_file"}},
                    {"type": "function", "function": {"name": "propose_edit"}},
                ]
            },
        )(),
    )

    user = (
        "请用 propose_edit 改 src/components/SettingsPanel.tsx 显示条目数；"
        "禁止只读收工。"
    )

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": user}],
            goal=None,
            config=LoopConfig.default().with_goal_mode(False),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return events, text.strip()

    events, assistant_text = asyncio.run(_run())
    nudges = [e for e in events if e.get("type") == "edit_nudge"]
    assert len(nudges) == 1
    assert nudges[0].get("reason") == "missing_propose_edit"
    assert saw_nudge_in_messages is True
    # turn1 tools + turn2 empty→nudge continue + turn3 empty→done = 3 chats
    assert chat_calls == 3
    assert "propose_edit" in assistant_text
    assert "未改" in assistant_text or "任务未完成" in assistant_text
    assert "工具调用已完成，但模型未给出文字说明" not in assistant_text


def test_zero_tool_empty_is_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.agent.loop_exit import EMPTY_RESPONSE_MESSAGE
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    async def fake_chat(messages, tools=None, model=None):
        return {"content": "", "tool_calls": []}

    monkeypatch.setattr(provider, "chat_complete", fake_chat)
    monkeypatch.setattr(
        loop_mod,
        "load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8},
    )
    monkeypatch.setattr(
        loop_mod,
        "registry",
        type("_R", (), {"get_openai_tools": lambda self: []})(),
    )

    async def _run() -> list[dict]:
        events: list[dict] = []
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "你好"}],
            config=LoopConfig.default(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    errs = [e for e in events if e.get("type") == "error" and e.get("code") == "EMPTY_RESPONSE"]
    assert len(errs) == 1
    assert errs[0].get("message") == EMPTY_RESPONSE_MESSAGE
    assert "既未调用工具" in errs[0]["message"]
    assert not any(e.get("type") == "token" for e in events)
