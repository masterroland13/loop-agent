"""YOLO gates must not emit pending confirmation SSE (no UI flicker)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from agent_window.agent.gate_hooks import handle_patch_gate, handle_shell_gate
from agent_window.services.patches import PatchStatus
from agent_window.services.shell import ShellStatus


def _collect(agen) -> list[tuple[dict[str, Any], str | None]]:
    async def _run():
        out = []
        async for item in agen:
            out.append(item)
        return out

    return asyncio.run(_run())


def test_shell_gate_yolo_skips_pending_and_await_approval() -> None:
    parsed = {
        "shell": {
            "id": "sh1",
            "argv": ["echo", "hi"],
            "cwd": ".",
            "command": "echo hi",
        }
    }

    class FakeShell:
        status = ShellStatus.DONE
        command_display = "echo hi"
        exit_code = 0
        stdout = "hi\n"
        stderr = ""
        truncated = False
        error = None

    fake = FakeShell()

    with (
        patch("agent_window.agent.gate_hooks.decide_shell", new=AsyncMock(return_value=fake)),
        patch(
            "agent_window.agent.gate_hooks.shell_to_public",
            return_value={
                "argv": ["echo", "hi"],
                "cwd": ".",
                "command": "echo hi",
                "status": "done",
                "exit_code": 0,
                "stdout": "hi\n",
                "stderr": "",
                "truncated": False,
                "error": None,
            },
        ),
    ):
        events = _collect(handle_shell_gate(parsed, auto_apply=True))

    types_status = [(e[0].get("type"), e[0].get("status")) for e in events if e[0].get("type") != "_result"]
    assert ("shell", "pending") not in types_status
    assert not any(e[0].get("type") == "await_approval" for e in events)
    assert ("shell", "done") in types_status


def test_shell_gate_trusted_emits_pending_then_await() -> None:
    parsed = {
        "shell": {
            "id": "sh2",
            "argv": ["echo", "hi"],
            "cwd": ".",
            "command": "echo hi",
        }
    }

    class FakeShell:
        status = ShellStatus.DONE
        command_display = "echo hi"
        exit_code = 0
        stdout = "hi\n"
        stderr = ""
        truncated = False
        error = None

    fake = FakeShell()

    with (
        patch(
            "agent_window.agent.gate_hooks.wait_for_shell_decision",
            new=AsyncMock(return_value=fake),
        ),
        patch(
            "agent_window.agent.gate_hooks.shell_to_public",
            return_value={
                "argv": ["echo", "hi"],
                "cwd": ".",
                "command": "echo hi",
                "status": "done",
                "exit_code": 0,
                "stdout": "hi\n",
                "stderr": "",
                "truncated": False,
                "error": None,
            },
        ),
    ):
        events = _collect(handle_shell_gate(parsed, auto_apply=False))

    assert any(e[0].get("type") == "shell" and e[0].get("status") == "pending" for e in events)
    assert any(e[0].get("type") == "await_approval" for e in events)


def test_patch_gate_yolo_skips_pending() -> None:
    parsed = {
        "patch": {
            "id": "p1",
            "path": "a.txt",
            "unified_diff": "--- a\n+++ b\n",
            "is_new_file": True,
            "is_delete": False,
        }
    }

    class FakePatch:
        status = PatchStatus.APPLIED
        path = "a.txt"
        unified_diff = "--- a\n+++ b\n"
        is_new_file = True
        is_delete = False
        error = None
        applied_hunks = None

    with patch(
        "agent_window.agent.gate_hooks.decide_patch",
        new=AsyncMock(return_value=FakePatch()),
    ):
        events = _collect(handle_patch_gate(parsed, auto_apply=True))

    assert not any(e[0].get("type") == "diff" and e[0].get("status") == "pending" for e in events)
    assert not any(e[0].get("type") == "await_approval" for e in events)
    assert any(e[0].get("type") == "diff" and e[0].get("status") == "applied" for e in events)
