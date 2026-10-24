"""C4: search_session reads this session's JSONL + spill only."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.attachment_context import use_attachment_session
from agent_window.services.session_search import (
    SessionSearchError,
    search_session_records,
)
from agent_window.services.session_transcript import transcript_path
from agent_window.services.storage import (
    add_message,
    create_session,
    get_session_path,
    write_turn_blob,
)


GREP_PATH = "backend/src/agent_window/agent/loop.py"


@pytest.fixture
def search_env(tmp_path, monkeypatch):
    data = tmp_path / "app-data"
    data.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text(f"workspace should hide {GREP_PATH}", encoding="utf-8")
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))
    monkeypatch.setattr(
        "agent_window.services.session_transcript.settings.app_data_dir",
        str(data),
    )
    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="search-a", workspace_root=str(workspace))
        yield {
            "db": db,
            "session": session,
            "other_id": "foreign-session-id",
            "workspace": workspace,
            "data": data,
        }
    finally:
        db.close()


def test_search_finds_grep_path_in_transcript_not_workspace(search_env) -> None:
    session = search_env["session"]
    add_message(search_env["db"], session, Role.ASSISTANT, f"grep hit {GREP_PATH}", 1)
    found = search_session_records(session, "loop.py")
    blob = json.dumps(found, ensure_ascii=False)
    assert found["hit_count"] >= 1
    assert GREP_PATH in blob
    assert any(hit.get("source") == "transcript" for hit in found["hits"])
    assert any(hit.get("line", 0) >= 1 for hit in found["hits"])
    assert "workspace should hide" not in blob
    notes = search_env["workspace"] / "notes.txt"
    assert notes.is_file()


def test_search_does_not_read_other_session_or_env(search_env) -> None:
    session = search_env["session"]
    add_message(search_env["db"], session, Role.USER, "keep THIS_SESSION_TOKEN", 1)
    sibling = (
        Path(settings.app_data_dir)
        / "users"
        / "local-user"
        / "sessions"
        / search_env["other_id"]
    )
    sibling.mkdir(parents=True)
    (sibling / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": "secret OTHER_SESSION_TOKEN"}) + "\n",
        encoding="utf-8",
    )
    root = get_session_path(session)
    (root / ".env").write_text("API_KEY=sk-envleak12345678\n", encoding="utf-8")
    found = search_session_records(session, "TOKEN")
    blob = json.dumps(found, ensure_ascii=False)
    assert "THIS_SESSION_TOKEN" in blob
    assert "OTHER_SESSION_TOKEN" not in blob
    assert "sk-envleak" not in blob
    with pytest.raises(SessionSearchError) as exc:
        search_session_records(session, "API_KEY", path=".env")
    assert exc.value.code == "PATH_FORBIDDEN"
    with pytest.raises(SessionSearchError) as exc2:
        search_session_records(session, "API_KEY", path="../.env")
    assert exc2.value.code == "PATH_FORBIDDEN"


def test_search_blob_excerpt_stays_small(search_env) -> None:
    session = search_env["session"]
    huge = ("padding " * 8000) + f" spilled grep {GREP_PATH} "
    write_turn_blob(session, "asst-1", 1, huge)
    found = search_session_records(session, "loop.py")
    raw = json.dumps(found, ensure_ascii=False)
    assert GREP_PATH in raw
    assert len(raw) < 50_000
    assert all(len(hit.get("excerpt") or "") <= 280 for hit in found["hits"])
    assert not any(len(hit.get("excerpt") or "") > 1000 for hit in found["hits"])
    assert found["hits"][0].get("source") == "blob"


def test_search_session_tool_bound_and_rejects_foreign(search_env) -> None:
    from agent_window.tools.session_tools import search_session_tool

    session = search_env["session"]
    add_message(search_env["db"], session, Role.USER, f"tool saw {GREP_PATH}", 1)

    async def _run():
        with use_attachment_session(session.id):
            ok = await search_session_tool({"query": "loop.py"})
            forbidden = await search_session_tool(
                {"query": "loop.py", "session_id": search_env["other_id"]}
            )
        bare = await search_session_tool({"query": "loop.py"})
        return ok, forbidden, bare

    ok, forbidden, bare = asyncio.run(_run())
    ok_data = json.loads(ok)
    assert GREP_PATH in ok
    assert ok_data["hit_count"] >= 1
    assert json.loads(forbidden)["code"] == "SESSION_FORBIDDEN"
    assert GREP_PATH not in forbidden
    assert json.loads(bare)["code"] == "NO_SESSION_CONTEXT"


def test_search_session_is_registered_and_prompt_mentions_it() -> None:
    import agent_window.tools  # noqa: F401
    from agent_window.tools.registry import registry

    assert registry.get("search_session") is not None
    assert "search_session" in registry.list_names()
    from agent_window.api.routes import _system_prompt

    prompt = _system_prompt()
    assert "search_session" in prompt
    assert "do not dump the whole log" in prompt
    assert "do not guess" in prompt


def test_search_does_not_fall_back_to_sqlite(search_env) -> None:
    session = search_env["session"]
    add_message(search_env["db"], session, Role.ASSISTANT, f"sqlite-only {GREP_PATH}", 1)
    path = transcript_path(session)
    assert path.is_file()
    path.unlink()
    found = search_session_records(session, "loop.py")
    blob = json.dumps(found, ensure_ascii=False)
    assert found["hit_count"] == 0
    assert GREP_PATH not in blob
    assert "sqlite-only" not in blob


def test_search_excerpt_includes_tool_name_field(search_env) -> None:
    from agent_window.services.session_transcript import append_transcript_event

    session = search_env["session"]
    append_transcript_event(
        session,
        "tool",
        {"name": "grep", "path": GREP_PATH, "content": "ok"},
    )
    found = search_session_records(session, "loop.py")
    assert found["hit_count"] >= 1
    assert GREP_PATH in found["hits"][0]["excerpt"]


def test_search_rejects_turns_env_and_bad_max_hits(search_env) -> None:
    from agent_window.tools.session_tools import search_session_tool
    from agent_window.services.attachment_context import use_attachment_session

    session = search_env["session"]
    with pytest.raises(SessionSearchError) as exc:
        search_session_records(session, "KEY", path="turns/secret.env")
    assert exc.value.code == "PATH_FORBIDDEN"

    async def _run():
        with use_attachment_session(session.id):
            return await search_session_tool({"query": "loop.py", "max_hits": "nope"})

    payload = json.loads(asyncio.run(_run()))
    assert payload["code"] == "INVALID_ARGS"
    assert "loop.py" not in json.dumps(payload)
