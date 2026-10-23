"""Session hard-bind: workspace_root persisted and returned."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db


@pytest.fixture
def sess_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()

    from agent_window.main import app

    client = TestClient(app)
    yield SimpleNamespace(client=client, data=data)


def test_create_with_workspace_root_listed(sess_env) -> None:
    client = sess_env.client
    root = "/home/user/my-project"
    created = client.post(
        "/api/sessions",
        json={"title": "bound", "workspace_root": root},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "bound"
    assert body["workspace_root"] == root
    assert body.get("workspace_root") is not None

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == body["id"])
    assert match["workspace_root"] == root
    assert match["title"] == "bound"


def test_create_without_workspace_root_is_null(sess_env) -> None:
    client = sess_env.client
    created = client.post("/api/sessions", json={"title": "unbound"})
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "unbound"
    assert body["workspace_root"] is None
    assert "workspace_root" in body

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == body["id"])
    assert match["workspace_root"] is None
    assert match["title"] == "unbound"


def test_create_empty_string_workspace_root_is_null(sess_env) -> None:
    client = sess_env.client
    created = client.post(
        "/api/sessions",
        json={"title": "empty-root", "workspace_root": ""},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["workspace_root"] is None
    assert body["title"] == "empty-root"
    assert body.get("workspace_root") is None


def test_patch_bind_workspace_root(sess_env, tmp_path) -> None:
    client = sess_env.client
    created = client.post("/api/sessions", json={"title": "to-bind"}).json()
    sid = created["id"]
    root = str(tmp_path / "proj")
    (tmp_path / "proj").mkdir()

    patched = client.patch(
        f"/api/sessions/{sid}",
        json={"workspace_root": root},
    )
    assert patched.status_code == 200
    assert patched.json()["workspace_root"] == root

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == sid)
    assert match["workspace_root"] == root


def test_patch_bind_rejects_when_already_bound(sess_env, tmp_path) -> None:
    client = sess_env.client
    a = str(tmp_path / "a")
    b = str(tmp_path / "b")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    created = client.post(
        "/api/sessions",
        json={"title": "bound", "workspace_root": a},
    ).json()

    again = client.patch(
        f"/api/sessions/{created['id']}",
        json={"workspace_root": b},
    )
    assert again.status_code == 400
    assert created["workspace_root"] == a or client.get(f"/api/sessions/{created['id']}").json()["workspace_root"] == a


def test_patch_unbind_rejected(sess_env, tmp_path) -> None:
    client = sess_env.client
    root = str(tmp_path / "proj")
    (tmp_path / "proj").mkdir()
    created = client.post(
        "/api/sessions",
        json={"title": "bound", "workspace_root": root},
    ).json()

    cleared = client.patch(
        f"/api/sessions/{created['id']}",
        json={"workspace_root": None},
    )
    assert cleared.status_code == 400
