"""F8: resolve_turn_goal + pin override + goal.change audit payload."""

from __future__ import annotations

import json
from types import SimpleNamespace

from agent_window.agent.goal import (
    GoalResolution,
    goal_change_audit_payload,
    normalize_pinned_goal,
    resolve_turn_goal,
)
from agent_window.core.goal_hooks import goal_change_audit_event, resolve_session_goal


def _asst(goal: str) -> SimpleNamespace:
    return SimpleNamespace(
        role="assistant",
        content="",
        summary=json.dumps({"type": "turn_meta", "goal": goal}),
        trace="[]",
    )


def test_resolve_goal_mode_off_returns_none() -> None:
    r = resolve_turn_goal(
        goal_mode=False,
        user_text="请修复 ImportError",
        history_messages=[],
        pinned_goal="被忽略的钉",
        audit_source="extract",
    )
    assert r.turn_goal is None
    assert r.changed is False
    assert r.changed is not True
    assert goal_change_audit_payload(r) is None


def test_resolve_uses_pinned_over_extract() -> None:
    r = resolve_turn_goal(
        goal_mode=True,
        user_text="请修复 ImportError 并跑 pytest",
        history_messages=[],
        pinned_goal="只跑前端 tsc",
        audit_source="extract",
    )
    assert r.turn_goal == "只跑前端 tsc"
    assert r.source == "pinned"
    assert r.source != "extract"
    assert r.changed is False


def test_resolve_extract_when_pin_empty() -> None:
    r = resolve_turn_goal(
        goal_mode=True,
        user_text="请列出 backend/src 下的 Python 文件",
        history_messages=[],
        pinned_goal="   ",
        audit_source="extract",
    )
    assert r.turn_goal is not None
    assert "列出" in (r.turn_goal or "") or "Python" in (r.turn_goal or "") or "backend" in (
        r.turn_goal or ""
    )
    assert r.source == "extract"
    assert r.source != "pinned"


def test_resolve_marks_change_and_audit_payload() -> None:
    hist = [_asst("修复 ImportError")]
    r = resolve_turn_goal(
        goal_mode=True,
        user_text="请改成只更新文档",
        history_messages=hist,
        pinned_goal=None,
        audit_source="regenerate",
    )
    assert r.changed is True
    assert r.previous_goal == "修复 ImportError"
    payload = goal_change_audit_payload(r)
    assert payload is not None
    assert payload["source"] == "regenerate"
    assert payload["goal"] == r.turn_goal
    assert payload["previous_goal"] == "修复 ImportError"
    # reverse: no payload when unchanged
    same = resolve_turn_goal(
        goal_mode=True,
        user_text="继续",
        history_messages=hist,
        pinned_goal="修复 ImportError",
        audit_source="extract",
    )
    assert same.changed is False
    assert goal_change_audit_payload(same) is None


def test_normalize_pinned_goal_clears_blank() -> None:
    assert normalize_pinned_goal("  ") is None
    assert normalize_pinned_goal(None) is None
    assert normalize_pinned_goal("跑 pytest") == "跑 pytest"
    assert normalize_pinned_goal("跑 pytest") is not None


def test_goal_hooks_reexport_matches_agent() -> None:
    r = resolve_session_goal(
        goal_mode=True,
        user_text="请跑 pytest",
        history_messages=[],
        pinned_goal="固定目标文案",
        audit_source="extract",
    )
    assert isinstance(r, GoalResolution)
    assert r.source == "pinned"
    assert goal_change_audit_event(r) is None
    assert r.turn_goal == "固定目标文案"
