"""F6 middle tier: TurnEvent schema + trace persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_window.agent.turn_event import (
    event_from_sse,
    events_to_tool_trace,
    latest_goal,
    latest_progress_checkpoint,
    parse_trace,
    serialize_trace,
)
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.storage import create_session, get_session
from agent_window.services.turn_trace import TurnTraceWriter, trace_for_response


def test_event_from_sse_tool_start_and_result() -> None:
    start = event_from_sse({"type": "tool_start", "name": "read_file", "arguments": '{"path":"a.py"}'})
    assert start is not None
    assert start["type"] == "tool_start"
    assert start["tool"] == "read_file"
    assert start["status"] == "running"

    result = event_from_sse(
        {
            "type": "tool_result",
            "name": "read_file",
            "content": json.dumps({"status": "ok", "content": "print(1)"}),
        }
    )
    assert result is not None
    assert result["type"] == "tool_result"
    assert result["status"] == "ok"


def test_events_to_tool_trace_running_then_done() -> None:
    events = [
        event_from_sse({"type": "tool_start", "name": "grep", "arguments": "{}"}),
        event_from_sse(
            {
                "type": "tool_result",
                "name": "grep",
                "content": json.dumps({"match_count": 2}),
            }
        ),
    ]
    events = [e for e in events if e]
    trace = events_to_tool_trace(events)
    assert len(trace) == 1
    assert trace[0]["name"] == "grep"
    assert trace[0]["status"] == "done"


def test_events_to_tool_trace_failed_result() -> None:
    events = [
        event_from_sse({"type": "tool_start", "name": "propose_shell", "arguments": "{}"}),
        event_from_sse(
            {
                "type": "tool_result",
                "name": "propose_shell",
                "content": json.dumps({"status": "failed", "error": "boom"}),
            }
        ),
    ]
    events = [e for e in events if e]
    trace = events_to_tool_trace(events)
    assert trace[0]["status"] == "error"


def test_latest_goal_and_checkpoint() -> None:
    events = [
        event_from_sse({"type": "turn_goal", "goal": "列出 src"}),
        event_from_sse(
            {
                "type": "progress_checkpoint",
                "goal": "列出 src",
                "tools_since_last": 3,
                "reason": "interval",
            }
        ),
    ]
    events = [e for e in events if e]
    assert latest_goal(events) == "列出 src"
    cp = latest_progress_checkpoint(events)
    assert cp is not None
    assert cp["toolsSinceLast"] == 3
    assert cp["reason"] == "interval"
    assert "reply" not in cp


def test_latest_checkpoint_prefers_reply() -> None:
    events = [
        event_from_sse(
            {
                "type": "progress_checkpoint",
                "tools_since_last": 2,
                "reason": "interval",
            }
        ),
        event_from_sse(
            {
                "type": "progress_checkpoint",
                "tools_since_last": 2,
                "reason": "interval",
                "reply": "进度：两步已完成，无阻塞；下一步收工。",
            }
        ),
    ]
    events = [e for e in events if e]
    cp = latest_progress_checkpoint(events)
    assert cp is not None
    assert cp.get("reply")
    assert "无阻塞" in cp["reply"]
    assert events[-1].get("full_ref")  # persisted for refresh


def test_store_full_ref_spills_when_over_limit() -> None:
    from agent_window.agent.turn_event import INLINE_FULL_MAX, FILE_REF_PREFIX, store_full_ref

    small, spilled = store_full_ref("ok")
    assert small == "ok"
    assert spilled is False

    big = "x" * (INLINE_FULL_MAX + 50)
    truncated, spilled = store_full_ref(big)
    assert spilled is False
    assert truncated is not None
    assert len(truncated) == INLINE_FULL_MAX

    spilled_refs: list[str] = []

    def spill(text: str) -> str:
        spilled_refs.append(text)
        return f"{FILE_REF_PREFIX}turns/a/e1.txt"

    ref, spilled = store_full_ref(big, spill=spill)
    assert spilled is True
    assert ref == f"{FILE_REF_PREFIX}turns/a/e1.txt"
    assert spilled_refs and len(spilled_refs[0]) == len(big)


def test_turn_trace_writer_spills_large_tool_result(data_dir: Path) -> None:
    from agent_window.agent.turn_event import INLINE_FULL_MAX, is_file_ref
    from agent_window.services.storage import read_session_blob

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="spill")
        session_db = get_session(db, session.id)
        assert session_db is not None
        writer = TurnTraceWriter.create_placeholder(db, session_db, sequence=2)
        huge = json.dumps({"content": "Z" * (INLINE_FULL_MAX + 200)}, ensure_ascii=False)
        writer.note_sse(
            {
                "type": "tool_result",
                "name": "read_file",
                "content": huge,
            }
        )
        assistant = [m for m in session_db.messages if m.role == Role.ASSISTANT][0]
        events = parse_trace(assistant.trace)
        assert len(events) == 1
        ev = events[0]
        assert is_file_ref(ev.get("full_ref"))
        assert ev.get("truncated") is True
        assert "…" in (ev.get("summary") or "") or "落盘" in (ev.get("summary") or "")
        body = read_session_blob(session_db, ev["full_ref"])
        assert body == huge
        trace = events_to_tool_trace(events)
        assert trace[0].get("fullRef")
        assert trace[0].get("truncated") is True
        assert "Z" * 50 not in (trace[0].get("detail") or "")
    finally:
        db.close()


def test_blob_path_rejects_traversal(data_dir: Path) -> None:
    from agent_window.services.storage import resolve_session_blob_path

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="safe")
        with pytest.raises(ValueError):
            resolve_session_blob_path(session, "../etc/passwd")
        with pytest.raises(ValueError):
            resolve_session_blob_path(session, "turns/../../x")
    finally:
        db.close()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from datetime import datetime, timedelta

    monkeypatch.setattr("agent_window.models.settings.app_data_dir", tmp_path)
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", tmp_path)

    clock = {"t": datetime(2026, 8, 23, 0, 0, 0)}

    class _FakeDateTime:
        @classmethod
        def utcnow(cls) -> datetime:
            clock["t"] += timedelta(seconds=1)
            return clock["t"]

    monkeypatch.setattr("agent_window.services.storage.datetime", _FakeDateTime)
    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    return tmp_path


def test_turn_trace_writer_persists_incremental_events(data_dir: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="t")
        session_db = get_session(db, session.id)
        assert session_db is not None

        writer = TurnTraceWriter.create_placeholder(db, session_db, sequence=2)
        writer.note_sse({"type": "tool_start", "name": "list_dir", "arguments": "{}"})
        writer.note_sse(
            {
                "type": "tool_result",
                "name": "list_dir",
                "content": json.dumps({"entries": ["a.py"]}),
            }
        )

        stored = get_session(db, session.id)
        assert stored is not None
        assistant = [m for m in stored.messages if m.role == Role.ASSISTANT][0]
        events = trace_for_response(assistant)
        assert len(events) == 2
        assert events[0]["type"] == "tool_start"
        assert events[1]["type"] == "tool_result"

        turn_meta = {
            "type": "turn_meta",
            "model": "test",
            "elapsed_ms": 1,
            "approx_prompt_tokens": 1,
            "approx_completion_tokens": 1,
            "compressed": False,
            "memory_injected": False,
            "goal": "go",
            "message_id": assistant.id,
        }
        writer.finalize(summary=json.dumps(turn_meta), content="done")
        db.refresh(assistant)
        assert assistant.content == "done"
        assert json.loads(assistant.summary)["type"] == "turn_meta"
    finally:
        db.close()


def test_parse_trace_invalid_returns_empty() -> None:
    assert parse_trace(None) == []
    assert parse_trace("not-json") == []
    assert parse_trace("{}") == []
    assert serialize_trace([{"type": "tool_start", "summary": "x"}]).startswith("[")


def test_event_from_sse_diff_keeps_type_not_gate() -> None:
    mapped = event_from_sse(
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "a.py",
            "unified_diff": "--- a\n+++ b\n@@\n+x\n",
            "status": "applied",
        }
    )
    assert mapped is not None
    assert mapped["type"] == "diff"
    assert mapped["type"] != "gate"
    assert mapped["patch_id"] == "p1"
    assert mapped["path"] == "a.py"
    assert mapped["status"] == "applied"


def test_finalize_interrupted_persists_cancelled_trace(data_dir: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="cancel")
        session_db = get_session(db, session.id)
        assert session_db is not None
        writer = TurnTraceWriter.create_placeholder(db, session_db, sequence=2)
        writer.note_sse({"type": "tool_start", "name": "grep", "arguments": "{}"})
        writer.finalize_interrupted(code="TURN_CANCELLED", message="已停止")
        db.refresh(writer.assistant)
        events = trace_for_response(writer.assistant)
        assert len(events) >= 2
        summary = json.loads(writer.assistant.summary)
        assert summary["type"] == "turn_cancelled"
        assert writer.assistant.content == "已停止"
    finally:
        db.close()
