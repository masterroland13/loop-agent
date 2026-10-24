"""C0: append-only session transcript under the user data dir."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_window.config import settings
from agent_window.models import Role, init_db
from agent_window.services.compress import compress_messages_if_needed
from agent_window.services.session_transcript import (
    TRANSCRIPT_NAME,
    append_sse_event,
    append_transcript_event,
    read_transcript_events,
    transcript_path,
)
from agent_window.services.storage import add_message, create_session, get_session


@pytest.fixture
def data_env(tmp_path, monkeypatch):
    data = tmp_path / "app-data"
    data.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("keep-out", encoding="utf-8")
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
    from agent_window.models import get_sessionmaker

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="transcript", workspace_root=str(workspace))
        yield {
            "db": db,
            "session": session,
            "data": data,
            "workspace": workspace,
            "tmp": tmp_path,
        }
    finally:
        db.close()


def test_two_turns_write_jsonl_under_user_data(data_env) -> None:
    db = data_env["db"]
    session = get_session(db, data_env["session"].id)
    assert session is not None
    add_message(db, session, Role.USER, "first ask", 1)
    add_message(db, session, Role.ASSISTANT, "first reply", 2)
    add_message(db, session, Role.USER, "second ask", 3)
    add_message(db, session, Role.ASSISTANT, "second reply", 4)

    path = transcript_path(session)
    assert path.is_file()
    assert path.parent == Path(settings.app_data_dir) / session.data_path
    events = read_transcript_events(session)
    assert len(events) >= 4
    types = [item["type"] for item in events]
    assert types.count("user") == 2
    assert types.count("assistant") == 2
    assert "first ask" in json.dumps(events, ensure_ascii=False)
    assert "second reply" in json.dumps(events, ensure_ascii=False)
    assert not (data_env["workspace"] / TRANSCRIPT_NAME).exists()
    assert list(data_env["workspace"].rglob(TRANSCRIPT_NAME)) == []


def test_transcript_stays_out_of_workspace_and_install(data_env, monkeypatch) -> None:
    install = data_env["tmp"] / "lib" / "loop-agent"
    install.mkdir(parents=True)
    monkeypatch.setenv("LOOP_INSTALL_DIR", str(install))
    db = data_env["db"]
    session = get_session(db, data_env["session"].id)
    assert session is not None
    add_message(db, session, Role.USER, "hello", 1)
    path = transcript_path(session)
    assert path.is_file()
    assert data_env["data"] in path.parents or path.is_relative_to(data_env["data"])
    assert list(data_env["workspace"].rglob("*.jsonl")) == []
    assert list(install.rglob("*.jsonl")) == []
    assert list(Path(session.workspace_root).rglob("transcript.jsonl")) == []


def test_secrets_are_redacted_and_attachment_bodies_stay_out(data_env) -> None:
    session = data_env["session"]
    secret = "sk-SUPERSECRETKEYVALUE99"
    append_transcript_event(
        session,
        "tool",
        {
            "name": "propose_edit",
            "api_key": secret,
            "authorization": f"Bearer {secret}",
            "content": f"api_key={secret} and bearer {secret}",
        },
    )
    text = transcript_path(session).read_text(encoding="utf-8")
    assert secret not in text
    assert "sk-SUPERSECRETKEYVALUE99" not in text
    assert "[redacted]" in text
    events = read_transcript_events(session)
    assert events[-1]["api_key"] == "[redacted]"
    assert events[-1]["authorization"] == "[redacted]"


def test_add_message_attachments_store_ids_not_bodies(data_env) -> None:
    db = data_env["db"]
    session = get_session(db, data_env["session"].id)
    assert session is not None
    body = "ATTACHMENT_BODY_MUST_NOT_LAND_IN_JSONL"
    add_message(
        db,
        session,
        Role.USER,
        "see file",
        1,
        attachments=json.dumps(
            [{"id": "att-1", "filename": "secret.txt", "text": body, "content": body}],
            ensure_ascii=False,
        ),
    )
    text = transcript_path(session).read_text(encoding="utf-8")
    assert body not in text
    events = read_transcript_events(session)
    user = next(item for item in events if item["type"] == "user")
    assert user["attachments"] == [{"id": "att-1", "filename": "secret.txt"}]


def test_compress_does_not_delete_or_rewrite_jsonl(data_env) -> None:
    session = data_env["session"]
    append_transcript_event(session, "user", {"content": "keep-me-1"})
    append_transcript_event(session, "assistant", {"content": "keep-me-2"})
    before = transcript_path(session).read_text(encoding="utf-8")
    assert before.count("\n") == 2

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "aaaaaaaaaa " * 80},
        {"role": "assistant", "content": "bbbbbbbbbb " * 80},
        {"role": "user", "content": "cccccccccc " * 80},
    ]

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=None,
        )

    out, compressed, _meta = asyncio.run(_run())
    assert compressed is True
    after = transcript_path(session).read_text(encoding="utf-8")
    assert after == before
    assert "keep-me-1" in after
    assert "keep-me-2" in after


def test_compress_off_leaves_jsonl_untouched(data_env) -> None:
    session = data_env["session"]
    append_transcript_event(session, "user", {"content": "still-here"})
    before = transcript_path(session).read_bytes()

    async def _run():
        return await compress_messages_if_needed(
            [{"role": "user", "content": "x"}],
            auto_compress=False,
            context_limit=8,
            summarize=None,
        )

    out, compressed, _meta = asyncio.run(_run())
    assert compressed is False
    assert out[0]["content"] == "x"
    assert transcript_path(session).read_bytes() == before


def test_empty_assistant_placeholder_is_not_a_line(data_env) -> None:
    db = data_env["db"]
    session = get_session(db, data_env["session"].id)
    assert session is not None
    add_message(db, session, Role.USER, "ask", 1)
    add_message(db, session, Role.ASSISTANT, "", 2)
    events = read_transcript_events(session)
    assert [item["type"] for item in events] == ["user"]
    assert all(item.get("content") != "" or item["type"] != "assistant" for item in events)


def test_uninstall_leaves_transcript(data_env, tmp_path) -> None:
    from agent_window.host.session import uninstall_shell_assets

    session = data_env["session"]
    append_transcript_event(session, "user", {"content": "survive-uninstall"})
    path = transcript_path(session)
    dest = tmp_path / "lib" / "loop-agent"
    dest.mkdir(parents=True)
    (dest / "dist").mkdir()
    (dest / "dist" / "index.html").write_text("ok", encoding="utf-8")
    uninstall_shell_assets(
        dest,
        tmp_path / "bin",
        tmp_path / "applications",
        data_env["data"],
    )
    assert path.is_file()
    assert "survive-uninstall" in path.read_text(encoding="utf-8")
    assert data_env["data"].exists()


def test_send_turn_appends_user_assistant_and_tool(data_env, monkeypatch) -> None:
    from agent_window.main import app
    from agent_window.services.provider import provider

    monkeypatch.setattr(provider, "is_available", lambda: True)
    monkeypatch.setattr(provider, "profile_is_ready", lambda _profile_id=None: True)

    async def fake_loop(*_a, **_k):
        yield {"type": "tool_start", "name": "list_dir", "tool_call_id": "c1"}
        yield {
            "type": "tool_result",
            "name": "list_dir",
            "tool_call_id": "c1",
            "content": "ok-dir",
        }
        yield {"type": "await_approval", "gate": "edit", "status": "pending"}
        yield {"type": "token", "content": "done-reply"}
        yield {"type": "done"}

    monkeypatch.setattr("agent_window.api.routes.run_agent_loop", fake_loop)
    client = TestClient(app)
    sid = data_env["session"].id
    with client.stream(
        "POST",
        f"/api/sessions/{sid}/messages",
        json={"content": "list the folder"},
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass

    session = get_session(data_env["db"], sid)
    assert session is not None
    events = read_transcript_events(session)
    types = [item["type"] for item in events]
    assert "user" in types
    assert "assistant" in types
    assert "tool" in types
    assert "gate" in types
    assert any(item.get("content") == "list the folder" for item in events)
    assert any(item.get("content") == "done-reply" for item in events)
    assert any(item.get("name") == "list_dir" for item in events)


def test_interrupted_turn_still_appends_assistant(data_env) -> None:
    from agent_window.models import get_sessionmaker
    from agent_window.services.turn_trace import TurnTraceWriter

    db = get_sessionmaker()()
    try:
        session = get_session(db, data_env["session"].id)
        assert session is not None
        writer = TurnTraceWriter.create_placeholder(db, session, sequence=2)
        writer.note_sse({"type": "token", "content": "partial-"})
        writer.finalize_interrupted(code="TURN_CANCELLED", message="已停止")
        events = read_transcript_events(session)
        assistants = [item for item in events if item["type"] == "assistant"]
        assert assistants
        assert "partial-" in assistants[-1]["content"]
        assert not any(item.get("content") == "" for item in assistants)
    finally:
        db.close()


def test_yolo_gate_sse_is_recorded_without_await_approval(data_env) -> None:
    session = data_env["session"]
    append_sse_event(
        session,
        {"type": "diff", "status": "applied", "path": "a.py"},
    )
    events = read_transcript_events(session)
    gates = [item for item in events if item["type"] == "gate"]
    assert gates
    assert gates[-1]["gate"] == "diff"
    assert gates[-1]["status"] == "applied"
    assert gates[-1]["path"] == "a.py"
    assert "unified_diff" not in gates[-1]


def test_tool_start_falls_back_to_arguments(data_env) -> None:
    session = data_env["session"]
    append_sse_event(
        session,
        {
            "type": "tool_start",
            "name": "read_file",
            "tool_call_id": "c9",
            "arguments": '{"path": "notes.txt"}',
        },
    )
    events = read_transcript_events(session)
    tools = [item for item in events if item["type"] == "tool"]
    assert tools[-1]["content"] == '{"path": "notes.txt"}'


def test_escape_data_path_does_not_write_outside_app_data(data_env) -> None:
    workspace = data_env["workspace"]

    class Fake:
        data_path = f"../{workspace.name}"

    append_transcript_event(Fake(), "user", {"content": "escaped-payload"})
    assert list(workspace.rglob(TRANSCRIPT_NAME)) == []
    assert read_transcript_events(Fake()) == []


def test_corrupt_jsonl_line_is_skipped(data_env) -> None:
    session = data_env["session"]
    append_transcript_event(session, "user", {"content": "good-1"})
    path = transcript_path(session)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not-json\n")
    append_transcript_event(session, "user", {"content": "good-2"})
    events = read_transcript_events(session)
    contents = [item.get("content") for item in events]
    assert "good-1" in contents
    assert "good-2" in contents
    assert all(isinstance(item, dict) for item in events)
