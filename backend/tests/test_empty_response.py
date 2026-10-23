"""EMPTY_RESPONSE guard when model ends tool-only turns without narration."""

from __future__ import annotations

import asyncio
import json

import pytest


def test_tool_then_empty_final_yields_synthesized_reply(monkeypatch: pytest.MonkeyPatch) -> None:
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
        type("_R", (), {"get_openai_tools": lambda self: [{"type": "function", "function": {"name": "list_dir"}}]})(),
    )

    async def _run() -> tuple[list[dict], str]:
        events: list[dict] = []
        text = ""
        async for ev in loop_mod.run_agent_loop(
            [{"role": "user", "content": "列出 backend 目录"}],
            goal="列出 backend 目录",
            config=LoopConfig.default().with_goal_mode(True),
        ):
            events.append(ev)
            if ev.get("type") == "token":
                text += ev.get("content") or ""
        return events, text.strip()

    events, assistant_text = asyncio.run(_run())

    assert chat_calls == 2
    assert not any(ev.get("code") == "EMPTY_RESPONSE" for ev in events)
    assert len(assistant_text) >= 20
    assert "查阅" in assistant_text or "看代码" in assistant_text or "文字说明" in assistant_text
    assert "本轮目标" in assistant_text
