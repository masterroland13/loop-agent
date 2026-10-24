"""C5: manual compact + context occupancy."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.storage import add_message, create_session, get_session


@pytest.fixture
def compact_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    notes = workspace / "notes.txt"
    notes.write_text("do-not-touch", encoding="utf-8")
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))
    monkeypatch.setattr(
        "agent_window.services.session_transcript.settings.app_data_dir",
        str(data),
    )
    monkeypatch.setattr(settings, "llm_base_url", "https://seed.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "seed-secret")
    monkeypatch.setattr(settings, "llm_model", "seed-model")

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()

    from agent_window.main import app

    client = TestClient(app)
    db = get_sessionmaker()()
    session = create_session(db, title="compact", workspace_root=str(workspace))
    yield {
        "client": client,
        "db": db,
        "session": session,
        "workspace": workspace,
        "notes": notes,
    }
    db.close()


def _seed_history(db, session, *, n: int = 6) -> None:
    parent = None
    seq = 1
    for i in range(n):
        user = add_message(
            db,
            session,
            Role.USER,
            f"第{i}轮请看 auth.py 与登录 " + ("背景" * 40),
            seq,
            parent_id=parent,
        )
        seq += 1
        asst = add_message(
            db,
            session,
            Role.ASSISTANT,
            f"第{i}轮：读了 auth.py " + ("内容" * 40),
            seq,
            parent_id=user.id,
        )
        seq += 1
        parent = asst.id


def test_empty_session_compact_is_400(compact_env) -> None:
    sid = compact_env["session"].id
    r = compact_env["client"].post(f"/api/sessions/{sid}/compact", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_SESSION"
    assert compact_env["notes"].read_text(encoding="utf-8") == "do-not-touch"


def test_occupancy_under_limit_then_drops_after_compact(compact_env) -> None:
    db = compact_env["db"]
    session = get_session(db, compact_env["session"].id)
    assert session is not None
    _seed_history(db, session, n=6)
    client = compact_env["client"]
    sid = session.id
    before = client.get(f"/api/sessions/{sid}/context").json()
    assert before["percent"] < 100
    assert before["tokens"] > 0
    assert before["context_limit"] >= 2048

    seen: list[str] = []

    async def fake_summarize(blob: str, profile_id=None) -> str:
        seen.append(blob)
        return (
            "## Goal\n保留 auth\n"
            "## Constraints\n（无）\n"
            "## Progress\n读了 auth.py\n"
            "## Key Decisions\n（无）\n"
            "## Next Steps\n继续 auth 校验\n"
            "## Critical Context\n- auth.py\n"
        )

    from agent_window.api import routes as routes_mod

    routes_mod._summarize_blob = fake_summarize  # type: ignore[method-assign]
    compact = client.post(
        f"/api/sessions/{sid}/compact",
        json={"focus": "只保留 auth"},
    )
    assert compact.status_code == 200, compact.text
    body = compact.json()
    assert body["compressed"] is True
    assert body["percent_after"] < body["percent_before"]
    assert body["tokens_after"] < body["tokens_before"]
    assert body["focus"] == "只保留 auth"
    assert seen
    assert "【Focus】" in seen[0]
    assert "auth" in seen[0].lower()

    after = client.get(f"/api/sessions/{sid}/context").json()
    assert after["percent"] < 100
    assert after["tokens"] == body["tokens_after"]

    messages = client.get(f"/api/sessions/{sid}/messages?view=active").json()
    types = [m.get("entry_type") for m in messages]
    assert "compaction_summary" in types
    active_blob = "\n".join(m.get("content") or "" for m in messages)
    assert "auth" in active_blob.lower()

    users = [m for m in messages if m.get("role") == "user" and m.get("entry_type") != "compaction_summary"]
    assert users, "C2: a real user original must remain on the active path"
    assert any("auth" in (m.get("content") or "").lower() for m in users)

    assert compact_env["notes"].read_text(encoding="utf-8") == "do-not-touch"
    assert not (compact_env["workspace"] / "transcript.jsonl").exists()


def test_compact_missing_session_is_404(compact_env) -> None:
    r = compact_env["client"].post("/api/sessions/does-not-exist/compact", json={})
    assert r.status_code == 404
    assert compact_env["notes"].read_text(encoding="utf-8") == "do-not-touch"


def test_compact_without_persist_is_400(compact_env, monkeypatch) -> None:
    db = compact_env["db"]
    session = get_session(db, compact_env["session"].id)
    assert session is not None
    _seed_history(db, session, n=6)

    async def fake_summarize(blob: str, profile_id=None) -> str:
        return (
            "## Goal\n保留 auth\n## Constraints\n（无）\n## Progress\n读了\n"
            "## Key Decisions\n（无）\n## Next Steps\n继续\n## Critical Context\n- auth.py\n"
        )

    from agent_window.api import routes as routes_mod

    routes_mod._summarize_blob = fake_summarize  # type: ignore[method-assign]
    monkeypatch.setattr(
        "agent_window.services.compaction_persist.persist_compaction_on_tree",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "agent_window.services.compaction_persist.persist_compaction_from_tree",
        lambda *a, **k: None,
    )
    r = compact_env["client"].post(f"/api/sessions/{session.id}/compact", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "COMPACT_NOT_PERSISTED"
    db.refresh(session)
    assert "compaction_summary" not in [m.entry_type for m in session.messages]
    assert compact_env["notes"].read_text(encoding="utf-8") == "do-not-touch"


def test_extractive_focus_biases_critical_and_next() -> None:
    from agent_window.services.compress import build_extractive_summary

    older = [
        {"role": "user", "content": "先改 styles.css 的颜色"},
        {"role": "assistant", "content": "改了样式"},
        {"role": "user", "content": "然后修 auth.py 登录校验"},
        {"role": "tool", "name": "read_file", "content": "auth.py ok"},
    ]
    text = build_extractive_summary(older, focus="只保留 auth")
    next_body = text.split("## Next Steps", 1)[1].split("##", 1)[0]
    crit = text.split("## Critical Context", 1)[1]
    assert "auth" in next_body.lower()
    assert "auth.py" in crit
    assert "优先保留" in next_body
    assert "styles.css" not in next_body
