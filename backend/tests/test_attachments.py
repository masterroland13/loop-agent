"""P1 real link attachments — upload, send refs, read_attachment tool."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db


@pytest.fixture
def att_env(tmp_path, monkeypatch):
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
    from agent_window.services.provider import provider

    monkeypatch.setattr(provider, "is_available", lambda: True)

    client = TestClient(app)
    sid = client.post("/api/sessions", json={"title": "att"}).json()["id"]
    yield SimpleNamespace(client=client, data=data, session_id=sid)


def test_upload_persists_meta_and_download_matches(att_env) -> None:
    client = att_env.client
    sid = att_env.session_id
    body = b"hello attachment world"
    r = client.post(
        f"/api/sessions/{sid}/attachments",
        files={"file": ("notes.txt", body, "text/plain")},
    )
    assert r.status_code == 200
    meta = r.json()
    assert meta["filename"] == "notes.txt"
    assert meta["size"] == len(body)
    assert meta["id"]
    assert sid in meta["url"]
    assert "hello attachment world" not in meta.get("url", "")

    disk = att_env.data
    metas = list(disk.rglob("*.meta.json"))
    assert len(metas) == 1
    stored = json.loads(metas[0].read_text(encoding="utf-8"))
    assert stored["id"] == meta["id"]
    assert stored["filename"] == "notes.txt"

    dl = client.get(f"/api/sessions/{sid}/attachments/{meta['id']}")
    assert dl.status_code == 200
    assert dl.content == body
    assert body.decode() not in json.dumps(meta)


def test_send_with_attachment_ids_stores_refs_not_body(att_env, monkeypatch) -> None:
    client = att_env.client
    sid = att_env.session_id
    secret = "UNIQUE_SECRET_BODY_SHOULD_NOT_INLINE_XYZ"
    up = client.post(
        f"/api/sessions/{sid}/attachments",
        files={"file": ("secret.txt", secret.encode(), "text/plain")},
    ).json()

    async def fake_loop(*_a, **_k):
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "请总结", "attachment_ids": [up["id"]]},
    ) as resp:
        assert resp.status_code == 200
        # drain SSE
        for _ in resp.iter_bytes():
            pass

    msgs = client.get(f"/api/sessions/{sid}/messages").json()
    user = next(m for m in msgs if m["role"] == "user")
    assert user["attachments"]
    assert user["attachments"][0]["id"] == up["id"]
    assert user["attachments"][0]["filename"] == "secret.txt"
    assert secret not in user["content"]
    assert up["id"] in user["content"]
    assert "secret.txt" in user["content"]
    assert "read_attachment" in user["content"]
    assert "[附件]" in user["content"]


def test_send_rejects_missing_attachment_id(att_env, monkeypatch) -> None:
    client = att_env.client
    sid = att_env.session_id

    async def fake_loop(*_a, **_k):
        if False:
            yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)

    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"content": "hi", "attachment_ids": ["deadbeefdead"]},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "ATTACHMENT_NOT_FOUND"


def test_upload_rejects_oversized(att_env) -> None:
    from agent_window.services.attachments import MAX_ATTACHMENT_BYTES

    client = att_env.client
    sid = att_env.session_id
    huge = b"x" * (MAX_ATTACHMENT_BYTES + 1)
    r = client.post(
        f"/api/sessions/{sid}/attachments",
        files={"file": ("big.txt", huge, "text/plain")},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "TOO_LARGE"


def test_read_attachment_tool_with_context(att_env) -> None:
    from agent_window.services.attachment_context import use_attachment_session
    from agent_window.tools.attachment_tools import read_attachment_tool

    client = att_env.client
    sid = att_env.session_id
    up = client.post(
        f"/api/sessions/{sid}/attachments",
        files={"file": ("a.txt", b"line1\nline2\n", "text/plain")},
    ).json()

    async def run():
        with use_attachment_session(sid):
            return await read_attachment_tool({"attachment_id": up["id"], "offset": 1, "limit": 10})

    raw = asyncio.run(run())
    data = json.loads(raw)
    assert "error" not in data
    assert "line1" in data["content"]
    assert data["filename"] == "a.txt"
    assert "NOT_TEXT" not in data.get("code", "")


def test_read_attachment_tool_without_context_errors() -> None:
    from agent_window.tools.attachment_tools import read_attachment_tool

    async def run():
        return await read_attachment_tool({"attachment_id": "anything"})

    raw = asyncio.run(run())
    data = json.loads(raw)
    assert data["code"] == "NO_SESSION_CONTEXT"
    assert "error" in data
    assert "session" in data["error"].lower() or "context" in data["error"].lower()
