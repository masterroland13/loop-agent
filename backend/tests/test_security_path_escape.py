"""Negative tests for workspace and user-data path escape.

These tests state the boundary. They do not change product code.
auto_compress stays off; C6/C7/N2 are not started.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.services.workspace import WorkspaceError


_DENY = {"PATH_ESCAPE", "NOT_ALLOWED", "BLOCKED", "INVALID_ARGV", "INVALID_PATH"}


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
    from agent_window.services import patches as patch_mod
    from agent_window.services import shell as shell_mod
    from agent_window.services.workspace import clear_workspace_root, set_workspace_root

    root = tmp_path / "ws"
    root.mkdir()
    set_workspace_root(str(root))
    shell_mod._shells.clear()
    patch_mod._patches.clear()
    yield root
    clear_workspace_root()
    shell_mod._shells.clear()
    patch_mod._patches.clear()


@pytest.fixture
def session(app_data: Path):
    from agent_window.models import get_sessionmaker, init_db
    from agent_window.services.storage import create_session

    init_db()
    db = get_sessionmaker()()
    try:
        created = create_session(db, title="path-escape")
        yield created
    finally:
        db.close()


def _leaked(blob: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker in blob]


def _shell_must_not_emit(argv: list[str], marker: str, *, cwd: str = ".") -> None:
    from agent_window.services.shell import create_shell_proposal, run_shell_command

    try:
        item = create_shell_proposal(list(argv), cwd=cwd)
    except WorkspaceError as exc:
        assert exc.code in _DENY
        assert marker not in str(exc)
        return
    asyncio.run(run_shell_command(item))
    emitted = "\n".join([item.stdout or "", item.stderr or "", item.error or ""])
    assert marker not in emitted


def test_grep_walk_does_not_return_symlink_file_outside_workspace(ws: Path, tmp_path: Path) -> None:
    """Directory grep must not return bytes reached through a file symlink."""
    from agent_window.services.workspace import grep_search

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "GREP_FILE_SYMLINK_MARKER"
    (outside / "secret.txt").write_text(marker + "\n", encoding="utf-8")
    (ws / "leak.txt").symlink_to(outside / "secret.txt")
    (ws / "notes.txt").write_text("GREP_FILE_VISIBLE_MARKER\n", encoding="utf-8")

    found = grep_search("MARKER", path=".")
    blob = json.dumps(found, ensure_ascii=False)
    assert "GREP_FILE_VISIBLE_MARKER" in blob
    assert _leaked(blob, [marker]) == []
    assert all(marker not in (hit.get("text") or "") for hit in found["matches"])


def test_grep_direct_symlink_path_does_not_return_outside_bytes(ws: Path, tmp_path: Path) -> None:
    """grep of the symlink path itself must not return the outside file."""
    from agent_window.services.workspace import grep_search

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "GREP_DIRECT_SYMLINK_MARKER"
    (outside / "secret.txt").write_text(marker + "\n", encoding="utf-8")
    (ws / "leak.txt").symlink_to(outside / "secret.txt")

    try:
        found = grep_search(marker, path="leak.txt")
    except WorkspaceError as exc:
        assert exc.code == "PATH_ESCAPE"
        assert marker not in str(exc)
    else:
        assert marker not in json.dumps(found, ensure_ascii=False)


def test_grep_walk_does_not_follow_symlink_directory(ws: Path, tmp_path: Path) -> None:
    """Directory grep must not walk a symlink that points at a directory outside."""
    from agent_window.services.workspace import grep_search

    outside = tmp_path / "outside-dir"
    outside.mkdir()
    marker = "GREP_DIR_SYMLINK_MARKER"
    (outside / "secret.txt").write_text(marker + "\n", encoding="utf-8")
    (ws / "linked").symlink_to(outside, target_is_directory=True)
    (ws / "notes.txt").write_text("GREP_DIR_VISIBLE_MARKER\n", encoding="utf-8")

    found = grep_search("MARKER", path=".")
    blob = json.dumps(found, ensure_ascii=False)
    assert "GREP_DIR_VISIBLE_MARKER" in blob
    assert marker not in blob

    try:
        direct = grep_search(marker, path="linked")
    except WorkspaceError as exc:
        assert exc.code == "PATH_ESCAPE"
        assert marker not in str(exc)
    else:
        assert marker not in json.dumps(direct, ensure_ascii=False)


def test_copy_tree_does_not_import_outside_symlink_bytes(ws: Path, tmp_path: Path) -> None:
    """Copying a workspace tree must not materialize a symlink's outside target."""
    from agent_window.services.workspace import copy_entry

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "COPY_SYMLINK_MARKER"
    secret = outside / "secret.txt"
    secret.write_text(marker, encoding="utf-8")
    bundle = ws / "bundle"
    bundle.mkdir()
    (bundle / "leak.txt").symlink_to(secret)
    (bundle / "ok.txt").write_text("COPY_VISIBLE", encoding="utf-8")

    try:
        copy_entry("bundle", "bundle-copy")
    except WorkspaceError as exc:
        assert exc.code == "PATH_ESCAPE"
        assert marker not in str(exc)
    else:
        leaked: list[str] = []
        for path in (ws / "bundle-copy").rglob("*"):
            if not path.is_file() and not path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if marker in text:
                leaked.append(str(path))
        assert leaked == []
    assert secret.read_text(encoding="utf-8") == marker
    assert secret.is_file()


