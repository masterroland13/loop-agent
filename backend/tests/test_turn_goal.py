"""Turn Goal extract / inject helpers."""

from __future__ import annotations

import json

from agent_window.agent.goal import (
    GOAL_MARKER,
    clip_goal,
    extract_turn_goal,
    format_goal_block,
    goals_equal,
    inject_goal_into_messages,
    is_exploratory_filler,
    is_low_info_followup,
    previous_turn_goal_from_messages,
)
from agent_window.agent.turn_event import event_from_sse


def test_affirmation_inherits_prior_goal() -> None:
    goal = extract_turn_goal(
        "好的",
        prior_user_texts=["运行 python -m pytest tests/"],
    )
    assert "pytest" in goal
    assert goal != "好的"


def test_continuation_prefix_inherits_prior_goal() -> None:
    prior = (
        "backend 里跑 pytest 报 ImportError: No module named 'agent_window'。"
        "请解释可能原因，先不要改文件。"
    )
    followup = (
        "好的，按你刚才的方向继续深挖，用工具看 backend 目录结构和 PYTHONPATH 相关配置，"
        "然后对照目标收工。"
    )
    goal = extract_turn_goal(followup, prior_user_texts=[prior])
    assert "ImportError" in goal or "agent_window" in goal
    assert "对照目标收工" not in goal


def test_substantive_message_becomes_goal() -> None:
    goal = extract_turn_goal("请列出 backend/src 下的 Python 文件", prior_user_texts=[])
    assert "Python" in goal or "backend" in goal


def test_long_filler_inherits_prior_goal() -> None:
    prior = "运行 python -m pytest tests/ 并解释 ImportError: No module named 'agent_window'"
    filler = (
        "StateGraph compiled with nodes: planner, executor, reviewer. "
        "Channel values include messages, scratchpad, tool_outputs. "
        "RunnableConfig tags=['langgraph', 'debug'] checkpoint_ns='' thread_id='abc'. "
        "Last event: on_chain_end output={'messages': [...]} metadata={'langgraph_step': 3}"
    )
    assert is_exploratory_filler(filler)
    goal = extract_turn_goal(filler, prior_user_texts=[prior])
    assert "pytest" in goal or "ImportError" in goal
    assert "StateGraph" not in goal
    assert "LangGraph" not in goal.lower()


def test_short_clear_rewrite_changes_goal() -> None:
    prior = "运行 python -m pytest tests/ 并解释 ImportError"
    rewrite = "请改 focus 到只跑 test_goal.py"
    goal = extract_turn_goal(rewrite, prior_user_texts=[prior])
    assert "test_goal" in goal
    assert goal != clip_goal(prior)


def test_low_info_followup_detection() -> None:
    assert is_low_info_followup("好的")
    assert is_low_info_followup("continue")
    assert not is_low_info_followup("请修复 test_checkpoint.py 里的断言")


def test_clip_goal_truncates_long_text() -> None:
    long_text = "x" * 500
    clipped = clip_goal(long_text)
    assert len(clipped) <= 240
    assert clipped.endswith("…")


def test_inject_goal_into_messages_inserts_system_block() -> None:
    messages = [{"role": "user", "content": "hello"}]
    out = inject_goal_into_messages(messages, "do the thing")
    assert out[0]["role"] == "system"
    assert GOAL_MARKER in out[0]["content"]
    assert "do the thing" in out[0]["content"]


def test_format_goal_block_contains_marker() -> None:
    block = format_goal_block("finish task")
    assert block.startswith(GOAL_MARKER)
    assert "finish task" in block


class _Msg:
    def __init__(self, role: str, *, summary: str = "", trace: str | None = None) -> None:
        self.role = role
        self.summary = summary
        self.trace = trace
        self.content = ""


def test_previous_turn_goal_from_summary() -> None:
    summary = json.dumps(
        {"type": "turn_meta", "goal": "修复 ImportError", "model": "x"},
        ensure_ascii=False,
    )
    msgs = [
        _Msg("user"),
        _Msg("assistant", summary=summary),
        _Msg("user"),
    ]
    assert previous_turn_goal_from_messages(msgs) == "修复 ImportError"


def test_previous_turn_goal_from_trace_when_summary_empty() -> None:
    trace = json.dumps(
        [{"type": "turn_goal", "goal": "列出 backend/src", "summary": "列出 backend/src"}],
        ensure_ascii=False,
    )
    msgs = [_Msg("assistant", summary="", trace=trace)]
    assert "backend" in (previous_turn_goal_from_messages(msgs) or "")


def test_goals_equal_clips_and_avoids_false_positive() -> None:
    assert goals_equal("跑 pytest", "跑 pytest")
    assert goals_equal("  跑 pytest  ", "跑 pytest")
    assert not goals_equal("跑 pytest", "改文档")
    assert not goals_equal(None, "跑 pytest")


def test_event_from_sse_turn_goal_includes_previous_goal() -> None:
    ev = event_from_sse(
        {
            "type": "turn_goal",
            "goal": "新目标",
            "previous_goal": "旧目标",
        }
    )
    assert ev is not None
    assert ev["goal"] == "新目标"
    assert ev["previous_goal"] == "旧目标"
    same = event_from_sse(
        {"type": "turn_goal", "goal": "同一目标", "previous_goal": "同一目标"}
    )
    assert same is not None
    assert "previous_goal" not in same
