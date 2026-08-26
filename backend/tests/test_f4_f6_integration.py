"""F4/F6 integration — loop slim vs SSE full; messages API trace."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_window.agent.turn_event import events_to_tool_trace
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.storage import add_message, create_session, get_session


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


def test_f4_loop_slim_in_working_full_in_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    """F4: model sees slim tool body; SSE tool_result stays full."""
    big_body = "\n".join(f"{i}|{'x' * 80}" for i in range(1, 401))
    full_result = json.dumps(
        {
            "path": "src/huge.py",
            "offset": 1,
            "limit": 400,
            "total_lines": 400,
            "truncated": False,
            "content": big_body,
        },
        ensure_ascii=False,
    )

    chat_calls: list[list[dict]] = []

    async def fake_chat(working, tools=None, model=None):
        chat_calls.append(list(working))
        if len(chat_calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc_rf", "name": "read_file", "arguments": '{"path":"src/huge.py"}'},
                ],
            }
        tool_msgs = [m for m in working if m.get("role") == "tool"]
        assert tool_msgs, "expected slim tool message in working[]"
        slim_body = tool_msgs[-1]["content"]
        assert len(slim_body) < len(full_result)
        slim = json.loads(slim_body)
        assert slim["path"] == "src/huge.py"
        assert slim.get("truncated") is True
        assert "hint" in slim
        return {"content": "已读文件。", "tool_calls": []}

    async def fake_handle(name: str, arguments) -> str:
        assert name == "read_file"
        return full_result

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_handle)
    monkeypatch.setattr(
        "agent_window.agent.loop.load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 0},
    )

    from agent_window.agent.loop import run_agent_loop

    async def _run() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop([{"role": "user", "content": "读大文件"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    tool_results = [e for e in events if e.get("type") == "tool_result" and e.get("name") == "read_file"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"] == full_result
    assert len(tool_results[0]["content"]) > len(json.loads(chat_calls[1][-1]["content"]))
    assert any(e.get("type") == "done" for e in events)


def test_f4_gate_continue_hint_survives_slim(monkeypatch: pytest.MonkeyPatch) -> None:
    """F4 + F3: continue_hint must remain in slim gate result for second LLM beat."""
    calls: list[dict] = []

    async def fake_chat(working, tools=None, model=None):
        calls.append({"n": len(calls) + 1})
        if len(calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "tc_sh", "name": "propose_shell", "arguments": '{"argv":["ls"]}'},
                ],
            }
        tool_msgs = [m for m in working if m.get("role") == "tool"]
        body = json.loads(tool_msgs[-1]["content"])
        assert body.get("loop_continue") is True
        assert "continue_hint" in body
        assert "stdout" not in body
        return {"content": "换命令后完成。", "tool_calls": []}

    async def fake_handle(name: str, arguments) -> str:
        return json.dumps(
            {
                "status": "failed",
                "shell_id": "s1",
                "command": "ls",
                "error": "boom",
                "stdout": "x" * 3000,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("agent_window.agent.loop.provider.chat_complete", fake_chat)
    monkeypatch.setattr("agent_window.agent.loop.handle_function_call", fake_handle)
    monkeypatch.setattr(
        "agent_window.agent.loop.load_agent_settings",
        lambda: {"disabled_tools": [], "max_tool_iters": 8, "checkpoint_every_n_tools": 0},
    )

    from agent_window.agent.loop import run_agent_loop

    async def _run() -> list[dict]:
        events: list[dict] = []
        async for ev in run_agent_loop([{"role": "user", "content": "列目录"}]):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert len(calls) == 2
    sse = [e for e in events if e.get("type") == "tool_result" and e.get("loop_continue")]
    assert len(sse) == 1
    full = json.loads(sse[0]["content"])
    assert "stdout" in full
    assert len(full["stdout"]) == 3000


def test_f6_trace_roundtrip_to_tool_timeline() -> None:
    """F6: persisted TurnEvents rebuild the same toolTrace shape as live SSE."""
    from agent_window.agent.turn_event import event_from_sse

    events = [
        event_from_sse({"type": "tool_start", "name": "grep", "arguments": '{"pattern":"foo"}'}),
        event_from_sse(
            {
                "type": "tool_result",
                "name": "grep",
                "content": json.dumps({"match_count": 1, "matches": [{"path": "a.py", "line": 3, "text": "foo"}]}),
            }
        ),
        event_from_sse(
            {
                "type": "progress_checkpoint",
                "goal": "找 foo",
                "tools_since_last": 1,
                "reason": "gate",
            }
        ),
    ]
    events = [e for e in events if e]
    trace = events_to_tool_trace(events)
    assert len(trace) == 1
    assert trace[0]["name"] == "grep"
    assert trace[0]["status"] == "done"
    assert "match_count" in (trace[0].get("detail") or "")


def test_f6_messages_api_includes_trace(data_dir: Path) -> None:
    """F6: GET /messages exposes trace for refresh recovery."""
    from fastapi.testclient import TestClient

    from agent_window.main import app

    db = get_sessionmaker()()
    session_id = ""
    try:
        session = create_session(db, title="trace-api")
        session_id = session.id
        add_message(db, session, Role.USER, "hi", 1)
        trace_json = json.dumps(
            [
                {"type": "tool_start", "tool": "list_dir", "status": "running", "summary": "list_dir"},
                {
                    "type": "tool_result",
                    "tool": "list_dir",
                    "status": "ok",
                    "summary": "2 entries",
                    "full_ref": '{"entries":[]}',
                },
            ],
            ensure_ascii=False,
        )
        add_message(db, session, Role.ASSISTANT, "", 2, summary="", trace=trace_json)
    finally:
        db.close()

    client = TestClient(app)
    response = client.get(f"/api/sessions/{session_id}/messages")
    assert response.status_code == 200
    messages = response.json()
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert len(assistant["trace"]) == 2
    assert assistant["trace"][0]["type"] == "tool_start"
    assert assistant["trace"][1]["type"] == "tool_result"
    assert assistant["content"] == ""


def test_f6_in_progress_assistant_has_trace_without_turn_meta(data_dir: Path) -> None:
    """F6: placeholder turn — trace present, turn_meta absent (refresh should poll)."""
    from agent_window.services.turn_trace import is_turn_in_progress

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="in-progress")
        add_message(db, session, Role.USER, "run tools", 1)
        assistant = add_message(
            db,
            session,
            Role.ASSISTANT,
            "",
            2,
            summary="",
            trace=json.dumps(
                [{"type": "tool_start", "tool": "read_file", "status": "running", "summary": "read_file"}],
                ensure_ascii=False,
            ),
        )
        assert is_turn_in_progress(assistant, session_active=True) is True
        assert is_turn_in_progress(assistant, session_active=False) is False

        turn_meta = json.dumps({"type": "turn_meta", "model": "m", "message_id": assistant.id})
        assistant.summary = turn_meta
        db.add(assistant)
        db.commit()
        db.refresh(assistant)
        assert is_turn_in_progress(assistant, session_active=True) is False
    finally:
        db.close()
