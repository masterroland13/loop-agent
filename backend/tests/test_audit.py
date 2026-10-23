"""Audit list filters + session summaries for M6 replay UI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db


@pytest.fixture
def audit_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()

    from agent_window.main import app

    client = TestClient(app)
    yield SimpleNamespace(client=client, data=data)


def test_audit_emit_list_and_filters(audit_env) -> None:
    client = audit_env.client

    r1 = client.post(
        "/api/audit",
        json={"event_type": "turn.complete", "payload": {"ok": True}, "session_id": "sess-a"},
    )
    r2 = client.post(
        "/api/audit",
        json={"event_type": "patch.apply", "payload": {"path": "a.py"}, "session_id": "sess-a"},
    )
    r3 = client.post(
        "/api/audit",
        json={"event_type": "turn.complete", "payload": {"ok": False}, "session_id": "sess-b"},
    )
    r4 = client.post(
        "/api/audit",
        json={"event_type": "settings.update", "payload": {"key": "x"}},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 200
    assert r4.status_code == 200
    assert r1.json()["session_id"] == "sess-a"
    assert "payload" in r1.json()
    assert r4.json().get("session_id") in (None, "")

    all_events = client.get("/api/audit?limit=50").json()
    types = {e["event_type"] for e in all_events}
    assert "turn.complete" in types
    assert "patch.apply" in types
    assert "settings.update" in types
    assert len(all_events) >= 4

    sess_a = client.get("/api/audit?session_id=sess-a&limit=50").json()
    assert len(sess_a) >= 2
    assert all(e["session_id"] == "sess-a" for e in sess_a)
    assert any(e["event_type"] == "patch.apply" for e in sess_a)
    assert not any(e["session_id"] == "sess-b" for e in sess_a)

    turns = client.get("/api/audit?event_type=turn.&limit=50").json()
    assert len(turns) >= 2
    assert all(e["event_type"].startswith("turn.") for e in turns)
    assert not any(e["event_type"] == "patch.apply" for e in turns)

    exact = client.get("/api/audit?event_type=patch.apply&limit=50").json()
    assert len(exact) >= 1
    assert all(e["event_type"] == "patch.apply" for e in exact)
    assert not any(e["event_type"] == "turn.complete" for e in exact)


def test_audit_session_summaries(audit_env) -> None:
    client = audit_env.client
    client.post(
        "/api/audit",
        json={"event_type": "shell.run", "payload": {}, "session_id": "sum-1"},
    )
    client.post(
        "/api/audit",
        json={"event_type": "shell.run", "payload": {}, "session_id": "sum-1"},
    )
    client.post(
        "/api/audit",
        json={"event_type": "memory.write", "payload": {}, "session_id": "sum-2"},
    )
    client.post("/api/audit", json={"event_type": "orphan.event", "payload": {}})

    summaries = client.get("/api/audit/sessions?limit=50").json()
    by_id = {row["session_id"]: row for row in summaries}
    assert "sum-1" in by_id
    assert "sum-2" in by_id
    assert by_id["sum-1"]["event_count"] >= 2
    assert by_id["sum-2"]["event_count"] >= 1
    assert by_id["sum-1"]["last_at"] is not None
    assert "" not in by_id
    assert None not in by_id


def test_session_audit_requires_existing_session(audit_env) -> None:
    client = audit_env.client
    missing = client.get("/api/sessions/no-such-session/audit")
    assert missing.status_code == 404
    assert missing.status_code != 200

    created = client.post("/api/sessions", json={"title": "audit-sess"})
    assert created.status_code == 200
    sid = created.json()["id"]
    client.post(
        "/api/audit",
        json={"event_type": "turn.complete", "payload": {"n": 1}, "session_id": sid},
    )
    listed = client.get(f"/api/sessions/{sid}/audit?limit=20").json()
    assert len(listed) >= 1
    assert all(e["session_id"] == sid for e in listed)
    assert any(e["event_type"] == "turn.complete" for e in listed)
    assert not any(e["session_id"] != sid for e in listed)


def test_settings_update_audit_carries_session_id(audit_env) -> None:
    client = audit_env.client
    created = client.post("/api/sessions", json={"title": "settings-audit"})
    assert created.status_code == 200
    sid = created.json()["id"]

    resp = client.put(
        f"/api/settings?session_id={sid}",
        json={"max_tool_iters": 20},
    )
    assert resp.status_code == 200

    listed = client.get(f"/api/audit?session_id={sid}&event_type=settings.update&limit=10").json()
    assert len(listed) >= 1
    assert all(e["session_id"] == sid for e in listed)
    assert all(e["event_type"] == "settings.update" for e in listed)
    assert listed[0]["payload"].get("max_tool_iters") == 20
