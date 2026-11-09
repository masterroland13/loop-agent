"""Negative tests: search must not return .env or credential-file bytes.

Covers workspace grep, the grep tool, session-search aliases, and shell rg.
Explicit read_file/cat of a named .env is a different boundary and is not asserted.
auto_compress stays off; C6/C7/N2 are not started.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.services.workspace import WorkspaceError


_SECRET_FILES = (
    (".env", "ENV_DOTFILE_MARKER"),
    (".env.local", "ENV_LOCAL_MARKER"),
    (".env.bak", "ENV_BAK_MARKER"),
    (".ENV", "ENV_CASE_MARKER"),
    ("prod.env", "ENV_SUFFIX_MARKER"),
    ("credentials.json", "CREDENTIALS_MARKER"),
    ("nested/.env", "ENV_NESTED_MARKER"),
)


def _bind_app_data(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    data = root / "app-data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(data))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(data))
    monkeypatch.setattr(
        "agent_window.services.session_search.settings.app_data_dir",
        str(data),
    )
    monkeypatch.setattr(
        "agent_window.services.session_transcript.settings.app_data_dir",
        str(data),
    )
    return data


@pytest.fixture
def app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = _bind_app_data(monkeypatch, tmp_path)
    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    yield data
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None


@pytest.fixture
def ws(app_data: Path, tmp_path: Path) -> Path:
    from agent_window.services import shell as shell_mod
    from agent_window.services.workspace import clear_workspace_root, set_workspace_root

    root = tmp_path / "ws"
    root.mkdir()
    set_workspace_root(str(root))
    shell_mod._shells.clear()
    yield root
    clear_workspace_root()
    shell_mod._shells.clear()


@pytest.fixture
def session(app_data: Path):
    from agent_window.models import get_sessionmaker, init_db
    from agent_window.services.storage import create_session

    init_db()
    db = get_sessionmaker()()
    try:
        created = create_session(db, title="env-search")
        yield created
    finally:
        db.close()


def _write_secret_tree(root: Path) -> list[str]:
    markers: list[str] = []
    for rel, marker in _SECRET_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker + "\n", encoding="utf-8")
        markers.append(marker)
    return markers


def _leaked(blob: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker in blob]


def _excerpts(found: dict) -> str:
    """Hit text only. The query field echoes the caller's marker and is not a leak."""
    return "\n".join(str(hit.get("excerpt") or "") for hit in found.get("hits") or [])


def test_workspace_grep_skips_env_and_credential_names(ws: Path) -> None:
    """Default workspace grep returns ordinary notes and not secret filenames."""
    from agent_window.services.workspace import grep_search

    markers = _write_secret_tree(ws)
    (ws / "notes.txt").write_text("GREP_VISIBLE_MARKER\n", encoding="utf-8")
    found = grep_search("MARKER", path=".")
    blob = json.dumps(found, ensure_ascii=False)
    assert "GREP_VISIBLE_MARKER" in blob
    assert _leaked(blob, markers) == []


def test_workspace_grep_env_glob_still_skips_dotenv(ws: Path) -> None:
    """A glob that names .env still must not return that file's bytes."""
    from agent_window.services.workspace import grep_search

    markers = _write_secret_tree(ws)
    found = grep_search("MARKER", path=".", glob=".env")
    blob = json.dumps(found, ensure_ascii=False)
    assert _leaked(blob, markers) == []
    assert found["matches"] == []


def test_grep_tool_skips_dotenv(ws: Path) -> None:
    """The agent grep tool must not return .env bytes."""
    from agent_window.tools.fs_tools import grep_tool

    markers = _write_secret_tree(ws)
    (ws / "notes.txt").write_text("GREP_TOOL_VISIBLE_MARKER\n", encoding="utf-8")
    raw = asyncio.run(grep_tool({"pattern": "MARKER", "path": "."}))
    assert "GREP_TOOL_VISIBLE_MARKER" in raw
    assert _leaked(raw, markers) == []
    assert "error" not in json.loads(raw)


def _turns(session) -> Path:
    from agent_window.services.storage import get_session_path

    turns = get_session_path(session) / "turns"
    turns.mkdir(parents=True, exist_ok=True)
    return turns


def test_session_search_ignores_symlink_alias_of_turns_dotenv(session) -> None:
    """A turns/ alias that points at turns/.env must not be searchable."""
    from agent_window.services.session_search import search_session_records

    turns = _turns(session)
    (turns / "note.txt").write_text("VISIBLE_SYMLINK_SPILL\n", encoding="utf-8")
    env_file = turns / ".env"
    marker = "ENV_SYMLINK_ALIAS_MARKER"
    env_file.write_text(marker + "\n", encoding="utf-8")
    (turns / "alias.txt").symlink_to(env_file)

    visible = search_session_records(session, "VISIBLE_SYMLINK_SPILL")
    assert visible["hit_count"] >= 1
    assert "VISIBLE_SYMLINK_SPILL" in _excerpts(visible)
    hidden = search_session_records(session, marker)
    assert marker not in _excerpts(hidden)
    assert hidden["hit_count"] == 0
    names = [Path(hit.get("path") or "").name.lower() for hit in hidden["hits"]]
    assert all(not (name.startswith(".env") or name.endswith(".env")) for name in names)