def test_mutate_symlink_does_not_touch_outside_target(ws: Path, tmp_path: Path) -> None:
    """Read, write, delete, patch, and mkdir through a symlink stay inside the workspace."""
    from agent_window.services.patches import create_patch_from_replace
    from agent_window.services.workspace import (
        delete_entry,
        list_directory,
        mkdir_directory,
        read_file,
        read_text_file,
        write_text_file,
    )

    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "MUTATION_SYMLINK_MARKER"
    secret = outside / "secret.txt"
    secret.write_text(marker, encoding="utf-8")
    (ws / "leak.txt").symlink_to(secret)
    (ws / "linkdir").symlink_to(outside, target_is_directory=True)

    listed = json.dumps(list_directory("."), ensure_ascii=False)
    assert marker not in listed

    for action in (
        lambda: read_text_file("leak.txt"),
        lambda: read_file("leak.txt"),
        lambda: write_text_file("leak.txt", "overwritten"),
        lambda: delete_entry("leak.txt"),
        lambda: create_patch_from_replace("leak.txt", marker, "overwritten"),
        lambda: mkdir_directory("linkdir/child"),
        lambda: write_text_file("linkdir/child.txt", "overwritten"),
    ):
        with pytest.raises(WorkspaceError) as exc:
            action()
        assert exc.value.code == "PATH_ESCAPE"
        assert marker not in str(exc.value)

    assert secret.read_text(encoding="utf-8") == marker
    assert secret.is_file()
    assert not (outside / "child").exists()
    assert not (outside / "child.txt").exists()


@pytest.mark.parametrize("binary", ["cat", "head", "tail"])
def test_shell_reader_rejects_absolute_path_outside_workspace(
    binary: str, ws: Path, tmp_path: Path
) -> None:
    """Whitelisted readers must not print a file outside the workspace."""
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} is not on PATH, so this argv escape cannot be shown")
    secret = tmp_path / "outside-abs.txt"
    marker = f"SHELL_ABS_{binary.upper()}_MARKER"
    secret.write_text(marker + "\n", encoding="utf-8")
    _shell_must_not_emit([binary, str(secret)], marker)
    assert secret.read_text(encoding="utf-8") == marker + "\n"


def test_shell_cat_rejects_parent_relative_path(ws: Path, tmp_path: Path) -> None:
    """cat ../outside must not print the outside file."""
    if shutil.which("cat") is None:
        pytest.skip("cat is not on PATH, so this argv escape cannot be shown")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "SHELL_PARENT_MARKER"
    (outside / "secret.txt").write_text(marker + "\n", encoding="utf-8")
    _shell_must_not_emit(["cat", "../outside/secret.txt"], marker)
    assert (outside / "secret.txt").read_text(encoding="utf-8") == marker + "\n"


def test_shell_cat_rejects_symlink_inside_workspace(ws: Path, tmp_path: Path) -> None:
    """cat of a workspace symlink must not print the outside target."""
    if shutil.which("cat") is None:
        pytest.skip("cat is not on PATH, so this argv escape cannot be shown")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = "SHELL_SYMLINK_MARKER"
    secret = outside / "secret.txt"
    secret.write_text(marker + "\n", encoding="utf-8")
    (ws / "leak.txt").symlink_to(secret)
    _shell_must_not_emit(["cat", "leak.txt"], marker)
    assert secret.read_text(encoding="utf-8") == marker + "\n"


def test_shell_ls_rejects_outside_directory(ws: Path, tmp_path: Path) -> None:
    """ls of an absolute outside directory must not list those names."""
    if shutil.which("ls") is None:
        pytest.skip("ls is not on PATH, so this argv escape cannot be shown")
    outside = tmp_path / "outside-list"
    outside.mkdir()
    (outside / "LS_ESCAPE_NAME.txt").write_text("x", encoding="utf-8")
    _shell_must_not_emit(["ls", str(outside)], "LS_ESCAPE_NAME")
    assert (outside / "LS_ESCAPE_NAME.txt").is_file()


