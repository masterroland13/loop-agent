"""Desktop shell: user data dir, no copied workspace, window close stops children."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agent_window.host.session import (
    _find_node,
    backend_env,
    prepare_data_dir,
    run_until_window_exits,
)


def test_backend_env_overrides_dev_data_dir(tmp_path: Path) -> None:
    data = tmp_path / "user-data"
    env = backend_env({"APP_DATA_DIR": "./data", "PATH": "/usr/bin"}, data)
    assert env["APP_DATA_DIR"] == str(data)
    assert env["APP_DATA_DIR"] != "./data"
    assert env["PATH"] == "/usr/bin"
    assert env["LOOP_SHELL"] == "1"


def test_shell_backend_ignores_dotenv_secrets(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "LLM_API_KEY=secret-from-dotenv\nLLM_BASE_URL=https://example.test/v1\n",
        encoding="utf-8",
    )
    data = tmp_path / "user-data"
    src = Path(__file__).resolve().parents[1] / "src"
    env = backend_env({"PATH": "/usr/bin"}, data)
    env["PYTHONPATH"] = str(src)
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    code = (
        "from agent_window.config import Settings\n"
        "s = Settings()\n"
        "print(repr(s.llm_api_key))\n"
        "print(s.llm_base_url)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = proc.stdout.strip().splitlines()
    assert lines[-2] == "''"
    assert lines[-1] == "https://llm-cn.gameye.ai/v1"
    assert "secret-from-dotenv" not in proc.stdout
    assert "example.test" not in proc.stdout

    plain = {"PATH": "/usr/bin", "PYTHONPATH": str(src)}
    leaked = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=plain,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "secret-from-dotenv" in leaked.stdout
    assert "example.test" in leaked.stdout
    assert "''" not in leaked.stdout.splitlines()[-2]


def test_prepare_data_dir_does_not_seed_workspace(tmp_path: Path) -> None:
    fresh = prepare_data_dir(tmp_path / "fresh")
    assert fresh.is_dir()
    assert not (fresh / "workspace.json").exists()

    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "workspace.json").write_text('{"root": "/tmp/proj"}', encoding="utf-8")
    prepare_data_dir(kept)
    text = (kept / "workspace.json").read_text(encoding="utf-8")
    assert "/tmp/proj" in text
    assert "agent window" not in text


def test_window_exit_stops_backend_and_passes_user_data_dir(tmp_path: Path) -> None:
    seen = tmp_path / "seen.txt"
    data = tmp_path / "user-data"
    env = backend_env({"APP_DATA_DIR": "./data", "PATH": "/usr/bin"}, data)
    env["SEEN"] = str(seen)
    backend = [
        sys.executable,
        "-c",
        "import os, time, pathlib; pathlib.Path(os.environ['SEEN']).write_text(os.environ['APP_DATA_DIR']); time.sleep(30)",
    ]
    window = [sys.executable, "-c", "import time; time.sleep(0.3)"]
    code = run_until_window_exits([backend], window, env=env, cwd=tmp_path)
    assert code == 0
    written = seen.read_text(encoding="utf-8")
    assert written == str(data)
    assert written != "./data"
    assert seen.exists()


def test_spawned_settings_follow_shell_data_dir_not_dotenv(tmp_path: Path) -> None:
    data = tmp_path / "user-data"
    env = backend_env(os.environ, data)
    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from agent_window.config import Settings; print(Settings().app_data_dir)",
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    line = proc.stdout.strip().splitlines()[-1]
    assert line == str(data)
    assert line != "./data"
    assert "backend/data" not in line


def test_find_node_skips_windows_shim(monkeypatch, tmp_path: Path) -> None:
    linux_node = tmp_path / ".nvm" / "versions" / "node" / "v1" / "bin" / "node"
    linux_node.parent.mkdir(parents=True)
    linux_node.write_bytes(b"\x7fELF")
    shim = tmp_path / ".local" / "bin" / "node"
    shim.parent.mkdir(parents=True)
    shim.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: str(shim))
    found = _find_node()
    assert found == str(linux_node)
    assert found != str(shim)


def test_agent_loop_does_not_import_the_shell_host() -> None:
    import agent_window.agent.loop as loop

    text = Path(loop.__file__).read_text(encoding="utf-8")
    assert "agent_window.host" not in text
    assert "run_shell" not in text
