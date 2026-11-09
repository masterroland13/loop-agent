"""Response models still accept ORM-style attribute objects."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent_window.schemas import MessageResponse, SessionResponse


def test_session_response_from_attributes() -> None:
    created = datetime(2026, 1, 1, 12, 0, 0)
    updated = datetime(2026, 1, 2, 12, 0, 0)
    obj = SimpleNamespace(
        id="sid-1",
        title="from-attrs",
        created_at=created,
        updated_at=updated,
        workspace_root="/tmp/ws",
        goal_mode=True,
        pinned_goal="do it",
        leaf_id="leaf-1",
        profile_id="p1",
        model_id="m1",
        title_locked=True,
        last_prompt_at=created,
    )
    resp = SessionResponse.model_validate(obj)
    assert resp.id == "sid-1"
    assert resp.title == "from-attrs"
    assert resp.goal_mode is True
    assert resp.workspace_root == "/tmp/ws"
    assert resp.title != "新对话"
    assert resp.goal_mode is not False


def test_message_response_from_attributes() -> None:
    created = datetime(2026, 1, 1, 12, 0, 0)
    obj = SimpleNamespace(
        id="mid-1",
        role="assistant",
        content="hello",
        sequence=2,
        is_favorite=True,
        summary=None,
        trace=[],
        attachments=[],
        created_at=created,
        parent_id="pid-1",
        entry_type="message",
    )
    resp = MessageResponse.model_validate(obj)
    assert resp.id == "mid-1"
    assert resp.role == "assistant"
    assert resp.content == "hello"
    assert resp.is_favorite is True
    assert resp.parent_id == "pid-1"
    assert resp.role != "user"
    assert resp.is_favorite is not False


def test_session_response_rejects_incomplete_dict() -> None:
    with pytest.raises(ValidationError):
        SessionResponse.model_validate({"id": "only-id"})
    with pytest.raises(ValidationError):
        SessionResponse.model_validate({"title": "no-id"})
