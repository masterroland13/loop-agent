"""A1b: session goal_mode persistence + chat path reads the flag."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db


@pytest.fixture
def goal_env(tmp_path, monkeypatch):
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
    monkeypatch.setattr(provider, "profile_is_ready", lambda _profile_id=None: True)

    client = TestClient(app)
    yield SimpleNamespace(client=client, data=data)


def test_new_session_goal_mode_defaults_false(goal_env) -> None:
    client = goal_env.client
    created = client.post("/api/sessions", json={"title": "fresh"})
    assert created.status_code == 200
    body = created.json()
    assert body["goal_mode"] is False
    assert body["goal_mode"] is not True
    assert body.get("pinned_goal") in (None, "")
    assert body["title"] == "fresh"

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == body["id"])
    assert match["goal_mode"] is False
    assert match["goal_mode"] is not True


def test_patch_pinned_goal_persists_and_clears(goal_env) -> None:
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "pin"}).json()["id"]

    set_pin = client.patch(f"/api/sessions/{sid}", json={"pinned_goal": "只跑 tsc"})
    assert set_pin.status_code == 200
    assert set_pin.json()["pinned_goal"] == "只跑 tsc"
    assert set_pin.json()["pinned_goal"] != "跑 pytest"

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == sid)
    assert match["pinned_goal"] == "只跑 tsc"

    cleared = client.patch(f"/api/sessions/{sid}", json={"pinned_goal": ""})
    assert cleared.status_code == 200
    assert cleared.json()["pinned_goal"] in (None, "")
    assert cleared.json()["pinned_goal"] != "只跑 tsc"

    # title-only patch keeps pin cleared / does not resurrect
    renamed = client.patch(f"/api/sessions/{sid}", json={"title": "pin2"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "pin2"
    assert renamed.json()["pinned_goal"] in (None, "")


def test_patch_goal_mode_true_then_false(goal_env) -> None:
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "toggle"}).json()["id"]

    on = client.patch(f"/api/sessions/{sid}", json={"goal_mode": True})
    assert on.status_code == 200
    assert on.json()["goal_mode"] is True
    assert on.json()["goal_mode"] is not False
    assert on.json()["title"] == "toggle"

    listed = client.get("/api/sessions").json()
    match = next(s for s in listed if s["id"] == sid)
    assert match["goal_mode"] is True
    assert match["goal_mode"] is not False

    off = client.patch(f"/api/sessions/{sid}", json={"goal_mode": False})
    assert off.status_code == 200
    assert off.json()["goal_mode"] is False
    assert off.json()["goal_mode"] is not True

    listed2 = client.get("/api/sessions").json()
    match2 = next(s for s in listed2 if s["id"] == sid)
    assert match2["goal_mode"] is False
    assert match2["goal_mode"] is not True


def test_patch_title_only_keeps_goal_mode(goal_env) -> None:
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "old"}).json()["id"]
    client.patch(f"/api/sessions/{sid}", json={"goal_mode": True})

    renamed = client.patch(f"/api/sessions/{sid}", json={"title": "new-title"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "new-title"
    assert renamed.json()["goal_mode"] is True
    assert renamed.json()["goal_mode"] is not False


def test_chat_stream_config_uses_session_goal_mode(goal_env, monkeypatch) -> None:
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "stream"}).json()["id"]
    captured: list[bool] = []

    async def fake_loop(*_a, **kwargs):
        cfg = kwargs.get("config")
        captured.append(bool(getattr(cfg, "goal_mode", False)))
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "hello off"},
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass

    assert captured == [False]
    assert captured[0] is not True

    client.patch(f"/api/sessions/{sid}", json={"goal_mode": True})
    captured.clear()

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "hello on"},
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass

    assert captured == [True]
    assert captured[0] is not False


def _parse_sse_events(raw: bytes) -> list[tuple[str, dict]]:
    text = raw.decode("utf-8", errors="replace")
    events: list[tuple[str, dict]] = []
    blocks = text.split("\n\n")
    for block in blocks:
        etype = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                etype = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not etype or not data_lines:
            continue
        import json

        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append((etype, payload))
    return events


def test_chat_meta_uses_pinned_goal_when_set(goal_env, monkeypatch) -> None:
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "pin-stream"}).json()["id"]

    async def fake_loop(*_a, **kwargs):
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)

    client.patch(f"/api/sessions/{sid}", json={"goal_mode": True, "pinned_goal": "只验证固定目标"})
    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "请修复完全不同的 ImportError"},
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())

    metas = [p for t, p in _parse_sse_events(body) if t == "meta"]
    assert metas
    assert metas[0].get("goal") == "只验证固定目标"
    assert "ImportError" not in (metas[0].get("goal") or "")


def test_chat_meta_omits_goal_when_goal_mode_off(goal_env, monkeypatch) -> None:
    """OFF: meta must not carry goal; ON: meta includes extracted goal."""
    client = goal_env.client
    sid = client.post("/api/sessions", json={"title": "meta-gate"}).json()["id"]

    async def fake_loop(*_a, **_kwargs):
        yield {"type": "token", "content": "reply"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "请列出 backend 目录"},
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())

    events = _parse_sse_events(body)
    metas = [p for t, p in events if t == "meta"]
    assert metas, "expected meta SSE"
    assert "goal" not in metas[0]
    assert metas[0].get("goal") is None
    turn_goals = [p for t, p in events if t == "turn_goal"]
    assert turn_goals == []

    client.patch(f"/api/sessions/{sid}", json={"goal_mode": True})
    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "请列出 src 目录"},
    ) as resp:
        assert resp.status_code == 200
        body_on = b"".join(resp.iter_bytes())

    metas_on = [p for t, p in _parse_sse_events(body_on) if t == "meta"]
    assert metas_on
    assert "goal" in metas_on[0]
    assert isinstance(metas_on[0]["goal"], str)
    assert len(metas_on[0]["goal"].strip()) > 0
    # reverse: ON must not omit goal
    assert metas_on[0].get("goal") is not None
