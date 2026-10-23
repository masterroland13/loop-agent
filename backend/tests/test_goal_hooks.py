"""GoalModeHooks install/clear + behavior parity with A1a gates."""

from __future__ import annotations

from agent_window.core.goal_hooks import install_goal_hooks
from agent_window.core.loop_config import LoopConfig


def test_with_goal_mode_true_installs_hooks() -> None:
    cfg = LoopConfig.default().with_goal_mode(True)
    assert cfg.goal_mode is True
    assert cfg.on_turn_start is not None
    assert cfg.after_tool_call is not None
    assert cfg.after_tool_batch is not None
    # reverse
    assert LoopConfig.default().on_turn_start is None


def test_with_goal_mode_false_clears_hooks() -> None:
    on = LoopConfig.default().with_goal_mode(True)
    off = on.with_goal_mode(False)
    assert off.goal_mode is False
    assert off.on_turn_start is None
    assert off.after_tool_call is None
    assert off.after_tool_batch is None
    assert off.goal_mode is not True


def test_install_goal_hooks_idempotent_off() -> None:
    cfg = install_goal_hooks(LoopConfig(goal_mode=False))
    assert cfg.on_turn_start is None
    cfg2 = install_goal_hooks(LoopConfig(goal_mode=True))
    assert cfg2.on_turn_start is not None
    assert cfg2.after_tool_batch is not None
