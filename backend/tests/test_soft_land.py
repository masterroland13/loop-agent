"""Honest soft-land when max_tool_iters is hit — mid-task wrap-up, not fake done."""

from __future__ import annotations

import asyncio
import json

import pytest


def test_soft_land_prompt_is_structured_and_forbids_fake_done() -> None:
    from agent_window.agent.loop import soft_land_user_prompt

    prompt = soft_land_user_prompt(max_tool_iters=8, turn_goal="修登录超时")
    assert "强制软着陆" in prompt
    assert "修登录超时" in prompt
    assert "## 已完成" in prompt
    assert "## 未完成 / 阻塞" in prompt
    assert "## 建议下一步" in prompt
    assert "不要声称" in prompt
    assert "可以收工" in prompt  # listed as forbidden claim
    assert "结案" in prompt
    assert "任务结束" in prompt
    # Must not read like a normal "you're done, summarize" nudge
    assert "请对照目标收工" not in prompt
    assert "已全部完成" not in prompt or "不要声称" in prompt


def test_soft_land_continue_message_carries_goal_and_sections() -> None:
    from agent_window.agent.loop import soft_land_continue_user_message

    reply = (
        "⚠️ 工具轮次已用尽…\n\n"
        "## 已完成\n"
        "读完 auth.ts\n\n"
        "## 未完成 / 阻塞\n"
        "尚未改 salt 编码\n\n"
        "## 建议下一步\n"
        "给 verifySalt 补 encode\n"
    )
    msg = soft_land_continue_user_message(turn_goal="修登录超时", soft_land_reply=reply)
    assert "软着陆处继续" in msg
    assert "本轮目标：修登录超时" in msg
    assert "尚未改 salt 编码" in msg
    assert "给 verifySalt 补 encode" in msg
    assert "不要重复已经完成" in msg
    assert "最大工具轮次" in msg
    # Must not be a bare continue
    assert msg.strip() != "继续"
    assert "已全部完成" not in msg


def test_soft_land_continue_without_sections_still_usable() -> None:
    from agent_window.agent.loop import soft_land_continue_user_message

    msg = soft_land_continue_user_message(turn_goal=None, soft_land_reply="随便一段无结构文字")
    assert "软着陆处继续" in msg
    assert "本轮目标" not in msg
    assert "上轮未写明" in msg
    assert msg.strip() != "继续"


def test_soft_land_banner_marks_incomplete() -> None:
    from agent_window.agent.loop import soft_land_banner, synthesize_soft_land_reply

    banner = soft_land_banner(max_tool_iters=8, tools_ran=8, turn_goal="清扫仓库")
    assert "工具轮次已用尽" in banner
    assert "提前收口" in banner
    assert "不代表任务已完成" in banner
    assert "清扫仓库" in banner
    assert "已中止" not in banner
    assert "任务完成" not in banner

    synth = synthesize_soft_land_reply(max_tool_iters=8, tools_ran=8, turn_goal="清扫仓库")
    assert banner.split("\n")[0] in synth
    assert "## 已完成" in synth
    assert "## 未完成 / 阻塞" in synth
    assert "## 建议下一步" in synth
    assert "未能收工" in synth
    assert "可以收工" not in synth


def test_soft_land_loop_emits_event_and_prepends_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    chat_calls = 0
    soft_land_prompt_seen = False

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls, soft_land_prompt_seen
        chat_calls += 1
        if tools is None:
            # Soft-land call: no tools. Model tries to claim done — banner must still lead.
            last = messages[-1] if messages else {}
            if last.get("role") == "user":
                soft_land_prompt_seen = "强制软着陆" in str(last.get("content") or "")
            return {
                "content": "审查完毕，已全部完成，可以收工。",
                "tool_calls": [],
            }
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"tc{chat_calls}",
                    "name": "list_dir",
                    "arguments": '{"path":"."}',
                }
            ],
        }

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"entries": ["src"]}, ensure_ascii=False)

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
                    {"type": "function", "function": {"name": "list_dir"}}
                ]
            },
        )(),
    )

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "持续探索仓库"}],
            goal="持续探索仓库",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return events, text.strip()

    events, assistant_text = asyncio.run(_run())

    soft_events = [e for e in events if e.get("type") == "soft_land"]
    assert len(soft_events) == 1
    assert soft_events[0].get("reason") == "max_tool_iters"
    assert soft_events[0].get("max_tool_iters") == 8
    assert soft_events[0].get("tools_ran") == 8
    assert soft_land_prompt_seen is True

    assert assistant_text.startswith("⚠️") or "工具轮次已用尽" in assistant_text[:80]
    assert "不代表任务已完成" in assistant_text
    assert "提前收口" in assistant_text
    # Model's false-done claim may still appear after the banner, but must not stand alone
    assert "已中止" not in assistant_text
    assert not any(e.get("code") == "TOOL_LOOP_LIMIT" for e in events)
    # Soft-land is one extra chat after 8 tool turns
    assert chat_calls == 9


def test_soft_land_empty_model_uses_synthesize(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.core.loop_config import LoopConfig
    from agent_window.services.provider import provider

    chat_calls = 0

    async def fake_chat(messages, tools=None, model=None):
        nonlocal chat_calls
        chat_calls += 1
        if tools is None:
            return {"content": "", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"tc{chat_calls}",
                    "name": "list_dir",
                    "arguments": '{"path":"."}',
                }
            ],
        }

    async def fake_tool(name: str, raw_args) -> str:
        return json.dumps({"ok": True}, ensure_ascii=False)

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
                    {"type": "function", "function": {"name": "list_dir"}}
                ]
            },
        )(),
    )

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "探索"}],
            goal="探索",
            config=LoopConfig.default().with_goal_mode(False),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return events, text.strip()

    events, assistant_text = asyncio.run(_run())

    assert any(e.get("type") == "soft_land" for e in events)
    assert "未能收工" in assistant_text
    assert "不代表任务已完成" in assistant_text
    assert not any(e.get("code") == "TOOL_LOOP_LIMIT" for e in events)


def test_event_from_sse_maps_soft_land() -> None:
    from agent_window.agent.turn_event import event_from_sse

    ev = event_from_sse(
        {
            "type": "soft_land",
            "reason": "max_tool_iters",
            "max_tool_iters": 8,
            "tools_ran": 8,
            "goal": "g",
        }
    )
    assert ev is not None
    assert ev["type"] == "soft_land"
    assert "cap=8" in (ev.get("summary") or "")
    assert ev.get("reason") == "max_tool_iters"
    assert ev.get("goal") == "g"
