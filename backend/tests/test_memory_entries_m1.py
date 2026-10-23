"""Mem M1: entry ops add/replace/remove + batch operations + § separator."""

from __future__ import annotations

import asyncio
import json
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


def test_parse_join_roundtrip_and_legacy_single(data_dir: Path) -> None:
    from agent_window.services.memory import ENTRY_SEP, join_memory_entries, parse_memory_entries

    assert parse_memory_entries("") == []
    assert parse_memory_entries("   ") == []
    legacy = "User prefers Chinese.\nKeep concise."
    assert parse_memory_entries(legacy) == [legacy]
    assert "§" not in join_memory_entries([legacy])

    joined = join_memory_entries(["alpha", "beta block\nline2", "gamma"])
    assert ENTRY_SEP in joined
    parts = parse_memory_entries(joined)
    assert parts == ["alpha", "beta block\nline2", "gamma"]
    assert "delta" not in parts
    assert len(parts) != 1


def test_add_replace_remove_and_duplicate(data_dir: Path) -> None:
    from agent_window.services.memory import (
        create_memory_proposal,
        decide_memory,
        join_memory_entries,
        parse_memory_entries,
        read_user_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    write_user_md("prefers tea\n")
    add = create_memory_proposal("likes dark mode", action="add", target="user")
    assert add.mode == "add"
    assert "→" in add.op_summary
    asyncio.run(decide_memory(add.id, "apply"))
    disk = read_user_md()
    entries = parse_memory_entries(disk)
    assert "prefers tea" in entries
    assert "likes dark mode" in entries
    assert len(entries) == 2

    with pytest.raises(WorkspaceError) as dup:
        create_memory_proposal("likes dark mode", action="add")
    assert dup.value.code == "DUPLICATE"
    assert dup.value.code != "MEMORY_FULL"

    with pytest.raises(WorkspaceError) as miss:
        create_memory_proposal(action="remove", old_text="no such fact")
    assert miss.value.code == "NOT_FOUND"

    write_user_md(join_memory_entries(["alpha one", "alpha two", "beta"]))
    with pytest.raises(WorkspaceError) as amb:
        create_memory_proposal(action="remove", old_text="alpha")
    assert amb.value.code == "AMBIGUOUS"

    rep = create_memory_proposal(
        "beta preferred",
        action="replace",
        old_text="beta",
        target="user",
    )
    assert rep.mode == "replace"
    assert "beta preferred" in rep.content
    asyncio.run(decide_memory(rep.id, "apply"))
    after = parse_memory_entries(read_user_md())
    assert "beta preferred" in after
    assert "beta" not in after

    rem = create_memory_proposal(action="remove", old_text="alpha one")
    asyncio.run(decide_memory(rem.id, "apply"))
    final = parse_memory_entries(read_user_md())
    assert "alpha one" not in final
    assert "alpha two" in final
    assert "beta preferred" in final


def test_batch_operations_atomic_budget(data_dir: Path) -> None:
    from agent_window.services.memory import (
        USER_MD_CHAR_LIMIT,
        create_memory_proposal,
        decide_memory,
        list_pending_memories,
        parse_memory_entries,
        read_user_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    write_user_md("keep-me\n")
    item = create_memory_proposal(
        target="user",
        operations=[
            {"action": "add", "content": "fact-a"},
            {"action": "add", "content": "fact-b"},
            {"action": "replace", "old_text": "keep-me", "content": "kept-renamed"},
        ],
    )
    assert item.mode == "operations"
    assert "3 ops" in item.op_summary
    asyncio.run(decide_memory(item.id, "apply"))
    entries = parse_memory_entries(read_user_md())
    assert entries == ["kept-renamed", "fact-a", "fact-b"]
    assert "keep-me" not in entries

    huge = "z" * (USER_MD_CHAR_LIMIT - 5)
    write_user_md(huge + "\n")
    before = read_user_md()
    with pytest.raises(WorkspaceError) as ei:
        create_memory_proposal(
            target="user",
            operations=[
                {"action": "add", "content": "push-over"},
                {"action": "add", "content": "also"},
            ],
        )
    assert ei.value.code == "MEMORY_FULL"
    assert "current_entries" in str(ei.value) or "MEMORY_FULL" in str(ei.value)
    assert read_user_md() == before
    assert list_pending_memories() == []


def test_memory_target_entry_ops(data_dir: Path) -> None:
    from agent_window.services.memory import (
        create_memory_proposal,
        decide_memory,
        parse_memory_entries,
        read_memory_md,
        write_memory_md,
    )

    write_memory_md("pytest -q\n")
    item = create_memory_proposal(
        "use PYTHONPATH=src",
        action="add",
        target="memory",
    )
    assert item.target == "memory"
    asyncio.run(decide_memory(item.id, "apply"))
    entries = parse_memory_entries(read_memory_md())
    assert "pytest -q" in entries
    assert "use PYTHONPATH=src" in entries
    assert read_memory_md() != "pytest -q\n" or len(entries) > 1


def test_propose_memory_tool_actions(data_dir: Path) -> None:
    from agent_window.services.memory import decide_memory, parse_memory_entries, read_user_md, write_user_md
    from agent_window.tools.memory_tools import AWAIT_MEMORY_KEY, propose_memory_tool

    write_user_md("base\n")

    async def _run() -> None:
        raw = await propose_memory_tool({"action": "add", "content": "tool-added", "target": "user"})
        payload = json.loads(raw)
        assert payload.get(AWAIT_MEMORY_KEY) is True
        assert "error" not in payload
        mid = payload["memory"]["id"]
        assert payload["memory"]["mode"] == "add"
        await decide_memory(mid, "apply")
        assert "tool-added" in parse_memory_entries(read_user_md())

        raw_rm = await propose_memory_tool({"action": "remove", "old_text": "tool-added"})
        assert "error" not in json.loads(raw_rm)
        await decide_memory(json.loads(raw_rm)["memory"]["id"], "apply")
        assert "tool-added" not in parse_memory_entries(read_user_md())

        raw_bad = await propose_memory_tool({"action": "remove", "old_text": "missing"})
        bad = json.loads(raw_bad)
        assert bad.get("code") == "NOT_FOUND"
        assert AWAIT_MEMORY_KEY not in bad

        raw_batch = await propose_memory_tool(
            {
                "target": "user",
                "operations": [
                    {"action": "add", "content": "batch-1"},
                    {"action": "add", "content": "batch-2"},
                ],
            }
        )
        batch = json.loads(raw_batch)
        assert batch.get(AWAIT_MEMORY_KEY) is True
        assert batch["memory"]["mode"] == "operations"
        await decide_memory(batch["memory"]["id"], "apply")
        entries = parse_memory_entries(read_user_md())
        assert "batch-1" in entries and "batch-2" in entries

    asyncio.run(_run())


def test_m0_whole_file_still_works(data_dir: Path) -> None:
    from agent_window.services.memory import (
        ENTRY_SEP,
        create_memory_proposal,
        decide_memory,
        read_user_md,
    )

    item = create_memory_proposal("whole profile", mode="replace")
    assert item.mode == "replace"
    assert item.op_summary == "replace"
    asyncio.run(decide_memory(item.id, "apply"))
    assert "whole profile" in read_user_md()
    assert ENTRY_SEP not in read_user_md()

    app = create_memory_proposal("extra line", mode="append")
    assert app.mode == "add"  # append aliases add
    asyncio.run(decide_memory(app.id, "apply"))
    body = read_user_md()
    assert "whole profile" in body and "extra line" in body
    assert ENTRY_SEP in body


def test_legacy_blank_lines_dedupe_and_normalize_sep(data_dir: Path) -> None:
    """Dogfood A5/B: blank-line files must split, reject dups, write §."""
    from agent_window.services.memory import (
        ENTRY_SEP,
        create_memory_proposal,
        decide_memory,
        parse_memory_entries,
        read_user_md,
        write_user_md,
    )
    from agent_window.services.workspace import WorkspaceError

    write_user_md("测试记忆写入\n\nUser prefers light theme in the IDE.\n")
    assert ENTRY_SEP not in read_user_md()
    assert parse_memory_entries(read_user_md()) == [
        "测试记忆写入",
        "User prefers light theme in the IDE.",
    ]

    with pytest.raises(WorkspaceError) as ei:
        create_memory_proposal(
            "User prefers light theme in the IDE.",
            action="add",
            target="user",
        )
    assert ei.value.code == "DUPLICATE"

    with pytest.raises(WorkspaceError) as ej:
        create_memory_proposal(
            "same\n\nsame\n\nsame",
            mode="replace",
            target="user",
        )
    assert ej.value.code == "DUPLICATE"

    add = create_memory_proposal("User prefers short Chinese replies.", action="add")
    asyncio.run(decide_memory(add.id, "apply"))
    body = read_user_md()
    assert ENTRY_SEP in body
    assert "§" in body
    assert "short Chinese" in body
    assert body.count("light theme") == 1
