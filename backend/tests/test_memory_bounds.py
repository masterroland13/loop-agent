"""A1d: USER.md hard char limit + session freeze snapshot."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_window.config import settings


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "app_data_dir", str(tmp_path))
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    from agent_window.services.memory import clear_memory_snapshot

    clear_memory_snapshot()
    yield tmp_path
    clear_memory_snapshot()


def test_replace_within_limit_creates_and_applies(data_dir: Path) -> None:
    from agent_window.services.memory import (
        USER_MD_CHAR_LIMIT,
        create_memory_proposal,
        decide_memory,
        get_memory,
        read_user_md,
    )

    body = "User prefers concise Chinese replies."
    assert len(body) < USER_MD_CHAR_LIMIT
    assert len(body) + 1 <= USER_MD_CHAR_LIMIT  # trailing newline on final

    item = create_memory_proposal(body, mode="replace")
    assert item.id
    assert get_memory(item.id) is not None
    assert item.status.value == "pending"
    assert body in item.content
    assert "MEMORY_FULL" not in (item.error or "")

    applied = asyncio.run(decide_memory(item.id, "apply"))
    assert applied.status.value == "applied"
    assert applied.status.value != "failed"
    disk = read_user_md()
    assert body in disk
    assert "too long" not in disk


def test_append_that_would_exceed_raises_memory_full(data_dir: Path) -> None:
    from agent_window.services.memory import (
        USER_MD_CHAR_LIMIT,
        create_memory_proposal,
        list_pending_memories,
        read_user_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    existing = "x" * (USER_MD_CHAR_LIMIT - 10)
    write_user_md(existing)
    before = read_user_md()
    assert before == existing
    assert len(before) <= USER_MD_CHAR_LIMIT

    with pytest.raises(WorkspaceError) as ei:
        create_memory_proposal("more facts that push over the cap", mode="append")
    assert ei.value.code == "MEMORY_FULL"
    assert ei.value.code != "TOO_LARGE"
    assert "replace" in str(ei.value).lower()
    assert read_user_md() == before
    assert list_pending_memories() == []


def test_replace_too_long_raises_memory_full(data_dir: Path) -> None:
    from agent_window.services.memory import (
        USER_MD_CHAR_LIMIT,
        create_memory_proposal,
        list_pending_memories,
        read_user_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    write_user_md("keep me\n")
    before = read_user_md()
    too_long = "y" * (USER_MD_CHAR_LIMIT + 50)
    assert len(too_long) > USER_MD_CHAR_LIMIT

    with pytest.raises(WorkspaceError) as ei:
        create_memory_proposal(too_long, mode="replace")
    assert ei.value.code == "MEMORY_FULL"
    assert "replace" in str(ei.value).lower() or "merged" in str(ei.value).lower()
    assert read_user_md() == before
    assert list_pending_memories() == []


def test_freeze_stays_until_force_or_clear(data_dir: Path) -> None:
    from agent_window.services.memory import (
        clear_memory_snapshot,
        freeze_user_md_for_session,
        get_frozen_user_md,
        write_user_md,
    )

    write_user_md("frozen-v1\n")
    sid = "sess-freeze-1"
    frozen = freeze_user_md_for_session(sid)
    assert "frozen-v1" in frozen
    assert "frozen-v2" not in frozen

    write_user_md("frozen-v2-longer-live\n")
    still = get_frozen_user_md(sid)
    assert still == frozen
    assert "frozen-v1" in still
    assert "frozen-v2" not in still

    forced = freeze_user_md_for_session(sid, force=True)
    assert "frozen-v2" in forced
    assert "frozen-v1" not in forced

    write_user_md("frozen-v3\n")
    clear_memory_snapshot(sid)
    anew = get_frozen_user_md(sid)
    assert "frozen-v3" in anew
    assert "frozen-v2" not in anew


def test_clear_all_snapshots_then_new_freeze_sees_disk(data_dir: Path) -> None:
    from agent_window.services.memory import (
        clear_memory_snapshot,
        get_frozen_user_md,
        write_user_md,
    )

    write_user_md("alpha\n")
    a = get_frozen_user_md("s-a")
    b = get_frozen_user_md("s-b")
    assert "alpha" in a and "alpha" in b

    write_user_md("beta\n")
    assert "alpha" in get_frozen_user_md("s-a")
    assert "beta" not in get_frozen_user_md("s-a")

    clear_memory_snapshot()
    refreshed = get_frozen_user_md("s-a")
    assert "beta" in refreshed
    assert "alpha" not in refreshed


def test_memory_status_includes_capacity(data_dir: Path) -> None:
    from agent_window.services.memory import USER_MD_CHAR_LIMIT, memory_status, write_user_md

    write_user_md("abc\n")
    st = memory_status()
    assert st["chars"] == len("abc\n")
    assert st["limit"] == USER_MD_CHAR_LIMIT
    assert st["usage_ratio"] == pytest.approx(st["chars"] / st["limit"])
    assert st["chars"] != 0
    assert st["usage_ratio"] < 1.0


def test_system_prompt_uses_frozen_not_live(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.services.memory import clear_memory_snapshot, get_frozen_user_md, write_user_md
    from agent_window.services.workspace import set_workspace_root

    set_workspace_root(str(data_dir))
    write_user_md("ONLY_FROZEN_MARKER\n")
    sid = "prompt-sess"
    get_frozen_user_md(sid)
    write_user_md("ONLY_LIVE_MARKER_SHOULD_NOT_APPEAR\n")

    from agent_window.api.routes import _system_prompt

    prompt = _system_prompt(sid)
    assert "ONLY_FROZEN_MARKER" in prompt
    assert "ONLY_LIVE_MARKER_SHOULD_NOT_APPEAR" not in prompt
    assert "frozen this session" in prompt
    assert "ONLY_FROZEN_MARKER" in prompt

    # Non-session path sees live disk
    live_prompt = _system_prompt()
    assert "ONLY_LIVE_MARKER_SHOULD_NOT_APPEAR" in live_prompt
    assert "ONLY_FROZEN_MARKER" not in live_prompt

    clear_memory_snapshot()


def test_user_md_char_limit_setting_clamps(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
    from agent_window.services.memory import get_user_md_char_limit

    assert load_agent_settings()["user_md_char_limit"] == 1375
    assert get_user_md_char_limit() == 1375

    saved = save_agent_settings({"user_md_char_limit": 100})
    assert saved["user_md_char_limit"] == 500
    assert get_user_md_char_limit() == 500
    assert get_user_md_char_limit() != 100

    saved = save_agent_settings({"user_md_char_limit": 99999})
    assert saved["user_md_char_limit"] == 8000
    assert get_user_md_char_limit() == 8000
    assert get_user_md_char_limit() != 99999
