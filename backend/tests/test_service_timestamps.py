"""Service/API timestamps use timezone-aware UTC instead of datetime.utcnow()."""

from __future__ import annotations

import re
import warnings
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.audit import emit_audit
from agent_window.services.storage import (
    add_message,
    append_message_to_markdown,
    create_session,
    get_session_path,
    set_session_leaf,
    update_session_title,
)
from agent_window.services.turn_trace import TurnTraceWriter


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    db = get_sessionmaker()()
    try:
        yield SimpleNamespace(db=db, data=data)
    finally:
        db.close()
        models._engine = None
        models._SessionLocal = None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _assert_utc_now_semantics(value: datetime, *, before: datetime, after: datetime) -> None:
    assert value is not None
    if value.tzinfo is not None:
        assert value.utcoffset() == timedelta(0)
        assert value.utcoffset() != timedelta(hours=8)
    aware = _as_utc(value)
    assert before - timedelta(seconds=2) <= aware <= after + timedelta(seconds=2)
    assert aware.year != 2020
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    naive_value = aware.replace(tzinfo=None)
    assert abs((naive_now - naive_value).total_seconds()) < 5


def _parse_markdown_updated_at(text: str) -> datetime:
    match = re.search(r"^updated_at:\s*(.+)$", text, re.MULTILINE)
    assert match is not None
    parsed = datetime.fromisoformat(match.group(1).strip())
    assert parsed != datetime(2020, 1, 1)
    return parsed


