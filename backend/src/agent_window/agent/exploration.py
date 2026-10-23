"""Exploration convergence: nudge the model after repeated list/read/grep tools."""

from __future__ import annotations

from typing import Optional

from agent_window.agent.goal import clip_goal

EXPLORATION_TOOLS = frozenset({"list_dir", "read_file", "grep", "read_attachment"})
EXPLORATION_CONVERGE_MARKER = "【探索收敛】"


def exploration_repeat_threshold_from_settings(raw: object, *, default: int = 6) -> int:
    """0 disables exploration convergence; else clamp 3–12."""
    try:
        n = int(raw if raw is not None else default)
    except (TypeError, ValueError):
        n = default
    if n <= 0:
        return 0
    return max(3, min(12, n))


def update_exploration_streak(
    prev_tool: Optional[str],
    prev_streak: int,
    tool_name: str,
) -> tuple[Optional[str], int]:
    """Track consecutive same exploration tool; reset on non-exploration or name change."""
    if tool_name not in EXPLORATION_TOOLS:
        return None, 0
    if tool_name == prev_tool:
        return tool_name, prev_streak + 1
    return tool_name, 1


def should_converge_exploration(streak: int, threshold: int) -> bool:
    return threshold > 0 and streak >= threshold


def format_exploration_converge_message(
    goal: Optional[str],
    tool_name: str,
    streak: int,
) -> str:
    g = clip_goal(goal or "")
    return (
        f"{EXPLORATION_CONVERGE_MARKER}\n"
        f"已连续 {streak} 次调用 `{tool_name}`。"
        f"对照本轮目标「{g}」，请先用 1–3 句话总结目前发现、主要阻塞（如有），"
        "以及下一步打算（换手段 / 向人求助 / 对照目标收工）。"
        "禁止再继续调用 list_dir、read_file、grep、read_attachment 等同类探索工具。"
        "说完后再换用其他工具或直接给出结论。"
    )
