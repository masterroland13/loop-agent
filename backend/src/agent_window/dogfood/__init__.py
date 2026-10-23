"""Foundation dogfood scripts (F9+)."""

from agent_window.dogfood.f9_scenario import (
    F9_TITLE,
    F9_USER_TURN1,
    F9_USER_TURN2,
    assert_f9_turn2_outcome,
    assistant_has_conclusion,
    extract_f9_turn2_goal,
    goal_covers_f9_intent,
    trace_has_tool_activity,
)

__all__ = [
    "F9_TITLE",
    "F9_USER_TURN1",
    "F9_USER_TURN2",
    "assert_f9_turn2_outcome",
    "assistant_has_conclusion",
    "extract_f9_turn2_goal",
    "goal_covers_f9_intent",
    "trace_has_tool_activity",
]
