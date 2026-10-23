"""Sidebar clock follows the latest user instruction, not later session writes."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.storage import add_message, get_session


@pytest.fixture
def session_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))
    monkeypatch.setattr(settings, "llm_base_url", "https://seed.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "seed-secret")
    monkeypatch.setattr(settings, "llm_model", "seed-model")

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()

    from agent_window.main import app

    client = TestClient(app)
    yield SimpleNamespace(client=client, data=data)


def _user_created_at(client: TestClient, session_id: str) -> str:
    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    users = [item for item in messages if item["role"] == "user" and item["entry_type"] == "message"]
    assert users
    assert not any(item["entry_type"] == "compaction_summary" for item in users)
    return users[-1]["created_at"]


def test_last_prompt_follows_user_message_and_ignores_reply_and_edits(session_env) -> None:
    client = session_env.client
    created = client.post("/api/sessions", json={"title": "新对话"}).json()
    assert created["last_prompt_at"] is None
    assert created["updated_at"]

    db = get_sessionmaker()()
    session = get_session(db, created["id"])
    assert session is not None
    add_message(db, session, Role.USER, "hello", 1)
    db.close()

    after_user = client.get(f"/api/sessions/{created['id']}").json()
    user_at = _user_created_at(client, created["id"])
    assert after_user["last_prompt_at"] == user_at
    assert after_user["last_prompt_at"] is not None

    raw = sqlite3.connect(session_env.data / "agent_window.db")
    raw.execute(
        "UPDATE sessions SET last_prompt_at = ? WHERE id = ?",
        ("2020-01-01 00:00:00", created["id"]),
    )
    raw.commit()
    raw.close()
    db = get_sessionmaker()()
    session = get_session(db, created["id"])
    assert session is not None
    assert session.last_prompt_at is not None
    assert session.last_prompt_at.year == 2020
    add_message(db, session, Role.ASSISTANT, "reply", 2)
    add_message(
        db,
        session,
        Role.USER,
        "summary",
        3,
        entry_type="compaction_summary",
    )
    db.close()

    after_reply = client.get(f"/api/sessions/{created['id']}").json()
    assert after_reply["last_prompt_at"].startswith("2020-01-01")
    assert after_reply["last_prompt_at"] != user_at

    renamed = client.patch(
        f"/api/sessions/{created['id']}",
        json={"title": "探针甲", "title_locked": True},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "探针甲"
    assert renamed.json()["last_prompt_at"].startswith("2020-01-01")

    retargeted = client.patch(
        f"/api/sessions/{created['id']}",
        json={"model_id": "custom-on-router"},
    )
    assert retargeted.status_code == 200
    assert retargeted.json()["model_id"] == "custom-on-router"
    assert retargeted.json()["last_prompt_at"].startswith("2020-01-01")

    db = get_sessionmaker()()
    session = get_session(db, created["id"])
    assert session is not None
    add_message(db, session, Role.USER, "again", 4)
    db.close()

    after_second = client.get(f"/api/sessions/{created['id']}").json()
    second_at = _user_created_at(client, created["id"])
    assert after_second["last_prompt_at"] == second_at
    assert not after_second["last_prompt_at"].startswith("2020-01-01")
    assert after_second["model_id"] == "custom-on-router"


def test_last_prompt_migration_uses_latest_user_message(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    db_path = data / "agent_window.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255), created_at DATETIME)"
    )
    conn.execute(
        "CREATE TABLE messages ("
        " id VARCHAR(36) PRIMARY KEY,"
        " session_id VARCHAR(36),"
        " role VARCHAR(32),"
        " entry_type VARCHAR(32),"
        " created_at DATETIME"
        " )"
    )
    conn.executemany(
        "INSERT INTO sessions (id, title, created_at) VALUES (?, ?, ?)",
        [("a", "有指令", "2024-01-01 00:00:00"), ("b", "空会话", "2024-06-01 00:00:00")],
    )
    conn.executemany(
        "INSERT INTO messages (id, session_id, role, entry_type, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("m1", "a", "USER", "message", "2024-05-01 08:00:00"),
            ("m2", "a", "ASSISTANT", "message", "2024-05-01 09:00:00"),
            ("m3", "a", "user", "compaction_summary", "2024-05-02 09:00:00"),
        ],
    )
    conn.commit()
    conn.close()

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    models._migrate_sessions_last_prompt_at()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(sessions)")]
    rows = dict(conn.execute("SELECT id, last_prompt_at FROM sessions"))
    conn.execute(
        "UPDATE sessions SET last_prompt_at = ? WHERE id = ?",
        ("1999-01-01 00:00:00", "a"),
    )
    conn.commit()
    conn.close()
    assert cols.count("last_prompt_at") == 1
    assert rows["a"] == "2024-05-01 08:00:00"
    assert rows["b"] is None
    assert rows["a"] != "2024-05-01 09:00:00"
    assert rows["a"] != "2024-05-02 09:00:00"

    models._migrate_sessions_last_prompt_at()
    conn = sqlite3.connect(db_path)
    again = dict(conn.execute("SELECT id, last_prompt_at FROM sessions"))
    conn.close()
    assert again["a"] == "1999-01-01 00:00:00"
    assert again["b"] is None
    assert again["a"] != "2024-05-01 08:00:00"
