"""First-run folder create: a This PC child dir, not a workspace bind."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db
from agent_window.services.workspace import (
    WorkspaceError,
    create_browse_directory,
    get_workspace_root,
)


@pytest.fixture
def mkdir_env(tmp_path, monkeypatch):
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

    yield SimpleNamespace(client=TestClient(app), data=data, home=tmp_path)


def test_create_child_then_bind_does_not_seed_workspace(mkdir_env) -> None:
    parent = mkdir_env.home / "desk"
    parent.mkdir()
    created = mkdir_env.client.post(
        "/api/workspace/mkdir",
        json={"parent": str(parent), "name": "notes"},
    )
    assert created.status_code == 200
    path = created.json()["path"]
    assert path.endswith("/notes")
    assert (parent / "notes").is_dir()
    assert not (mkdir_env.data / "workspace.json").exists()
    assert get_workspace_root() is None

    bound = mkdir_env.client.put("/api/workspace", json={"root": path})
    assert bound.status_code == 200
    body = bound.json()
    assert body["configured"] is True
    assert body["root"] == path
    assert body["name"] == "notes"
    assert "agent window" not in path


def test_rejects_parent_escape_and_nested_name(mkdir_env) -> None:
    parent = mkdir_env.home / "desk"
    parent.mkdir()
    escaped = mkdir_env.client.post(
        "/api/workspace/mkdir",
        json={"parent": str(parent), "name": "../escape"},
    )
    nested = mkdir_env.client.post(
        "/api/workspace/mkdir",
        json={"parent": str(parent), "name": "a/b"},
    )
    dotted = mkdir_env.client.post(
        "/api/workspace/mkdir",
        json={"parent": str(parent), "name": ".."},
    )
    assert escaped.status_code == 400
    assert nested.status_code == 400
    assert dotted.status_code == 400
    assert not (mkdir_env.home / "escape").exists()
    assert not (parent / "a").exists()
    assert not (parent / "b").exists()
    assert get_workspace_root() is None
    assert not (mkdir_env.data / "workspace.json").exists()


def test_existing_directory_is_returned_again(tmp_path) -> None:
    parent = tmp_path / "desk"
    parent.mkdir()
    (parent / "notes").mkdir()
    first = create_browse_directory(str(parent), "notes")
    second = create_browse_directory(str(parent), "notes")
    assert first == second
    assert first.is_dir()
    with pytest.raises(WorkspaceError) as blocked:
        create_browse_directory(str(parent), "notes/other")
    assert blocked.value.code == "INVALID_NAME"
    assert not (parent / "other").exists()
