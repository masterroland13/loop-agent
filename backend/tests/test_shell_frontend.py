"""Desktop shell serves the installed page. The dev app stays API-only."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_window.host.frontend import mount_shell_frontend
from agent_window.main import app


def test_shell_serves_index_and_keeps_api(tmp_path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Loop Agent</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    shell = FastAPI()

    @shell.get("/api/workspace")
    def workspace():
        return {"configured": False, "root": None}

    assert mount_shell_frontend(shell, dist) is True
    client = TestClient(shell)
    page = client.get("/")
    assert page.status_code == 200
    assert "Loop Agent" in page.text
    assert "agent window" not in page.text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log(1)" in asset.text
    icon = client.get("/favicon.svg")
    assert icon.status_code == 200
    assert "<svg" in icon.text
    api = client.get("/api/workspace")
    assert api.status_code == 200
    assert api.json()["configured"] is False
    assert api.json()["root"] is None
    missing = client.get("/assets/nope.js")
    assert missing.status_code == 404


def test_dev_app_does_not_serve_the_shell_page() -> None:
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 404
    assert "Loop Agent" not in page.text
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert isinstance(body["provider_available"], bool)
