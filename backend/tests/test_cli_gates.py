"""CLI status / approve / reject — no live backend."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from agent_window.cli.main import (
    _explicit_targets,
    _print_status,
    _resolve_prompt,
    _status_payload,
    _wait_pending,
    build_parser,
    cmd_approve,
    cmd_reject,
    cmd_status,
)


class FakeClient:
    def __init__(
        self,
        *,
        patches: Optional[List[Dict[str, Any]]] = None,
        shells: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        sessions: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        active: Optional[List[str]] = None,
    ) -> None:
        self.patches = list(patches or [])
        self.shells = list(shells or [])
        self.memories = list(memories or [])
        self.sessions = list(sessions or [])
        self.messages = list(messages or [])
        self.active = list(active or [])
        self.posts: List[str] = []

    def get(self, path: str, **_kwargs: Any) -> Any:
        if path == "/api/workspace/patches":
            return self.patches
        if path == "/api/workspace/shells":
            return self.shells
        if path == "/api/memory/proposals":
            return self.memories
        if path == "/api/runtime":
            return {"active_sessions": self.active}
        if path == "/api/sessions":
            return self.sessions
        if path.endswith("/messages"):
            return self.messages
        raise AssertionError(path)

    def post(self, path: str, body: Any = None, **_kwargs: Any) -> Any:
        self.posts.append(path)
        if "/patches/" in path:
            return {"id": "p1", "path": "hello.txt", "status": "applied" if path.endswith("/apply") else "rejected"}
        if "/shells/" in path:
            return {"id": "s1", "command": "pwd", "status": "applied" if path.endswith("/apply") else "rejected"}
        if "/proposals/" in path:
            return {"id": "m1", "mode": "append", "status": "applied" if path.endswith("/apply") else "rejected"}
        raise AssertionError(path)


def test_parser_has_status_approve_reject() -> None:
    parser = build_parser()
    status = parser.parse_args(["status", "--json", "--session-id", "abc"])
    assert status.command == "status"
    assert status.session == "abc"
    assert status.json is True
    approve = parser.parse_args(["approve", "--patch-id", "p1", "--shell-id", "s1"])
    assert approve.patch_ids == ["p1"]
    assert approve.shell_ids == ["s1"]
    reject = parser.parse_args(["reject", "--memory-id", "m1"])
    assert reject.memory_ids == ["m1"]


def test_status_payload_workspace_and_session() -> None:
    client = FakeClient(
        patches=[{"id": "p1", "path": "a.txt", "status": "pending"}],
        sessions=[{"id": "sid", "title": "cli: hello"}],
        messages=[{"id": "m", "role": "assistant", "content": "ok"}],
        active=["sid"],
    )
    payload = _status_payload(client, "sid")
    assert payload["awaiting_approval"] is True
    assert payload["session"]["is_running"] is True
    assert payload["session"]["title"] == "cli: hello"
    assert payload["patches"][0]["id"] == "p1"


def test_print_status_empty(capsys: pytest.CaptureFixture[str]) -> None:
    _print_status({"patches": [], "shells": [], "memories": [], "active_sessions": []})
    out = capsys.readouterr().out
    assert "待审批: (无)" in out


def test_approve_explicit_ids() -> None:
    client = FakeClient()
    args = SimpleNamespace(patch_ids=["p1"], shell_ids=[], memory_ids=[], no_input=True)
    assert cmd_approve(client, args) == 0
    assert client.posts == ["/api/workspace/patches/p1/apply"]


def test_reject_explicit_ids() -> None:
    client = FakeClient()
    args = SimpleNamespace(patch_ids=[], shell_ids=["s1"], memory_ids=[], no_input=True)
    assert cmd_reject(client, args) == 0
    assert client.posts == ["/api/workspace/shells/s1/reject"]


def test_approve_no_input_without_ids_exits_2() -> None:
    client = FakeClient(patches=[{"id": "p1", "path": "a.txt", "status": "pending"}])
    args = SimpleNamespace(patch_ids=[], shell_ids=[], memory_ids=[], no_input=True)
    assert cmd_approve(client, args) == 2
    assert client.posts == []


def test_explicit_targets_order() -> None:
    args = SimpleNamespace(patch_ids=["a"], shell_ids=["b"], memory_ids=["c"])
    assert _explicit_targets(args) == [("patch", "a"), ("shell", "b"), ("memory", "c")]


def test_cmd_status_json(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient()
    args = SimpleNamespace(session=None, json=True)
    assert cmd_status(client, args) == 0
    out = capsys.readouterr().out
    assert '"awaiting_approval": false' in out


def test_parser_run_has_wait_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--wait", "--wait-timeout", "60", "-s", "sid", "do it"])
    assert args.wait is True
    assert args.wait_timeout == 60.0
    assert args.session == "sid"


def test_wait_pending_clears_immediately() -> None:
    client = FakeClient()
    assert _wait_pending(client, 5.0) == 0


def test_wait_pending_times_out() -> None:
    client = FakeClient(patches=[{"id": "p1", "path": "x.txt", "status": "pending"}])
    assert _wait_pending(client, 0.1) == 3


def test_resolve_prompt_from_file(tmp_path) -> None:
    f = tmp_path / "task.md"
    f.write_text("refactor utils", encoding="utf-8")
    args = SimpleNamespace(prompt="", file=str(f))
    assert _resolve_prompt(args) == "refactor utils"


def test_resolve_prompt_combines_file(tmp_path) -> None:
    f = tmp_path / "extra.md"
    f.write_text("details here", encoding="utf-8")
    args = SimpleNamespace(prompt="do this", file=str(f))
    result = _resolve_prompt(args)
    assert "do this" in result
    assert "details here" in result
