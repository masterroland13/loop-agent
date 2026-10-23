"""Shell argv normalization: bare python → venv / python3."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_normalize_bare_python_uses_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.services import shell as shell_mod

    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(shell_mod, "resolve_loop_python", lambda: str(venv_py))

    out = shell_mod.normalize_shell_argv(["python", "-m", "pytest", "-q"])
    assert out[0] == str(venv_py)
    assert out[1:] == ["-m", "pytest", "-q"]
    assert out[0] != "python"


def test_normalize_leaves_python3_and_paths() -> None:
    from agent_window.services.shell import normalize_shell_argv

    assert normalize_shell_argv(["python3", "x.py"])[0] == "python3"
    assert normalize_shell_argv(["/usr/bin/python", "x.py"])[0] == "/usr/bin/python"
    assert normalize_shell_argv(["ls", "-la"])[0] == "ls"


def test_normalize_falls_back_to_python3(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.services import shell as shell_mod

    monkeypatch.setattr(shell_mod, "resolve_loop_python", lambda: "python3")
    out = shell_mod.normalize_shell_argv(["python", "scripts/a.py"])
    assert out == ["python3", "scripts/a.py"]
    assert out[0] != "python"


def test_create_shell_proposal_rewrites_display(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_window.config import settings
    from agent_window.services import shell as shell_mod
    from agent_window.services.workspace import set_workspace_root

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    set_workspace_root(str(tmp_path))
    shell_mod._shells.clear()

    venv_py = tmp_path / "fake-python"
    venv_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(shell_mod, "resolve_loop_python", lambda: str(venv_py))

    item = shell_mod.create_shell_proposal(["python", "-m", "pytest"], cwd=".")
    assert item.argv[0] == str(venv_py)
    assert "python -m" not in item.command_display or str(venv_py) in item.command_display
    assert item.argv[0] != "python"
