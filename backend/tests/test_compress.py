"""M2 compress: preserve Turn Goal across auto_compress."""

from __future__ import annotations

import asyncio

from agent_window.agent.goal import GOAL_MARKER, inject_goal_into_messages
from agent_window.services.compress import (
    approx_messages_tokens,
    compress_messages_if_needed,
    messages_contain_goal,
)


def _long_history(*, n_pairs: int = 8) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "你是编码助手。"}]
    for i in range(n_pairs):
        msgs.append(
            {
                "role": "user",
                "content": f"第{i}轮：请详细解释一段很长的背景 " + ("背景" * 80),
            }
        )
        msgs.append(
            {
                "role": "assistant",
                "content": f"第{i}轮回复：" + ("内容" * 80),
            }
        )
    msgs.append(
        {
            "role": "user",
            "content": "backend 跑 pytest 报 ImportError: No module named 'agent_window'。请排查。",
        }
    )
    msgs.append({"role": "assistant", "content": "可能是 PYTHONPATH。建议设置 PYTHONPATH=src。"})
    msgs.append({"role": "user", "content": "好的，按你刚才的方向继续深挖，然后对照目标收工。"})
    return msgs


def test_compress_preserves_goal_in_system_block() -> None:
    goal = (
        "backend 跑 pytest 报 ImportError: No module named 'agent_window'。请排查。"
    )
    messages = _long_history()
    assert approx_messages_tokens(messages) > 200

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=None,
            preserve_goal=goal,
        )

    out, compressed = asyncio.run(_run())
    assert compressed is True
    assert messages_contain_goal(out, goal)
    goal_blocks = [
        m
        for m in out
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and str(m["content"]).startswith(GOAL_MARKER)
    ]
    assert len(goal_blocks) == 1
    assert "ImportError" in goal_blocks[0]["content"]
    assert "agent_window" in goal_blocks[0]["content"]


def test_compress_summary_header_pins_goal() -> None:
    goal = "修复 ImportError: No module named 'agent_window'"
    messages = _long_history()

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=goal,
        )

    out, compressed = asyncio.run(_run())
    assert compressed
    summary_msgs = [
        m
        for m in out
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and "压缩摘要" in m["content"]
    ]
    assert summary_msgs
    assert "本轮目标（压缩保留）" in summary_msgs[0]["content"]
    assert "ImportError" in summary_msgs[0]["content"]


def test_compress_without_goal_still_works() -> None:
    messages = _long_history()

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=None,
        )

    out, compressed = asyncio.run(_run())
    assert compressed
    assert not any(
        isinstance(m.get("content"), str) and str(m["content"]).startswith(GOAL_MARKER)
        for m in out
    )


def test_compress_summarize_receives_goal_hint() -> None:
    goal = "排查 ImportError agent_window"
    messages = _long_history()
    seen: list[str] = []

    async def fake_summarize(blob: str) -> str:
        seen.append(blob)
        return "历史：多次背景讨论后开始查 ImportError。"

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=fake_summarize,
            preserve_goal=goal,
        )

    out, compressed = asyncio.run(_run())
    assert compressed
    assert seen
    assert "【必须保留的本轮目标】" in seen[0]
    assert "ImportError" in seen[0]
    assert messages_contain_goal(out, goal)


def test_compress_noop_when_under_limit() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=10_000,
            preserve_goal="should not inject when not compressed",
        )

    out, compressed = asyncio.run(_run())
    assert compressed is False
    assert out == messages


def test_compress_replaces_stale_goal_block() -> None:
    goal = "新目标：修好 pytest ImportError"
    messages = inject_goal_into_messages(_long_history(), "旧目标：别的事")

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=goal,
        )

    out, compressed = asyncio.run(_run())
    assert compressed
    assert messages_contain_goal(out, goal)
    assert not messages_contain_goal(out, "旧目标：别的事")
    goal_blocks = [
        m
        for m in out
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and str(m["content"]).startswith(GOAL_MARKER)
    ]
    assert len(goal_blocks) == 1