def test_create_session_id_is_utc_wall_clock(db_env) -> None:
    db = db_env.db
    before = datetime.now(timezone.utc).replace(microsecond=0)
    session = create_session(db, title="utc-id")
    after = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)

    assert re.fullmatch(r"\d{8}-\d{6}", session.id)
    parsed = datetime.strptime(session.id, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    assert before - timedelta(seconds=2) <= parsed <= after + timedelta(seconds=2)
    assert session.title == "utc-id"
    assert session.title != "新对话"
    assert session.id != "untitled"


def test_markdown_timestamps_are_utc_now(db_env) -> None:
    db = db_env.db
    session = create_session(db, title="md-utc")
    before = datetime.now(timezone.utc)
    message = add_message(db, session, Role.USER, "hello", 1)
    after = datetime.now(timezone.utc)

    md_path = get_session_path(session) / "session.md"
    text = md_path.read_text(encoding="utf-8")
    header_at = _parse_markdown_updated_at(text)
    _assert_utc_now_semantics(header_at, before=before, after=after)
    assert "hello" in text
    assert "goodbye" not in text
    assert message.content == "hello"

    fallback_before = datetime.now(timezone.utc)
    message.created_at = None
    append_message_to_markdown(session, message)
    fallback_after = datetime.now(timezone.utc)
    updated = (get_session_path(session) / "session.md").read_text(encoding="utf-8")
    stamps = re.findall(r" at ([^\n]+)", updated)
    assert stamps
    fallback = datetime.fromisoformat(stamps[-1].strip())
    _assert_utc_now_semantics(fallback, before=fallback_before, after=fallback_after)
    assert fallback != datetime(2020, 1, 1)


def test_storage_updated_at_assignments_are_utc_now(db_env) -> None:
    db = db_env.db
    session = create_session(db, title="before")
    db.refresh(session)
    first = _as_utc(session.updated_at)

    before = datetime.now(timezone.utc)
    update_session_title(db, session, "after")
    after = datetime.now(timezone.utc)
    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert _as_utc(session.updated_at) >= first
    assert session.title == "after"
    assert session.title != "before"

    before = datetime.now(timezone.utc)
    message = add_message(db, session, Role.USER, "ping", 1)
    after = datetime.now(timezone.utc)
    db.refresh(session)
    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert message.role == Role.USER
    assert message.role != Role.ASSISTANT

    before = datetime.now(timezone.utc)
    set_session_leaf(db, session, message.id)
    after = datetime.now(timezone.utc)
    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert session.leaf_id == message.id
    assert session.leaf_id != "missing"


def test_emit_audit_created_at_is_utc_now(db_env) -> None:
    db = db_env.db
    before = datetime.now(timezone.utc)
    event = emit_audit(db, "turn.complete", payload={"ok": True}, session_id="sess-utc")
    after = datetime.now(timezone.utc)

    _assert_utc_now_semantics(event.created_at, before=before, after=after)
    assert event.event_type == "turn.complete"
    assert event.event_type != "patch.apply"
    assert event.session_id == "sess-utc"
    assert event.session_id != "other"


def test_turn_trace_finalize_updated_at_is_utc_now(db_env) -> None:
    db = db_env.db
    session = create_session(db, title="trace-utc")
    writer = TurnTraceWriter.create_placeholder(db, session, sequence=2)
    first = _as_utc(session.updated_at)

    before = datetime.now(timezone.utc)
    writer.finalize(summary="done", content="hello")
    after = datetime.now(timezone.utc)
    db.refresh(session)

    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert _as_utc(session.updated_at) >= first
    assert writer.assistant.content == "hello"
    assert writer.assistant.content != "goodbye"

    before = datetime.now(timezone.utc)
    writer.finalize_interrupted(code="TURN_CANCELLED", message="stopped")
    after = datetime.now(timezone.utc)
    db.refresh(session)
    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert "turn_cancelled" in (writer.assistant.summary or "")
    assert "turn_failed" not in (writer.assistant.summary or "")


def test_patch_session_updated_at_is_utc_now(db_env) -> None:
    from agent_window.main import app

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        client = TestClient(app)
        created = client.post("/api/sessions", json={"title": "api-utc"})
        assert created.status_code == 200
        sid = created.json()["id"]
        first = datetime.fromisoformat(created.json()["updated_at"])

        before = datetime.now(timezone.utc)
        locked = client.patch(f"/api/sessions/{sid}", json={"title_locked": True})
        after = datetime.now(timezone.utc)
        assert locked.status_code == 200
        locked_at = datetime.fromisoformat(locked.json()["updated_at"])
        _assert_utc_now_semantics(locked_at, before=before, after=after)
        assert locked.json()["title_locked"] is True
        assert locked.json()["title_locked"] is not False
        assert _as_utc(locked_at) >= _as_utc(first)

        before = datetime.now(timezone.utc)
        retargeted = client.patch(f"/api/sessions/{sid}", json={"model_id": "utc-model"})
        after = datetime.now(timezone.utc)
        assert retargeted.status_code == 200
        model_at = datetime.fromisoformat(retargeted.json()["updated_at"])
        _assert_utc_now_semantics(model_at, before=before, after=after)
        assert retargeted.json()["model_id"] == "utc-model"
        assert retargeted.json()["model_id"] != "seed-model"
        assert _as_utc(model_at) >= _as_utc(locked_at)
        utcnow_warnings = [
            item
            for item in caught
            if "utcnow" in str(item.message).lower() or "utcfromtimestamp" in str(item.message).lower()
        ]
    assert utcnow_warnings == []


def test_service_paths_do_not_emit_naive_utcnow_warning(db_env) -> None:
    db = db_env.db
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        session = create_session(db, title="warn-utc")
        add_message(db, session, Role.USER, "x", 1)
        update_session_title(db, session, "warn-utc-2")
        emit_audit(db, "warn", payload={})
        writer = TurnTraceWriter.create_placeholder(db, session, sequence=2)
        writer.finalize(summary="ok", content="y")
        utcnow_warnings = [
            item
            for item in caught
            if "utcnow" in str(item.message).lower() or "utcfromtimestamp" in str(item.message).lower()
        ]
    assert utcnow_warnings == []
    assert session.title == "warn-utc-2"
    assert session.title != "warn-utc"
    assert writer.assistant.content == "y"
    assert writer.assistant.content != "x"
