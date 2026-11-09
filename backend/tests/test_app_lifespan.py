"""App lifespan initializes the DB and restores pending approvals."""

from __future__ import annotations

import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.services.attachment_context import use_attachment_session
from agent_window.services.memory import _memories, create_memory_proposal
from agent_window.services.patches import _patches, create_patch_from_content
from agent_window.services.shell import _shells, create_shell_proposal
from agent_window.services.workspace import set_workspace_root


def test_lifespan_boots_db_and_restores_pending_approvals(
    tmp_path: Path, monkeypatch
) -> None:
    data = tmp_path / "data"
    ws = tmp_path / "ws"
    data.mkdir()
    ws.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    set_workspace_root(str(ws))

    with use_attachment_session("sess-boot"):
        patch = create_patch_from_content("restored.txt", "hello-lifespan\n")
        shell = create_shell_proposal(["pwd"])
        memory = create_memory_proposal("remember-lifespan", mode="replace", target="user")

    assert (data / "pending_patches.json").is_file()
    assert (data / "pending_shells.json").is_file()
    assert (data / "pending_memories.json").is_file()
    assert not (data / "agent_window.db").exists()

    _patches.clear()
    _shells.clear()
    _memories.clear()
    assert list(_patches) == []
    assert list(_shells) == []
    assert list(_memories) == []

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None

    from agent_window.main import app

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with TestClient(app) as client:
            health = client.get("/health")
            created = client.post("/api/sessions", json={"title": "lifespan-boot"})
            patches = client.get("/api/workspace/patches")
            shells = client.get("/api/workspace/shells")
            memories = client.get("/api/memory/proposals")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.status_code != 503
    assert created.status_code == 200
    assert created.json()["title"] == "lifespan-boot"
    assert created.json()["title"] != "新对话"
    assert (data / "agent_window.db").is_file()

    patch_ids = {item["id"] for item in patches.json()}
    assert patches.status_code == 200
    assert patch.id in patch_ids
    assert "missing-patch" not in patch_ids
    assert any(item["path"] == "restored.txt" for item in patches.json())
    assert all(item["path"] != "absent.txt" for item in patches.json())

    shell_ids = {item["id"] for item in shells.json()}
    assert shells.status_code == 200
    assert shell.id in shell_ids
    assert "missing-shell" not in shell_ids
    assert any(item["argv"] == ["pwd"] for item in shells.json())
    assert all(item["argv"] != ["rm", "-rf", "/"] for item in shells.json())

    memory_ids = {item["id"] for item in memories.json()}
    assert memories.status_code == 200
    assert memory.id in memory_ids
    assert "missing-memory" not in memory_ids
    assert any("remember-lifespan" in (item.get("preview") or item.get("content") or "") for item in memories.json())
    assert all("forget-this" not in (item.get("preview") or item.get("content") or "") for item in memories.json())

    on_event_warnings = [
        item
        for item in caught
        if "on_event" in str(item.message).lower()
        or "lifespan event handlers" in str(item.message).lower()
    ]
    assert on_event_warnings == []
