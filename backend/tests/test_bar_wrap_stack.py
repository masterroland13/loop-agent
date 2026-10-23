"""Regression: bar wrap helpers are mirrored in src/utils/barWrapStack.ts (logic-only)."""


def single_row_content_width(shell_w: int, left: int, right: int) -> int:
    pad, gap = 20, 6
    return max(shell_w - pad - left - right - gap * 2, 80)


def bar_needs_wrap_stack(scroll_h: int, stacked: bool, has_nl: bool, min_h: int = 32) -> bool:
    if has_nl:
        return True
    if stacked:
        return scroll_h > min_h
    return scroll_h > min_h + 4


def test_single_row_width_reserves_tool_strip():
    w = single_row_content_width(400, 72, 160)
    assert w == 400 - 20 - 72 - 160 - 12
    assert w < 400 - 20


def test_wrap_decision_uses_narrow_measure_not_full_width():
    # One line at full width (32px) but two lines when tools share the row (48px).
    assert bar_needs_wrap_stack(32, False, False) is False
    assert bar_needs_wrap_stack(48, False, False) is True
    # Stacked: still two lines at narrow width → stay stacked.
    assert bar_needs_wrap_stack(48, True, False) is True
    # Back to one line at narrow width → collapse.
    assert bar_needs_wrap_stack(32, True, False) is False


def test_newline_forces_stacked():
    assert bar_needs_wrap_stack(32, False, True) is True
