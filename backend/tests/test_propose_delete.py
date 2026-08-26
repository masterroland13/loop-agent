# -*- coding: utf-8 -*-
"""propose_delete: pending gate, apply unlinks, reject keeps file, path escape rejected."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.services.patches import (
    PatchStatus,
    _patches,
    create_patch_for_delete,
    decide_patch,
)
from agent_window.services.workspace import WorkspaceError, set_workspace_root
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY, propose_delete_tool


@pytest.fixture
def ws(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    _patches.clear()
    set_workspace_root(str(tmp_path))
    yield tmp_path
    _patches.clear()


def test_propose_delete_creates_pending(ws: Path) -> None:
    target = ws / "doomed.txt"
    target.write_text("bye\n", encoding="utf-8")

    patch = create_patch_for_delete("doomed.txt")
    assert patch.status == PatchStatus.PENDING
    assert patch.is_delete is True
    assert patch.is_new_file is False
    assert patch.path == "doomed.txt"
    assert "bye" in patch.old_content
    assert patch.new_content == ""
    assert target.exists()  # not deleted yet
    assert target.read_text(encoding="utf-8") == "bye\n"


def test_apply_removes_file(ws: Path) -> None:
    target = ws / "gone.txt"
    target.write_text("x\n", encoding="utf-8")
    patch = create_patch_for_delete("gone.txt")
    decided = asyncio.run(decide_patch(patch.id, "apply"))
    assert decided.status == PatchStatus.APPLIED
    assert not target.exists()
    assert decided.status != PatchStatus.REJECTED


def test_reject_keeps_file(ws: Path) -> None:
    target = ws / "keep.txt"
    target.write_text("keep me\n", encoding="utf-8")
    patch = create_patch_for_delete("keep.txt")
    decided = asyncio.run(decide_patch(patch.id, "reject"))
    assert decided.status == PatchStatus.REJECTED
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "keep me\n"
    assert decided.status != PatchStatus.APPLIED


def test_path_escape_rejected(ws: Path) -> None:
    before = set(_patches.keys())
    with pytest.raises(WorkspaceError) as ei:
        create_patch_for_delete("../outside.txt")
    assert ei.value.code == "PATH_ESCAPE"
    assert ei.value.code != "OK"
    assert set(_patches.keys()) == before


def test_missing_file_rejected(ws: Path) -> None:
    with pytest.raises(WorkspaceError) as ei:
        create_patch_for_delete("no-such.txt")
    assert ei.value.code == "NOT_FOUND"
    assert not any(p.path == "no-such.txt" for p in _patches.values())


def test_propose_delete_tool_await_marker(ws: Path) -> None:
    target = ws / "tool.txt"
    target.write_text("z\n", encoding="utf-8")
    raw = asyncio.run(propose_delete_tool({"path": "tool.txt"}))
    data = json.loads(raw)
    assert data.get(AWAIT_PATCH_KEY) is True
    assert data["patch"]["is_delete"] is True
    assert data["patch"]["status"] == "pending"
    assert "error" not in data
    assert target.exists()