def test_shell_cwd_symlink_directory_stays_inside_workspace(ws: Path, tmp_path: Path) -> None:
    """A symlink directory cannot be used as the shell cwd."""
    from agent_window.services.shell import create_shell_proposal

    outside = tmp_path / "outside-cwd"
    outside.mkdir()
    (ws / "linkdir").symlink_to(outside, target_is_directory=True)
    try:
        item = create_shell_proposal(["pwd"], cwd="linkdir")
    except WorkspaceError as exc:
        assert exc.code == "PATH_ESCAPE"
        assert str(outside) not in str(exc)
        return
    resolved = Path(item.cwd_abs).resolve()
    try:
        resolved.relative_to(ws.resolve())
    except ValueError:
        raise AssertionError(f"shell cwd escaped workspace: {resolved}") from None
    assert resolved != outside.resolve()


def test_shell_cat_of_workspace_file_still_runs(ws: Path, tmp_path: Path) -> None:
    """cat of a normal workspace file still returns that file and not an outside one."""
    from agent_window.services.shell import ShellStatus, create_shell_proposal, run_shell_command

    if shutil.which("cat") is None:
        pytest.skip("cat is not on PATH")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("OUTSIDE_CAT_MARKER\n", encoding="utf-8")
    (ws / "inside.txt").write_text("INSIDE_CAT_MARKER\n", encoding="utf-8")
    item = create_shell_proposal(["cat", "inside.txt"])
    asyncio.run(run_shell_command(item))
    assert item.status == ShellStatus.DONE
    assert "INSIDE_CAT_MARKER" in item.stdout
    assert "OUTSIDE_CAT_MARKER" not in (item.stdout or "")
    assert "OUTSIDE_CAT_MARKER" not in (item.stderr or "")


def test_shell_rejects_python_inline_code(ws: Path, tmp_path: Path) -> None:
    """python -c is rejected before it can read an outside file."""
    from agent_window.services.shell import create_shell_proposal

    secret = tmp_path / "outside-py.txt"
    marker = "PYTHON_INLINE_MARKER"
    secret.write_text(marker, encoding="utf-8")
    with pytest.raises(WorkspaceError) as exc:
        create_shell_proposal(["python3", "-c", f"print(open({str(secret)!r}).read())"])
    assert exc.value.code in {"NOT_ALLOWED", "BLOCKED"}
    assert marker not in str(exc.value)
    assert secret.read_text(encoding="utf-8") == marker


def test_attachment_upload_rejects_absolute_data_path(session, tmp_path: Path) -> None:
    """An absolute session.data_path must not receive attachment bytes."""
    from agent_window.services.attachments import save_upload
    from agent_window.services.storage import get_session_path

    saved = save_upload(session, "ok.txt", b"ATTACHMENT_INSIDE_OK")
    root = get_session_path(session)
    assert saved["filename"] == "ok.txt"
    assert any(
        path.is_file() and path.read_bytes() == b"ATTACHMENT_INSIDE_OK"
        for path in root.rglob("*")
    )
    outside = tmp_path / "escaped-abs"
    session.data_path = str(outside)
    try:
        save_upload(session, "note.txt", b"ATTACHMENT_ABS_MARKER")
    except Exception as exc:
        assert "ATTACHMENT_ABS_MARKER" not in str(exc)
    assert not outside.exists()


def test_attachment_upload_rejects_relative_data_path(session, tmp_path: Path) -> None:
    """A data_path of ../ must not create files beside the user-data directory."""
    from agent_window.services.attachments import save_upload

    session.data_path = "../escaped-rel"
    escaped = tmp_path / "escaped-rel"
    try:
        save_upload(session, "note.txt", b"ATTACHMENT_REL_MARKER")
    except Exception as exc:
        assert "ATTACHMENT_REL_MARKER" not in str(exc)
    assert not escaped.exists()


def test_attachment_upload_rejects_symlinked_session_dir(session, tmp_path: Path) -> None:
    """Replacing the session directory with a symlink must not store uploads there."""
    from agent_window.services.attachments import save_upload
    from agent_window.services.storage import get_session_path

    save_upload(session, "ok.txt", b"ATTACHMENT_INSIDE_OK")
    session_dir = get_session_path(session)
    shutil.rmtree(session_dir)
    outside = tmp_path / "symlink-target"
    outside.mkdir()
    (outside / "preexisting.txt").write_text("PREEXISTING", encoding="utf-8")
    session_dir.symlink_to(outside, target_is_directory=True)
    try:
        save_upload(session, "note.txt", b"ATTACHMENT_SYMLINK_MARKER")
    except Exception as exc:
        assert "ATTACHMENT_SYMLINK_MARKER" not in str(exc)
    leaked = [
        str(path)
        for path in outside.rglob("*")
        if path.is_file() and b"ATTACHMENT_SYMLINK_MARKER" in path.read_bytes()
    ]
    assert leaked == []
    assert (outside / "preexisting.txt").read_text(encoding="utf-8") == "PREEXISTING"


