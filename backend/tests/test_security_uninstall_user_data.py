"""Negative tests: loop uninstall must not delete user data or the workspace.

Calls uninstall_shell_assets with tmp paths only. Does not invoke `loop uninstall`
and does not touch the real home directory. auto_compress stays off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_window.host.session import (
    ShellError,
    shell_data_dir,
    shell_install_dir,
    uninstall_shell_assets,
)


def _seed_install(dest: Path) -> None:
    (dest / "dist").mkdir(parents=True, exist_ok=True)
    (dest / "dist" / "index.html").write_text("<html>loop</html>", encoding="utf-8")
    (dest / "loop-window").write_text("window", encoding="utf-8")
    (dest / "venv").mkdir(exist_ok=True)
    (dest / "venv" / "pyvenv.cfg").write_text("home = /tmp\n", encoding="utf-8")


def _require_under(tmp_path: Path, *paths: Path) -> None:
    root = tmp_path.resolve()
    for path in paths:
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise AssertionError(f"refusing to touch a path outside tmp: {path}") from exc


def _changed(expected: dict[Path, str]) -> list[str]:
    bad: list[str] = []
    for path, text in expected.items():
        if not path.is_file():
            bad.append(f"missing {path}")
            continue
        if path.read_text(encoding="utf-8") != text:
            bad.append(f"changed {path}")
    return bad


def test_uninstall_keeps_user_data_and_workspace_nested_in_install(tmp_path: Path) -> None:
    """User data and the workspace survive even when they live inside the install tree."""
    install = tmp_path / "install"
    data = install / "user-data"
    workspace = install / "workspace"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    sibling = tmp_path / "untouched.txt"
    _require_under(tmp_path, install, data, workspace, bin_dir, apps, sibling)
    _seed_install(install)
    transcript = data / "users" / "local-user" / "sessions" / "s1" / "transcript.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript_text = '{"type":"user","content":"USER_DATA_MARKER"}\n'
    transcript.write_text(transcript_text, encoding="utf-8")
    profiles = data / "model_profiles.json"
    profiles_text = '{"profiles":[]}\n'
    profiles.write_text(profiles_text, encoding="utf-8")
    user_md = data / "users" / "local-user" / "USER.md"
    user_md_text = "USER_MD_MARKER\n"
    user_md.write_text(user_md_text, encoding="utf-8")
    notes = workspace / "notes.txt"
    notes.parent.mkdir(parents=True)
    notes_text = "WORKSPACE_MARKER\n"
    notes.write_text(notes_text, encoding="utf-8")
    sibling_text = "UNTOUCHED_MARKER\n"
    sibling.write_text(sibling_text, encoding="utf-8")

    try:
        uninstall_shell_assets(install, bin_dir, apps, data)
    except ShellError:
        pass

    assert _changed(
        {
            transcript: transcript_text,
            profiles: profiles_text,
            user_md: user_md_text,
            notes: notes_text,
            sibling: sibling_text,
        }
    ) == []


def test_uninstall_refuses_when_install_symlink_resolves_to_user_data(tmp_path: Path) -> None:
    """An install path that resolves to the user-data directory is not removed."""
    real = tmp_path / "same"
    link = tmp_path / "install-link"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    _require_under(tmp_path, real, link, bin_dir, apps)
    _seed_install(real)
    keep = real / "transcript.jsonl"
    keep_text = "SAME_PATH_MARKER\n"
    keep.write_text(keep_text, encoding="utf-8")
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ShellError) as exc:
        uninstall_shell_assets(link, bin_dir, apps, real)
    assert "没有卸载" in str(exc.value)
    assert _changed({keep: keep_text}) == []
    assert (real / "dist" / "index.html").is_file()
    assert link.is_symlink()


def test_uninstall_keeps_parent_user_data_when_install_is_nested(tmp_path: Path) -> None:
    """Removing an install directory that sits inside user data leaves the other files."""
    data = tmp_path / "data"
    install = data / "loop-agent"
    workspace = tmp_path / "workspace"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    _require_under(tmp_path, data, install, workspace, bin_dir, apps)
    _seed_install(install)
    keep = data / "keep.txt"
    keep_text = "ANCESTOR_MARKER\n"
    keep.write_text(keep_text, encoding="utf-8")
    notes = workspace / "notes.txt"
    notes.parent.mkdir(parents=True)
    notes_text = "WORKSPACE_MARKER\n"
    notes.write_text(notes_text, encoding="utf-8")

    removed = uninstall_shell_assets(install, bin_dir, apps, data)
    assert not install.exists()
    assert data.resolve() not in [path.resolve() for path in removed]
    assert workspace.resolve() not in [path.resolve() for path in removed]
    assert _changed({keep: keep_text, notes: notes_text}) == []
    assert data.is_dir()


def test_uninstall_does_not_follow_symlink_to_external_user_data(tmp_path: Path) -> None:
    """A symlink inside the install tree must not cause the link target to be deleted."""
    install = tmp_path / "install"
    external = tmp_path / "external-data"
    data = tmp_path / "separate-data"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    _require_under(tmp_path, install, external, data, bin_dir, apps)
    _seed_install(install)
    external.mkdir()
    external_keep = external / "keep.txt"
    external_text = "EXTERNAL_MARKER\n"
    external_keep.write_text(external_text, encoding="utf-8")
    (install / "data-link").symlink_to(external, target_is_directory=True)
    data.mkdir()
    separate = data / "keep.txt"
    separate_text = "SEPARATE_MARKER\n"
    separate.write_text(separate_text, encoding="utf-8")

    uninstall_shell_assets(install, bin_dir, apps, data)
    assert _changed({external_keep: external_text, separate: separate_text}) == []
    assert external.is_dir()
    assert data.is_dir()


def test_uninstall_launcher_removal_does_not_wipe_user_data_dir(tmp_path: Path) -> None:
    """If the launcher path is inside user data, only that marked file is removed."""
    from agent_window.host.session import LAUNCHER_MARK

    install = tmp_path / "install"
    data = tmp_path / "data"
    bin_dir = data
    apps = tmp_path / "applications"
    _require_under(tmp_path, install, data, apps)
    _seed_install(install)
    data.mkdir()
    transcript = data / "transcript.jsonl"
    transcript_text = "BIN_DIR_MARKER\n"
    transcript.write_text(transcript_text, encoding="utf-8")
    (data / "loop").write_text(f"#!/bin/sh\n{LAUNCHER_MARK}\n", encoding="utf-8")

    uninstall_shell_assets(install, bin_dir, apps, data)
    assert not (data / "loop").exists()
    assert _changed({transcript: transcript_text}) == []
    assert data.is_dir()


def test_default_install_dir_does_not_contain_user_data() -> None:
    """The default install directory is not the user-data directory and does not contain it."""
    install = shell_install_dir()
    data = shell_data_dir()
    assert install.resolve() != data.resolve()
    try:
        data.resolve().relative_to(install.resolve())
    except ValueError:
        nested = False
    else:
        nested = True
    assert nested is False
