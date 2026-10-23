"""GET /api/sessions/{id} returns leaf_id and session fields."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_window.main import app


def test_get_session_by_id_includes_leaf_id() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"title": "get-me"}).json()
    sid = created["id"]
    assert created.get("leaf_id") is None or created.get("leaf_id") is not None

    resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sid
    assert body["title"] == "get-me"
    assert "leaf_id" in body
    assert "goal_mode" in body
    assert body["goal_mode"] is False
    # Must not be list endpoint shape
    assert isinstance(body, dict)
    assert not isinstance(body, list)


def test_get_session_404() -> None:
    client = TestClient(app)
    resp = client.get("/api/sessions/does-not-exist-zzzz")
    assert resp.status_code == 404
    assert resp.status_code != 405