def test_session_search_explicit_alias_path_ignores_dotenv(session) -> None:
    """path=turns/alias.txt must not read a symlink to turns/.env."""
    from agent_window.services.session_search import SessionSearchError, search_session_records

    turns = _turns(session)
    marker = "ENV_EXPLICIT_ALIAS_MARKER"
    env_file = turns / ".env"
    env_file.write_text(marker + "\n", encoding="utf-8")
    (turns / "alias.txt").symlink_to(env_file)
    try:
        found = search_session_records(session, marker, path="turns/alias.txt")
    except SessionSearchError as exc:
        assert exc.code == "PATH_FORBIDDEN"
        assert marker not in str(exc)
        return
    assert marker not in _excerpts(found)
    assert found["hit_count"] == 0


def test_session_search_ignores_hardlink_alias_of_turns_dotenv(session) -> None:
    """A hard link under an allowed name must not expose turns/.env bytes."""
    from agent_window.services.session_search import search_session_records

    turns = _turns(session)
    (turns / "note.txt").write_text("VISIBLE_HARDLINK_SPILL\n", encoding="utf-8")
    env_file = turns / ".env"
    marker = "ENV_HARDLINK_ALIAS_MARKER"
    env_file.write_text(marker + "\n", encoding="utf-8")
    alias = turns / "alias.txt"
    try:
        os.link(env_file, alias)
    except OSError as exc:
        pytest.skip(f"hard links are not available on this filesystem: {exc}")

    visible = search_session_records(session, "VISIBLE_HARDLINK_SPILL")
    assert "VISIBLE_HARDLINK_SPILL" in _excerpts(visible)
    hidden = search_session_records(session, marker)
    assert marker not in _excerpts(hidden)
    assert hidden["hit_count"] == 0


def test_session_search_ignores_symlink_to_outside_dotenv(session, tmp_path: Path) -> None:
    """A turns/ symlink to an outside .env must not be readable."""
    from agent_window.services.session_search import SessionSearchError, search_session_records

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "ENV_OUTSIDE_SYMLINK_MARKER"
    secret = outside / ".env"
    secret.write_text(marker + "\n", encoding="utf-8")
    turns = _turns(session)
    (turns / "note.txt").write_text("VISIBLE_OUTSIDE_SPILL\n", encoding="utf-8")
    (turns / "alias.txt").symlink_to(secret)

    visible = search_session_records(session, "VISIBLE_OUTSIDE_SPILL")
    assert "VISIBLE_OUTSIDE_SPILL" in _excerpts(visible)
    try:
        hidden = search_session_records(session, marker)
    except SessionSearchError as exc:
        assert exc.code == "PATH_FORBIDDEN"
        assert marker not in str(exc)
    else:
        assert marker not in _excerpts(hidden)
        assert hidden["hit_count"] == 0
    try:
        explicit = search_session_records(session, marker, path="turns/alias.txt")
    except SessionSearchError as exc:
        assert exc.code == "PATH_FORBIDDEN"
        assert marker not in str(exc)
    else:
        assert marker not in _excerpts(explicit)
        assert explicit["hit_count"] == 0
    assert secret.read_text(encoding="utf-8") == marker + "\n"


def test_shell_rg_explicit_dotenv_is_not_searched(ws: Path) -> None:
    """Shell rg of .env is still search and must not print that file."""
    from agent_window.services.shell import create_shell_proposal, run_shell_command

    if shutil.which("rg") is None:
        pytest.skip(
            "rg is not installed, so the shell search bypass cannot be executed. "
            "Workspace grep_search is asserted in the other tests in this file."
        )
    marker = "ENV_SHELL_RG_FILE_MARKER"
    (ws / ".env").write_text(marker + "\n", encoding="utf-8")
    (ws / "notes.txt").write_text("RG_VISIBLE\n", encoding="utf-8")
    try:
        item = create_shell_proposal(["rg", "-n", "ENV_SHELL_RG_FILE", ".env"])
    except WorkspaceError as exc:
        assert exc.code in {"PATH_ESCAPE", "NOT_ALLOWED", "BLOCKED"}
        assert marker not in str(exc)
        return
    asyncio.run(run_shell_command(item))
    assert marker not in (item.stdout or "")
    assert marker not in (item.stderr or "")


def test_shell_rg_hidden_walk_does_not_return_dotenv(ws: Path) -> None:
    """rg --hidden over the workspace must not return .env bytes."""
    from agent_window.services.shell import create_shell_proposal, run_shell_command

    if shutil.which("rg") is None:
        pytest.skip(
            "rg is not installed, so the hidden-file shell search cannot be executed. "
            "Workspace grep_search is asserted in the other tests in this file."
        )
    marker = "ENV_SHELL_RG_HIDDEN_MARKER"
    (ws / ".env").write_text(marker + "\n", encoding="utf-8")
    (ws / "notes.txt").write_text("RG_HIDDEN_VISIBLE\n", encoding="utf-8")
    try:
        item = create_shell_proposal(["rg", "--hidden", "-n", "ENV_SHELL_RG_HIDDEN", "."])
    except WorkspaceError as exc:
        assert exc.code in {"PATH_ESCAPE", "NOT_ALLOWED", "BLOCKED"}
        assert marker not in str(exc)
        return
    asyncio.run(run_shell_command(item))
    assert marker not in (item.stdout or "")
    assert marker not in (item.stderr or "")
