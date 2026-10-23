"""App data dir is the user directory unless APP_DATA_DIR is set."""

from pathlib import Path

import pytest

from agent_window.config import Settings
from agent_window.services.workspace import (
    WorkspaceError,
    get_workspace_root,
    require_root,
)


def test_unset_app_data_dir_is_user_dir_not_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    got = Settings(_env_file=None)
    user_dir = tmp_path / ".local" / "share" / "loop-agent"
    assert got.app_data_dir == str(user_dir)
    assert got.app_data_dir != "./data"
    assert Path(got.app_data_dir) != (cwd / "data")


def test_blank_app_data_dir_falls_back_to_user_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APP_DATA_DIR", "   ")
    got = Settings(_env_file=None)
    user_dir = tmp_path / ".local" / "share" / "loop-agent"
    assert got.app_data_dir == str(user_dir)
    assert got.app_data_dir.strip() != ""
    assert "./data" not in got.app_data_dir


def test_tilde_app_data_dir_expands_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APP_DATA_DIR", "~/custom-data")
    got = Settings(_env_file=None)
    assert got.app_data_dir == str(home / "custom-data")
    assert "~" not in got.app_data_dir
    assert got.app_data_dir != "~/custom-data"


def test_relative_app_data_dir_stays_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APP_DATA_DIR", "./data")
    got = Settings(_env_file=None)
    assert got.app_data_dir == "./data"
    assert got.app_data_dir != str(tmp_path / ".local" / "share" / "loop-agent")


def test_app_data_dir_env_overrides_user_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    custom = tmp_path / "custom-data"
    monkeypatch.setenv("APP_DATA_DIR", str(custom))
    got = Settings(_env_file=None)
    assert got.app_data_dir == str(custom)
    assert ".local/share/loop-agent" not in got.app_data_dir.replace("\\", "/")


def test_fresh_data_dir_has_no_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setattr("agent_window.services.workspace.settings.app_data_dir", str(fresh))
    assert get_workspace_root() is None
    assert not (fresh / "workspace.json").exists()
    with pytest.raises(WorkspaceError) as raised:
        require_root()
    assert raised.value.code == "NO_WORKSPACE"
    assert raised.value.code != "PATH_ESCAPE"
