"""LoopConfig factories (A0): default, with_goal_mode, with_preset."""

from __future__ import annotations


def test_default_has_goal_mode_false_and_yolo() -> None:
    from agent_window.core.loop_config import LoopConfig, LoopPreset

    cfg = LoopConfig.default()
    assert cfg.goal_mode is False
    assert cfg.preset is LoopPreset.YOLO
    # reverse: default must not enable goal mode
    assert cfg.goal_mode is not True


def test_with_goal_mode_returns_new_does_not_mutate() -> None:
    from agent_window.core.loop_config import LoopConfig

    original = LoopConfig.default()
    enabled = original.with_goal_mode(True)
    assert enabled.goal_mode is True
    assert original.goal_mode is False
    assert enabled is not original
    # reverse: original must not flip to True
    assert original.goal_mode is not True


def test_with_preset_trusted_and_invalid_falls_back_to_yolo() -> None:
    from agent_window.core.loop_config import LoopConfig, LoopPreset

    cfg = LoopConfig.default().with_preset("trusted")
    assert cfg.preset is LoopPreset.TRUSTED
    assert cfg.preset is not LoopPreset.YOLO

    # A1c: invalid → YOLO (same as settings normalize), does not raise
    bad = LoopConfig.default().with_preset("not-a-real-preset")
    assert bad.preset is LoopPreset.YOLO
    assert bad.preset is not LoopPreset.TRUSTED
