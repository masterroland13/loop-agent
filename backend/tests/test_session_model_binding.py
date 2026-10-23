"""New sessions copy the active model profile; PATCH can retarget one chat."""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import init_db
import agent_window.services.model_registry as registry


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


def test_new_session_copies_active_profile_not_a_later_active(session_env) -> None:
    client = session_env.client
    seeded = registry.list_profiles_public()
    active_id = seeded["active_id"]
    created = client.post("/api/sessions", json={"title": "bound"}).json()
    assert created["profile_id"] == active_id
    assert created["model_id"] == "seed-model"
    assert created["profile_id"] != ""

    other = registry.create_profile(
        label="Later",
        base_url="https://later.example/v1",
        api_key="later-key",
        model_id="later-model",
        activate=True,
    )
    again = client.get(f"/api/sessions/{created['id']}").json()
    assert again["profile_id"] == active_id
    assert again["model_id"] == "seed-model"
    assert again["profile_id"] != other["id"]
    assert "later-key" not in str(again)


def test_patch_model_keeps_profile_until_profile_sent(session_env) -> None:
    client = session_env.client
    created = client.post("/api/sessions", json={"title": "pick"}).json()
    original = created["profile_id"]
    patched = client.patch(
        f"/api/sessions/{created['id']}",
        json={"model_id": "custom-on-router"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["model_id"] == "custom-on-router"
    assert body["profile_id"] == original
    assert body["model_id"] != "seed-model"

    missing = client.patch(
        f"/api/sessions/{created['id']}",
        json={"profile_id": "does-not-exist"},
    )
    assert missing.status_code == 400
    still = client.get(f"/api/sessions/{created['id']}").json()
    assert still["profile_id"] == original
    assert still["profile_id"] != "does-not-exist"


def test_migrate_adds_binding_columns_on_an_old_sessions_table(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    db_path = data / "agent_window.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255))")
    conn.execute("INSERT INTO sessions (id, title) VALUES ('old', 'legacy')")
    conn.commit()
    conn.close()

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    models._migrate_sessions_model_binding()
    models._migrate_sessions_model_binding()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(sessions)")]
    row = conn.execute("SELECT profile_id, model_id FROM sessions WHERE id = 'old'").fetchone()
    conn.close()
    assert cols.count("profile_id") == 1
    assert cols.count("model_id") == 1
    assert row == (None, None)


def test_bind_legacy_row_uses_active_and_disabled_profile_is_persisted(session_env) -> None:
    from agent_window.api.routes import _bind_turn_model
    from agent_window.models import get_sessionmaker
    from agent_window.services.storage import get_session

    client = session_env.client
    seeded = registry.list_profiles_public()
    active_id = seeded["active_id"]
    created = client.post("/api/sessions", json={"title": "legacy"}).json()
    cleared = client.patch(
        f"/api/sessions/{created['id']}",
        json={"profile_id": "", "model_id": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["profile_id"] is None
    assert cleared.json()["model_id"] is None

    db = get_sessionmaker()()
    session = get_session(db, created["id"])
    model, fallback, pid = _bind_turn_model(session, "from-request", db)
    assert fallback is False
    assert pid == active_id
    assert model == "from-request"
    assert model != "seed-model"
    again = client.get(f"/api/sessions/{created['id']}").json()
    assert again["profile_id"] is None
    assert again["model_id"] is None

    other = registry.create_profile(
        label="Other",
        base_url="https://other.example/v1",
        api_key="other-key",
        model_id="other-model",
        activate=False,
    )
    client.patch(
        f"/api/sessions/{created['id']}",
        json={"profile_id": other["id"], "model_id": "custom-on-other"},
    )
    registry.update_profile(other["id"], {"enabled": False})
    db.expire_all()
    session = get_session(db, created["id"])
    model, fallback, pid = _bind_turn_model(session, "custom-on-other", db)
    db.close()
    assert fallback is True
    assert pid == active_id
    assert model == "seed-model"
    assert model != "custom-on-other"
    assert "other-key" not in model
    stored = client.get(f"/api/sessions/{created['id']}").json()
    assert stored["profile_id"] == active_id
    assert stored["model_id"] == "seed-model"
    assert stored["profile_id"] != other["id"]


def test_send_gate_follows_the_session_profile(session_env, monkeypatch) -> None:
    client = session_env.client
    seeded = registry.list_profiles_public()
    active_id = seeded["active_id"]
    created = client.post("/api/sessions", json={"title": "gate"}).json()
    keyed = registry.create_profile(
        label="Keyed",
        base_url="https://b.example/v1",
        api_key="key-b",
        model_id="model-b",
        activate=False,
    )
    empty = registry.create_profile(
        label="Empty",
        base_url="https://empty.example/v1",
        api_key="",
        model_id="empty-model",
        activate=True,
    )
    patched = client.patch(
        f"/api/sessions/{created['id']}",
        json={"profile_id": keyed["id"], "model_id": "model-b"},
    )
    assert patched.status_code == 200
    assert registry.list_profiles_public()["active_id"] == empty["id"]
    assert settings.llm_api_key == ""

    called: list[str] = []

    async def fake_loop(*_args, **kwargs):
        called.append(str(kwargs.get("model") or ""))
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)
    with client.stream(
        "POST",
        f"/api/sessions/{created['id']}/messages",
        json={"content": "hi", "model": "model-b"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.status_code != 503
        for _ in resp.iter_bytes():
            pass
    assert called == ["model-b"]
    assert settings.llm_base_url != "https://b.example/v1"
    assert settings.llm_api_key == ""

    registry.set_active(active_id)
    client.patch(
        f"/api/sessions/{created['id']}",
        json={"profile_id": empty["id"], "model_id": "empty-model"},
    )
    called.clear()
    refused = client.post(
        f"/api/sessions/{created['id']}/messages",
        json={"content": "no-key"},
    )
    assert refused.status_code == 503
    assert called == []
    stayed = client.get(f"/api/sessions/{created['id']}").json()
    assert stayed["profile_id"] == empty["id"]
    assert stayed["profile_id"] != active_id


def _meta_events(body: str) -> list[dict]:
    found: list[dict] = []
    for block in body.split("\n\n"):
        if "event: meta" not in block:
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                found.append(json.loads(line[6:]))
    return found


def test_fallback_meta_names_the_profile_written_back(session_env, monkeypatch) -> None:
    client = session_env.client
    created = client.post("/api/sessions", json={}).json()
    stale_id = created["profile_id"]
    spare = registry.create_profile(
        label="Spare",
        base_url="https://spare.example/v1",
        api_key="spare-key",
        model_id="spare-model",
        activate=True,
    )
    registry.update_profile(stale_id, {"enabled": False})

    async def fake_loop(*_args, **_kwargs):
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)
    with client.stream(
        "POST",
        f"/api/sessions/{created['id']}/messages",
        json={"content": "hi"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    meta = _meta_events(body)
    assert meta
    assert meta[0].get("model_fallback") is True
    assert meta[0].get("profile_id") == spare["id"]
    assert meta[0].get("profile_id") != stale_id
    assert meta[0].get("model") == "spare-model"
    saved = client.get(f"/api/sessions/{created['id']}").json()
    assert saved["profile_id"] == spare["id"]
    assert saved["model_id"] == "spare-model"

    with client.stream(
        "POST",
        f"/api/sessions/{created['id']}/messages",
        json={"content": "again"},
    ) as resp:
        assert resp.status_code == 200
        calm = "".join(resp.iter_text())
    calm_meta = _meta_events(calm)
    assert calm_meta
    assert calm_meta[0].get("model_fallback") is not True
    assert "profile_id" not in calm_meta[0]


def test_manual_title_locks_and_plain_title_patch_does_not(session_env) -> None:
    client = session_env.client
    created = client.post("/api/sessions", json={"title": "新对话"}).json()
    assert created["title_locked"] is False

    auto = client.patch(f"/api/sessions/{created['id']}", json={"title": "只回复一个字：好"})
    assert auto.status_code == 200
    assert auto.json()["title"] == "只回复一个字：好"
    assert auto.json()["title_locked"] is False

    locked = client.patch(
        f"/api/sessions/{created['id']}",
        json={"title": "探针甲", "title_locked": True},
    )
    assert locked.status_code == 200
    assert locked.json()["title"] == "探针甲"
    assert locked.json()["title_locked"] is True

    follow = client.patch(f"/api/sessions/{created['id']}", json={"title": "后来的指令"})
    assert follow.status_code == 200
    assert follow.json()["title"] == "后来的指令"
    assert follow.json()["title_locked"] is True

    unlock = client.patch(f"/api/sessions/{created['id']}", json={"title_locked": False})
    assert unlock.status_code == 200
    assert unlock.json()["title_locked"] is True
    assert unlock.json()["title_locked"] is not False


def test_title_lock_migration_marks_custom_names(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    db_path = data / "agent_window.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255))")
    conn.executemany(
        "INSERT INTO sessions (id, title) VALUES (?, ?)",
        [("a", "新对话"), ("b", "New Chat"), ("c", "我改的名字")],
    )
    conn.commit()
    conn.close()

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    models._migrate_sessions_title_locked()
    models._migrate_sessions_title_locked()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(sessions)")]
    rows = dict(conn.execute("SELECT id, title_locked FROM sessions"))
    conn.close()
    assert cols.count("title_locked") == 1
    assert rows["a"] == 0
    assert rows["b"] == 0
    assert rows["c"] == 1
    assert rows["c"] != 0
