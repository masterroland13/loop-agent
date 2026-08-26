"""F9 Foundation dogfood — fixed two-turn script and pass/fail assertions.

Scenario (from agent-window-roadmap §0 accident):
  Turn 1 — user asks to explain an ImportError / pytest failure (no edits).
  Turn 2 — user says 「好的」/ agrees to dig deeper; Goal must inherit turn 1;
            agent uses tools, persists trace (F6), and closes against Goal (F1/F2).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

F9_TITLE = "F9 狗粮：解释报错 → 同意深挖 → 对照 Goal 收工"

F9_USER_TURN1 = (
    "backend 里跑 `python -m pytest tests/` 报 ImportError: No module named 'agent_window'。"
    "请解释可能原因，并给出排查步骤；先不要改任何文件。"
)

F9_USER_TURN2 = (
    "好的，按你刚才的方向继续深挖，用工具看 backend 目录结构和 PYTHONPATH 相关配置，"
    "然后对照目标收工。"
)

# Turn-1 intent markers — Goal after turn 2 should still reference the original ask.
F9_GOAL_MARKERS = (
    "ImportError",
    "agent_window",
    "pytest",
    "PYTHONPATH",
    "排查",
)

# Final assistant should read like a conclusion, not an empty or pure 「好的」 echo.
F9_CONCLUSION_MARKERS = (
    "对照目标",
    "收工",
    "结论",
    "原因",
    "PYTHONPATH",
    "PYTHONPATH=src",
    "排查",
    "backend",
)


def extract_f9_turn2_goal(prior_user_texts: Sequence[str] | None = None) -> str:
    from agent_window.agent.goal import extract_turn_goal

    priors = list(prior_user_texts) if prior_user_texts else [F9_USER_TURN1]
    return extract_turn_goal(F9_USER_TURN2, priors)


def goal_covers_f9_intent(goal: str) -> bool:
    """Turn-2 Goal should inherit turn-1 substance, not collapse to 「好的」."""
    g = (goal or "").strip()
    if not g or g == "好的":
        return False
    lower = g.lower()
    hits = sum(1 for marker in F9_GOAL_MARKERS if marker.lower() in lower)
    return hits >= 2


def assistant_has_conclusion(content: str, goal: str) -> bool:
    text = (content or "").strip()
    if len(text) < 48:
        return False
    if any(marker in text for marker in F9_CONCLUSION_MARKERS):
        return True
    # At least one meaningful token from Goal appears in the answer.
    tokens = [t for t in re.split(r"[\s，。；、：]+", goal) if len(t) >= 4]
    return any(t in text for t in tokens[:6])


def trace_has_tool_activity(events: Iterable[Mapping[str, Any]], *, min_results: int = 1) -> bool:
    results = [e for e in events if e.get("type") == "tool_result"]
    return len(results) >= min_results


def events_include_turn_goal(events: Iterable[Mapping[str, Any]], goal: str) -> bool:
    for ev in events:
        if ev.get("type") == "turn_goal" and (ev.get("goal") or "").strip() == goal.strip():
            return True
    return False


def assert_f9_turn2_outcome(
    events: Sequence[Mapping[str, Any]],
    assistant_content: str,
    goal: str,
) -> None:
    """Raise AssertionError when F9 turn-2 expectations fail (for tests + manual runners)."""
    assert goal_covers_f9_intent(goal), f"Goal lost turn-1 intent: {goal!r}"
    assert events_include_turn_goal(events, goal), "missing turn_goal SSE/event"
    assert trace_has_tool_activity(events), "expected at least one tool_result in trace"
    assert assistant_has_conclusion(assistant_content, goal), (
        "assistant reply too short or missing goal-aligned conclusion"
    )
