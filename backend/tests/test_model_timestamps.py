"""SQLAlchemy Column timestamps use timezone-aware UTC callables."""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from agent_window.config import settings
from agent_window.models import AuditEvent, Message, Role, Session, get_sessionmaker, init_db


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))

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


def test_session_column_defaults_are_utc_now(db_env) -> None:
    db = db_env.db
    before = datetime.now(timezone.utc)
    session = Session(title="utc-session", data_path="users/x/sessions/utc-session")
    db.add(session)
    db.commit()
    db.refresh(session)
    after = datetime.now(timezone.utc)

    _assert_utc_now_semantics(session.created_at, before=before, after=after)
    _assert_utc_now_semantics(session.updated_at, before=before, after=after)
    assert session.title != "新对话"
    assert session.created_at is not None
    assert session.updated_at is not None


def test_message_column_default_is_utc_now(db_env) -> None:
    db = db_env.db
    session = Session(title="utc-msg", data_path="users/x/sessions/utc-msg")
    db.add(session)
    db.flush()
    before = datetime.now(timezone.utc)
    message = Message(session_id=session.id, role=Role.USER, content="hello", sequence=1)
    db.add(message)
    db.commit()
    db.refresh(message)
    after = datetime.now(timezone.utc)

    _assert_utc_now_semantics(message.created_at, before=before, after=after)
    assert message.content == "hello"
    assert message.content != "goodbye"
    assert message.created_at is not None


def test_audit_event_column_default_is_utc_now(db_env) -> None:
    db = db_env.db
    before = datetime.now(timezone.utc)
    event = AuditEvent(event_type="model.timestamp", payload="{}")
    db.add(event)
    db.commit()
    db.refresh(event)
    after = datetime.now(timezone.utc)

    _assert_utc_now_semantics(event.created_at, before=before, after=after)
    assert event.event_type == "model.timestamp"
    assert event.event_type != "turn.complete"
    assert event.created_at is not None


def test_session_updated_at_onupdate_advances(db_env) -> None:
    db = db_env.db
    session = Session(title="before", data_path="users/x/sessions/onupdate")
    db.add(session)
    db.commit()
    db.refresh(session)
    first = _as_utc(session.updated_at)

    session.title = "after"
    db.commit()
    db.refresh(session)
    second = _as_utc(session.updated_at)

    assert session.title == "after"
    assert session.title != "before"
    assert second >= first
    _assert_utc_now_semantics(
        session.updated_at,
        before=first,
        after=datetime.now(timezone.utc),
    )


def test_column_defaults_do_not_emit_naive_utcnow_warning(db_env) -> None:
    db = db_env.db
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        session = Session(title="warn", data_path="users/x/sessions/warn")
        db.add(session)
        db.flush()
        db.add(Message(session_id=session.id, role=Role.USER, content="x", sequence=1))
        db.add(AuditEvent(event_type="warn", payload="{}"))
        db.flush()
        session.title = "warn-2"
        db.commit()
        utcnow_warnings = [
            item
            for item in caught
            if "utcnow" in str(item.message).lower() or "utcfromtimestamp" in str(item.message).lower()
        ]
    assert utcnow_warnings == []
    assert session.title == "warn-2"
    assert session.title != "warn"
