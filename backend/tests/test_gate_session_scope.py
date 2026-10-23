"""Phase 3: pending gate cancel/list scoped by session_id."""

from __future__ import annotations

from agent_window.config import settings
from agent_window.services.attachment_context import use_attachment_session
from agent_window.services.memory import (
    _memories,
    cancel_pending_memories,
    create_memory_proposal,
    list_pending_memories,
)
from agent_window.services.patches import (
    _patches,
    cancel_pending_patches,
    create_patch_from_content,
    list_pending,
)
from agent_window.services.session_turns import cancel_turn, end_turn, try_begin_turn
from agent_window.services.shell import (
    _shells,
    cancel_pending_shells,
    create_shell_proposal,
    list_pending_shells,
)
from agent_window.services.workspace import set_workspace_root


def _clear_gates() -> None:
    _patches.clear()
    _shells.clear()
    _memories.clear()


def _bind_workspace(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    set_workspace_root(str(tmp_path))
    _clear_gates()


def test_cancel_pending_patches_scoped_by_session(tmp_path, monkeypatch) -> None:
    _bind_workspace(tmp_path, monkeypatch)

    with use_attachment_session("sess-a"):
        create_patch_from_content("a.txt", "hello-a\n")
    with use_attachment_session("sess-b"):
        create_patch_from_content("b.txt", "hello-b\n")

    assert len(list_pending()) == 2
    assert len(list_pending("sess-a")) == 1
    assert len(list_pending("sess-b")) == 1
    assert list_pending("sess-a")[0]["path"] == "a.txt"
    assert list_pending("sess-a")[0]["session_id"] == "sess-a"
    assert list_pending("sess-a")[0]["path"] != "b.txt"

    n = cancel_pending_patches("sess-a")
    assert n == 1
    assert n != 2
    assert list_pending("sess-a") == []
    assert len(list_pending("sess-b")) == 1
    assert list_pending("sess-b")[0]["path"] == "b.txt"


def test_cancel_turn_does_not_wipe_other_session_gates(tmp_path, monkeypatch) -> None:
    _bind_workspace(tmp_path, monkeypatch)

    with use_attachment_session("sess-a"):
        create_patch_from_content("a.py", "print(1)\n")
        create_shell_proposal(["ls", "-la"])
        create_memory_proposal("pref-a", mode="replace", target="user")
    with use_attachment_session("sess-b"):
        create_patch_from_content("b.py", "print(2)\n")
        create_shell_proposal(["pwd"])
        create_memory_proposal("pref-b", mode="replace", target="user")

    try_begin_turn("sess-a")
    cancelled = cancel_turn("sess-a")
    assert cancelled is True
    end_turn("sess-a")

    assert list_pending("sess-a") == []
    assert list_pending_shells("sess-a") == []
    assert list_pending_memories("sess-a") == []
    assert len(list_pending("sess-b")) == 1
    assert len(list_pending_shells("sess-b")) == 1
    assert len(list_pending_memories("sess-b")) == 1
    assert list_pending("sess-b")[0]["session_id"] == "sess-b"
    assert list_pending_shells("sess-b")[0]["session_id"] == "sess-b"
    assert list_pending_memories("sess-b")[0]["session_id"] == "sess-b"


def test_cancel_pending_without_session_still_clears_all(tmp_path, monkeypatch) -> None:
    _bind_workspace(tmp_path, monkeypatch)

    with use_attachment_session("s1"):
        create_patch_from_content("x.txt", "x\n")
    with use_attachment_session("s2"):
        create_patch_from_content("y.txt", "y\n")

    n = cancel_pending_patches()
    assert n == 2
    assert list_pending() == []
    assert cancel_pending_shells() == 0
    assert cancel_pending_memories() == 0
