"""M0: MEMORY.md track + propose_memory target=user|memory."""

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


def test_memory_md_replace_and_apply_isolated_from_user(data_dir: Path) -> None:
    from agent_window.services.memory import (
        create_memory_proposal,
        decide_memory,
        read_memory_md,
        read_user_md,
        write_user_md,
    )

    write_user_md("User prefers Chinese.\n")
    item = create_memory_proposal(
        "Prefer pytest -q in this repo.",
        mode="replace",
        target="memory",
    )
    assert item.target == "memory"
    assert item.target != "user"
    applied = asyncio.run(decide_memory(item.id, "apply"))
    assert applied.status.value == "applied"
    assert "pytest -q" in read_memory_md()
    assert "User prefers Chinese" in read_user_md()
    assert "pytest -q" not in read_user_md()


def test_memory_md_full_does_not_touch_user(data_dir: Path) -> None:
    from agent_window.services.memory import (
        MEMORY_MD_CHAR_LIMIT,
        create_memory_proposal,
        list_pending_memories,
        read_memory_md,
        read_user_md,
        write_memory_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    write_user_md("keep-user\n")
    write_memory_md("m" * (MEMORY_MD_CHAR_LIMIT - 5))
    before_user = read_user_md()
    before_mem = read_memory_md()

    with pytest.raises(WorkspaceError) as ei:
        create_memory_proposal("overflow-memory-track", mode="append", target="memory")
    assert ei.value.code == "MEMORY_FULL"
    assert "MEMORY.md" in str(ei.value)
    assert "target=memory" in str(ei.value)
    assert read_user_md() == before_user
    assert read_memory_md() == before_mem
    assert list_pending_memories() == []


def test_memory_md_freeze_independent(data_dir: Path) -> None:
    from agent_window.services.memory import (
        clear_memory_snapshot,
        freeze_memory_md_for_session,
        get_frozen_memory_md,
        get_frozen_user_md,
        write_memory_md,
        write_user_md,
    )

    write_user_md("user-v1\n")
    write_memory_md("mem-v1\n")
    sid = "sess-dual"
    assert "user-v1" in get_frozen_user_md(sid)
    assert "mem-v1" in freeze_memory_md_for_session(sid)

    write_user_md("user-v2\n")
    write_memory_md("mem-v2\n")
    assert "user-v1" in get_frozen_user_md(sid)
    assert "mem-v1" in get_frozen_memory_md(sid)
    assert "mem-v2" not in get_frozen_memory_md(sid)

    clear_memory_snapshot(sid)
    assert "user-v2" in get_frozen_user_md(sid)
    assert "mem-v2" in get_frozen_memory_md(sid)


def test_system_prompt_injects_guidance_and_both_tracks(
    data_dir: Path,
) -> None:
    from agent_window.api.routes import _system_prompt
    from agent_window.services.memory import (
        clear_memory_snapshot,
        get_frozen_memory_md,
        get_frozen_user_md,
        write_memory_md,
        write_user_md,
    )
    from agent_window.services.workspace import set_workspace_root

    set_workspace_root(str(data_dir))
    write_user_md("USER_ONLY_MARKER\n")
    write_memory_md("MEMORY_ONLY_MARKER\n")
    sid = "prompt-dual"
    get_frozen_user_md(sid)
    get_frozen_memory_md(sid)
    write_user_md("USER_LIVE_HIDDEN\n")
    write_memory_md("MEMORY_LIVE_HIDDEN\n")

    prompt = _system_prompt(sid)
    assert "Memory guidance" in prompt
    assert "target=memory" in prompt
    assert "USER_ONLY_MARKER" in prompt
    assert "MEMORY_ONLY_MARKER" in prompt
    assert "USER_LIVE_HIDDEN" not in prompt
    assert "MEMORY_LIVE_HIDDEN" not in prompt
    assert "MEMORY.md (frozen this session" in prompt
    assert "USER.md (frozen this session" in prompt

    live = _system_prompt()
    assert "USER_LIVE_HIDDEN" in live
    assert "MEMORY_LIVE_HIDDEN" in live
    clear_memory_snapshot()


def test_default_target_user_back_compat(data_dir: Path) -> None:
    from agent_window.services.memory import create_memory_proposal, decide_memory, read_user_md

    item = create_memory_proposal("prefers dark mode", mode="replace")
    assert item.target == "user"
    asyncio.run(decide_memory(item.id, "apply"))
    assert "dark mode" in read_user_md()


def test_memory_md_char_limit_setting_clamps(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
    from agent_window.services.memory import get_memory_md_char_limit

    assert load_agent_settings()["memory_md_char_limit"] == 2200
    assert get_memory_md_char_limit() == 2200
    saved = save_agent_settings({"memory_md_char_limit": 50})
    assert saved["memory_md_char_limit"] == 500
    assert get_memory_md_char_limit() == 500
    saved = save_agent_settings({"memory_md_char_limit": 99999})
    assert saved["memory_md_char_limit"] == 8000
    assert get_memory_md_char_limit() != 99999