def test_blob_read_rejects_absolute_data_path(session, tmp_path: Path) -> None:
    """read_session_blob must not return a file outside the user-data directory."""
    from agent_window.services.storage import get_session_path, read_session_blob

    inside = get_session_path(session) / "turns"
    inside.mkdir(parents=True)
    (inside / "ok.txt").write_text("BLOB_INSIDE_OK", encoding="utf-8")
    assert read_session_blob(session, "file:turns/ok.txt") == "BLOB_INSIDE_OK"

    outside = tmp_path / "blob-abs"
    outside.mkdir()
    marker = "BLOB_ABS_MARKER"
    (outside / "secret.txt").write_text(marker, encoding="utf-8")
    session.data_path = str(outside)
    try:
        body = read_session_blob(session, "file:secret.txt")
    except Exception as exc:
        assert marker not in str(exc)
    else:
        assert marker not in body
    assert (outside / "secret.txt").read_text(encoding="utf-8") == marker


def test_blob_read_rejects_symlinked_session_dir(session, tmp_path: Path) -> None:
    """A symlinked session directory must not make outside blobs readable."""
    from agent_window.services.storage import get_session_path, read_session_blob

    inside = get_session_path(session) / "turns"
    inside.mkdir(parents=True)
    (inside / "ok.txt").write_text("BLOB_INSIDE_OK", encoding="utf-8")
    assert read_session_blob(session, "file:turns/ok.txt") == "BLOB_INSIDE_OK"

    session_dir = get_session_path(session)
    shutil.rmtree(session_dir)
    outside = tmp_path / "blob-symlink"
    outside.mkdir()
    marker = "BLOB_SYMLINK_MARKER"
    (outside / "secret.txt").write_text(marker, encoding="utf-8")
    session_dir.symlink_to(outside, target_is_directory=True)
    try:
        body = read_session_blob(session, "file:secret.txt")
    except Exception as exc:
        assert marker not in str(exc)
    else:
        assert marker not in body


def test_session_search_refuses_absolute_data_path(session, tmp_path: Path) -> None:
    """Search must refuse a session whose data_path is an absolute outside directory."""
    from agent_window.services.session_search import SessionSearchError, search_session_records

    outside = tmp_path / "search-abs"
    outside.mkdir()
    marker = "SEARCH_ABSOLUTE_ESCAPE_MARKER"
    (outside / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": marker}) + "\n",
        encoding="utf-8",
    )
    session.data_path = str(outside)
    with pytest.raises(SessionSearchError) as exc:
        search_session_records(session, marker)
    assert exc.value.code == "PATH_FORBIDDEN"
    assert marker not in str(exc.value)


def test_session_search_refuses_symlinked_session_dir(session, tmp_path: Path) -> None:
    """Search must refuse a session directory that is a symlink to the outside."""
    from agent_window.services.session_search import SessionSearchError, search_session_records
    from agent_window.services.storage import get_session_path

    session_dir = get_session_path(session)
    shutil.rmtree(session_dir)
    outside = tmp_path / "search-symlink"
    outside.mkdir()
    marker = "SEARCH_SYMLINK_ESCAPE_MARKER"
    (outside / "transcript.jsonl").write_text(
        json.dumps({"type": "user", "content": marker}) + "\n",
        encoding="utf-8",
    )
    session_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SessionSearchError) as exc:
        search_session_records(session, marker)
    assert exc.value.code == "PATH_FORBIDDEN"
    assert marker not in str(exc.value)


@pytest.mark.skip(
    reason=(
        "browse_directory and create_browse_directory are the This PC picker. "
        "They are specified to list and create absolute host directories before "
        "a workspace is bound, so this file does not treat that picker as a "
        "workspace path-escape bug."
    )
)
def test_this_pc_picker_is_outside_workspace_sandbox() -> None:
    raise AssertionError("picker is intentionally not the workspace sandbox")


@pytest.mark.skip(
    reason=(
        "python/node/pytest may run a script that sits inside the workspace. "
        "The whitelist blocks inline -c/--eval, which is asserted separately, "
        "but those interpreters can still open any path the OS allows. "
        "An OS sandbox is out of scope for this draft. auto_compress stays off "
        "and C6/C7/N2 are not started. This case is not recorded as a pass."
    )
)
def test_interpreter_script_cannot_read_outside_workspace() -> None:
    raise AssertionError("interpreter filesystem sandbox is not claimed here")
