"""Gate 深拆 Step 1: await markers resolve via gate_hooks, not loop inline."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

from agent_window.agent.gate_hooks import (
    await_marker_kind,
    resolve_await_marker,
    still_has_await_marker,
)
from agent_window.services.patches import PatchStatus
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY
from agent_window.tools.memory_tools import AWAIT_MEMORY_KEY
from agent_window.tools.shell_tools import AWAIT_SHELL_KEY


def _collect(agen) -> list[tuple[dict[str, Any], str | None]]:
    async def _run():
        out = []
        async for item in agen:
            out.append(item)
        return out

    return asyncio.run(_run())


def test_await_marker_kind_positive_and_negative() -> None:
    assert await_marker_kind({AWAIT_PATCH_KEY: True, "patch": {}}) == "patch"
    assert await_marker_kind({AWAIT_SHELL_KEY: True}) == "shell"
    assert await_marker_kind({AWAIT_MEMORY_KEY: True}) == "memory"
    assert await_marker_kind({"status": "applied"}) is None
    assert await_marker_kind(None) is None
    assert still_has_await_marker({AWAIT_PATCH_KEY: True})
    assert not still_has_await_marker({"status": "done"})


def test_resolve_await_marker_missing_patch_payload() -> None:
    events = _collect(
        resolve_await_marker({AWAIT_PATCH_KEY: True}, auto_apply=True)
    )
    assert len(events) == 1
    assert events[0][0].get("type") == "_result"
    body = json.loads(events[0][1] or "{}")
    assert body.get("status") == "failed"
    assert "missing patch" in (body.get("error") or "")
    assert body.get("status") != "applied"


def test_resolve_await_marker_missing_shell_payload() -> None:
    events = _collect(
        resolve_await_marker({AWAIT_SHELL_KEY: True}, auto_apply=False)
    )
    body = json.loads(events[0][1] or "{}")
    assert body.get("status") == "failed"
    assert "missing shell" in (body.get("error") or "")
    assert not any(e[0].get("type") == "await_approval" for e in events)


def test_resolve_await_marker_delegates_patch_yolo() -> None:
    parsed = {
        AWAIT_PATCH_KEY: True,
        "patch": {
            "id": "p_res",
            "path": "a.txt",
            "unified_diff": "diff",
            "is_new_file": True,
            "is_delete": False,
        },
    }

    class FakePatch:
        status = PatchStatus.APPLIED
        path = "a.txt"
        unified_diff = "diff"
        is_new_file = True
        is_delete = False
        error = None
        applied_hunks = None

    with patch(
        "agent_window.agent.gate_hooks.decide_patch",
        new=AsyncMock(return_value=FakePatch()),
    ):
        events = _collect(resolve_await_marker(parsed, auto_apply=True))

    assert not any(e[0].get("type") == "await_approval" for e in events)
    assert any(e[0].get("type") == "diff" and e[0].get("status") == "applied" for e in events)
    final = [e for e in events if e[0].get("type") == "_result"]
    assert final
    assert json.loads(final[0][1] or "{}").get("status") == "applied"
    assert json.loads(final[0][1] or "{}").get("status") != "rejected"
