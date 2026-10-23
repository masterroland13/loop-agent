"""API: USER.md vs MEMORY.md content endpoints must not share a path."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "app_data_dir", str(tmp_path))
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    from agent_window.services.memory import clear_memory_snapshot

    clear_memory_snapshot()
    from agent_window.main import app

    with TestClient(app) as c:
        yield c
    clear_memory_snapshot()


def test_memory_content_get_put_separate_files(client: TestClient) -> None:
    u = client.get("/api/memory/tracks/user/content")
    m = client.get("/api/memory/tracks/memory/content")
    assert u.status_code == 200
    assert m.status_code == 200
    uj, mj = u.json(), m.json()
    assert uj["target"] == "user"
    assert mj["target"] == "memory"
    assert uj["path"].endswith("USER.md")
    assert mj["path"].endswith("MEMORY.md")
    assert uj["path"] != mj["path"]
    assert Path(mj["path"]).name == "MEMORY.md"
    assert Path(uj["path"]).name == "USER.md"

    put_m = client.put(
        "/api/memory/tracks/memory/content",
        json={"content": "ONLY_IN_MEMORY\n", "target": "user"},  # path wins
    )
    assert put_m.status_code == 200
    assert put_m.json()["path"].endswith("MEMORY.md")
    assert put_m.json()["target"] == "memory"

    put_u = client.put(
        "/api/memory/tracks/user/content",
        json={"content": "ONLY_IN_USER\n", "target": "memory"},  # path wins
    )
    assert put_u.status_code == 200
    assert put_u.json()["path"].endswith("USER.md")

    again_u = client.get("/api/memory/tracks/user/content").json()
    again_m = client.get("/api/memory/tracks/memory/content").json()
    assert "ONLY_IN_USER" in again_u["content"]
    assert "ONLY_IN_MEMORY" not in again_u["content"]
    assert "ONLY_IN_MEMORY" in again_m["content"]
    assert "ONLY_IN_USER" not in again_m["content"]
    assert again_u["path"] != again_m["path"]

    # Legacy query API still separates tracks
    legacy_m = client.get("/api/memory/content", params={"target": "memory"}).json()
    assert legacy_m["path"].endswith("MEMORY.md")
    assert "ONLY_IN_MEMORY" in legacy_m["content"]
