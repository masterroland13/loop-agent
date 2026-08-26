"""Compress service: auto_compress=False short-circuits even when over limit."""

from __future__ import annotations

import asyncio

from agent_window.services.compress import (
    approx_messages_tokens,
    compress_messages_if_needed,
    messages_contain_goal,
)


def _long_history() -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "你是编码助手。"}]
    for i in range(8):
        msgs.append({"role": "user", "content": f"第{i}轮：" + ("背景" * 80)})
        msgs.append({"role": "assistant", "content": f"第{i}轮回复：" + ("内容" * 80)})
    msgs.append({"role": "user", "content": "请排查 pytest 报错。"})
    return msgs


def test_auto_compress_off_returns_messages_untouched() -> None:
    """关闭自动压缩时，即使消息明显超限也原样返回，且不注入目标块。"""
    goal = "不该被注入的目标：修好 pytest"
    messages = _long_history()
    assert approx_messages_tokens(messages) > 200  # 前置：确认确实超限

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=False,
            context_limit=200,
            preserve_goal=goal,
        )

    out, compressed = asyncio.run(_run())
    # 行为：不压缩、消息逐条原样返回
    assert compressed is False
    assert out == messages
    # 反向断言：不注入目标块、不生成摘要块
    assert not messages_contain_goal(out, goal)
    assert not any(
        m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and "压缩摘要" in m["content"]
        for m in out
    )


def test_auto_compress_on_same_input_does_compress() -> None:
    """正向对照：同样的输入开自动压缩就会压缩，证明前置超限条件真实有效。"""
    messages = _long_history()

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
        )

    out, compressed = asyncio.run(_run())
    assert compressed is True
    assert len(out) < len(messages)
    assert any(
        m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and "压缩摘要" in m["content"]
        for m in out
    )
