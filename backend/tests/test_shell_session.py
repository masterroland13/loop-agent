"""Desktop shell: user data dir, no copied workspace, window close stops children."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_window.config import default_user_data_dir
from agent_window.host.session import (
    ShellError,
    backend_env,
    checkout_root,
    install_shell_assets,
    launch_plan,
    prepare_data_dir,
    run_until_window_exits,
    shell_applications_dir,
    shell_bin_dir,
    shell_commands,
    shell_install_dir,
    shell_port_is_free,
    uninstall_shell_assets,
)
from agent_window.services.shell import python_for_package


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
    pid_file = tmp_path / "backend.pid"
    data = tmp_path / "user-data"
    env = backend_env({"APP_DATA_DIR": "./data", "PATH": "/usr/bin"}, data)
    env["SEEN"] = str(seen)
    env["PID"] = str(pid_file)
    backend = [
        sys.executable,
        "-c",
        "import os, time, pathlib; pathlib.Path(os.environ['SEEN']).write_text(os.environ['APP_DATA_DIR']); pathlib.Path(os.environ['PID']).write_text(str(os.getpid())); time.sleep(30)",
    ]
    window = [sys.executable, "-c", "import time; time.sleep(0.3)"]
    code = run_until_window_exits([backend], window, env=env, cwd=tmp_path)
    assert code == 0
    written = seen.read_text(encoding="utf-8")
    assert written == str(data)
    assert written != "./data"
    assert seen.exists()
    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_shell_port_is_free_detects_a_listener() -> None:
    import socket

    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    port = int(busy.getsockname()[1])
    assert shell_port_is_free(port=port) is False
    busy.close()
    assert shell_port_is_free(port=port) is True
    assert port != 8000


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


def test_install_dir_is_separate_from_user_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LOOP_INSTALL_DIR", raising=False)
    install = shell_install_dir()
    data = Path(default_user_data_dir())
    assert install == tmp_path / ".local" / "lib" / "loop-agent"
    assert data == tmp_path / ".local" / "share" / "loop-agent"
    assert install != data
    monkeypatch.delenv("LOOP_BIN_DIR", raising=False)
    command_dir = shell_bin_dir()
    assert command_dir == tmp_path / ".local" / "bin"
    assert command_dir != install
    assert command_dir != data
    monkeypatch.setenv("LOOP_INSTALL_DIR", str(tmp_path / "custom"))
    overridden = shell_install_dir()
    assert overridden == tmp_path / "custom"
    assert "share/loop-agent" not in str(overridden)
    monkeypatch.setenv("LOOP_BIN_DIR", str(tmp_path / "commands"))
    assert shell_bin_dir() == tmp_path / "commands"
    assert "share/loop-agent" not in str(shell_bin_dir())
    monkeypatch.delenv("LOOP_APPLICATIONS_DIR", raising=False)
    apps = shell_applications_dir()
    assert apps == tmp_path / ".local" / "share" / "applications"
    assert apps != data
    assert "loop-agent" not in str(apps)
    monkeypatch.setenv("LOOP_APPLICATIONS_DIR", str(tmp_path / "menu"))
    assert shell_applications_dir() == tmp_path / "menu"


def _seed_checkout(repo: Path) -> None:
    (repo / "dist" / "assets").mkdir(parents=True)
    (repo / "dist" / "index.html").write_text("<title>Loop Agent</title>", encoding="utf-8")
    (repo / "dist" / "assets" / "app.js").write_text("app", encoding="utf-8")
    (repo / "shell").mkdir()
    (repo / "shell" / "loop-window").write_bytes(b"\x7fELF")
    package = repo / "backend" / "src" / "agent_window"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("MARKER = 'installed-copy'\n", encoding="utf-8")
    site = repo / "backend" / ".venv" / "lib" / "python3.13" / "site-packages"
    site.mkdir(parents=True)
    (repo / "backend" / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (repo / "backend" / ".venv" / "bin").mkdir()
    (repo / "backend" / ".venv" / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (site / "_editable_impl_loop_agent_backend.pth").write_text(
        "/home/caapap/agent window/backend/src\n",
        encoding="utf-8",
    )
    (repo / "public").mkdir()
    (repo / "public" / "ouroboros-logo.png").write_bytes(b"\x89PNG")


def test_install_copies_ui_and_window_not_workspace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    (repo / "backend" / "data").mkdir(parents=True)
    (repo / "backend" / "data" / "workspace.json").write_text(
        '{"root": "/home/caapap/agent window"}',
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    dest = install_shell_assets(
        repo, tmp_path / "lib" / "loop-agent", bin_dir=bin_dir, applications_dir=apps
    )
    page = (dest / "dist" / "index.html").read_text(encoding="utf-8")
    assert page.startswith("<title>Loop Agent</title>")
    assert "agent window" not in page
    assert (dest / "loop-window").read_bytes().startswith(b"\x7fELF")
    copied = (dest / "venv" / "lib" / "python3.13" / "site-packages" / "agent_window" / "__init__.py")
    assert "installed-copy" in copied.read_text(encoding="utf-8")
    pointers = list(dest.rglob("_editable_impl_*.pth"))
    assert pointers == []
    assert "agent window" not in copied.read_text(encoding="utf-8")
    source_pointer = (
        repo / "backend" / ".venv" / "lib" / "python3.13" / "site-packages" / "_editable_impl_loop_agent_backend.pth"
    )
    assert "agent window" in source_pointer.read_text(encoding="utf-8")
    command = (bin_dir / "loop").read_text(encoding="utf-8")
    python = dest / "venv" / "bin" / "python"
    assert "# loop-agent launcher" in command
    assert str(python) in command
    assert "agent window" not in command
    assert "-m agent_window.cli" in command
    assert "cli.main" not in command
    desktop = (apps / "loop-agent.desktop").read_text(encoding="utf-8")
    assert "# loop-agent desktop" in desktop
    assert 'Exec="' + str(bin_dir / "loop") + '" shell' in desktop
    assert "Name=Loop Agent" in desktop
    assert "Terminal=false" in desktop
    assert "agent window" not in desktop
    assert str(dest / "ouroboros-logo.png") in desktop
    assert (dest / "ouroboros-logo.png").read_bytes() == b"\x89PNG"
    assert not (apps / "workspace.json").exists()
    assert not (dest / "workspace.json").exists()
    assert not (dest / "backend").exists()
    assert (repo / "backend" / "data" / "workspace.json").is_file()


def test_install_refuses_an_installed_package(tmp_path: Path) -> None:
    dest = tmp_path / "lib"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    installed = (
        tmp_path / "venv" / "lib" / "python3.13" / "site-packages" / "agent_window" / "host" / "session.py"
    )
    installed.parent.mkdir(parents=True)
    installed.write_text("x", encoding="utf-8")
    with pytest.raises(ShellError) as blocked:
        checkout_root(installed)
    assert "已经是装好的程序" in str(blocked.value)
    with pytest.raises(ShellError) as blocked_install:
        install_shell_assets(tmp_path / "venv", dest, bin_dir=bin_dir, applications_dir=apps)
    assert "已经是装好的程序" in str(blocked_install.value)
    assert not dest.exists()
    assert not (bin_dir / "loop").exists()
    assert not (apps / "loop-agent.desktop").exists()


def test_install_refuses_missing_frontend(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    package = repo / "backend" / "src" / "agent_window"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    dest = tmp_path / "lib"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    with pytest.raises(ShellError) as blocked:
        install_shell_assets(repo, dest, bin_dir=bin_dir, applications_dir=apps)
    assert "npm run build" in str(blocked.value)
    assert "已经是装好的程序" not in str(blocked.value)
    assert not (dest / "workspace.json").exists()
    assert not (dest / "dist").exists()
    assert not (bin_dir / "loop").exists()
    assert not (apps / "loop-agent.desktop").exists()


def test_install_refuses_a_foreign_loop_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    dest = tmp_path / "lib" / "loop-agent"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "loop").write_text("#!/bin/sh\necho other\n", encoding="utf-8")
    with pytest.raises(ShellError) as blocked:
        install_shell_assets(
            repo, dest, bin_dir=bin_dir, applications_dir=tmp_path / "applications"
        )
    assert "别的 loop 命令" in str(blocked.value)
    assert (bin_dir / "loop").read_text(encoding="utf-8") == "#!/bin/sh\necho other\n"
    assert not dest.exists()


def test_install_replaces_our_loop_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    dest = tmp_path / "lib" / "loop-agent"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "loop").write_text(
        "#!/bin/sh\n# loop-agent launcher\nexec /old/python -m agent_window.cli.main \"$@\"\n",
        encoding="utf-8",
    )
    install_shell_assets(
        repo, dest, bin_dir=bin_dir, applications_dir=tmp_path / "applications"
    )
    command = (bin_dir / "loop").read_text(encoding="utf-8")
    assert str(dest / "venv" / "bin" / "python") in command
    assert "/old/python" not in command
    assert "# loop-agent launcher" in command


def test_install_refuses_a_foreign_desktop_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    dest = tmp_path / "lib" / "loop-agent"
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "loop-agent.desktop").write_text(
        "[Desktop Entry]\nName=Other\n",
        encoding="utf-8",
    )
    with pytest.raises(ShellError) as blocked:
        install_shell_assets(
            repo, dest, bin_dir=tmp_path / "bin", applications_dir=apps
        )
    assert "别的桌面启动项" in str(blocked.value)
    assert (apps / "loop-agent.desktop").read_text(encoding="utf-8") == (
        "[Desktop Entry]\nName=Other\n"
    )
    assert not dest.exists()


def test_uninstall_removes_program_keeps_user_data(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    dest = tmp_path / "lib" / "loop-agent"
    bin_dir = tmp_path / "bin"
    apps = tmp_path / "applications"
    data = tmp_path / "share" / "loop-agent"
    data.mkdir(parents=True)
    (data / "workspace.json").write_text(
        '{"root": "/tmp/notes"}',
        encoding="utf-8",
    )
    (repo / "backend" / "data").mkdir(parents=True)
    (repo / "backend" / "data" / "workspace.json").write_text(
        '{"root": "/home/caapap/agent window"}',
        encoding="utf-8",
    )
    install_shell_assets(repo, dest, bin_dir=bin_dir, applications_dir=apps)
    removed = uninstall_shell_assets(dest, bin_dir, apps, data)
    assert dest in removed
    assert not dest.exists()
    assert not (bin_dir / "loop").exists()
    assert not (apps / "loop-agent.desktop").exists()
    assert (data / "workspace.json").read_text(encoding="utf-8") == '{"root": "/tmp/notes"}'
    assert (repo / "backend" / "data" / "workspace.json").is_file()
    assert data.exists()


def test_uninstall_leaves_a_foreign_loop_command(tmp_path: Path) -> None:
    dest = tmp_path / "lib" / "loop-agent"
    dest.mkdir(parents=True)
    (dest / "dist").mkdir()
    (dest / "dist" / "index.html").write_text("ok", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "loop").write_text("#!/bin/sh\necho other\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    (data / "keep.txt").write_text("stay", encoding="utf-8")
    uninstall_shell_assets(dest, bin_dir, tmp_path / "applications", data)
    assert not dest.exists()
    assert (bin_dir / "loop").read_text(encoding="utf-8") == "#!/bin/sh\necho other\n"
    assert (data / "keep.txt").read_text(encoding="utf-8") == "stay"


def test_uninstall_refuses_a_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    with pytest.raises(ShellError) as blocked:
        uninstall_shell_assets(repo, tmp_path / "bin", tmp_path / "applications", tmp_path / "data")
    assert "仓库" in str(blocked.value)
    assert (repo / "backend" / "src" / "agent_window" / "__init__.py").is_file()


def test_checkout_root_finds_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_checkout(repo)
    nested = repo / "backend" / "src" / "agent_window" / "host" / "session.py"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("x", encoding="utf-8")
    assert checkout_root(nested) == repo
    assert checkout_root(nested) != tmp_path / "lib"


def test_shell_window_uses_install_python(tmp_path: Path) -> None:
    install = tmp_path / "install"
    (install / "dist").mkdir(parents=True)
    (install / "dist" / "index.html").write_text("ok", encoding="utf-8")
    binary = install / "loop-window"
    binary.write_text("window", encoding="utf-8")
    python = install / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    checkout = "/home/caapap/agent window/backend/src"
    backend, window, env, cwd = launch_plan(
        install,
        tmp_path / "data",
        {"PATH": "/usr/bin", "PYTHONPATH": checkout},
    )
    joined = " ".join(backend + window)
    assert "preview-server" not in joined
    assert "node" not in joined
    assert backend[0] == str(python)
    assert checkout not in backend[0]
    assert "PYTHONPATH" not in env
    assert cwd == install
    assert cwd != tmp_path / "data"
    assert window[0] == str(binary)
    assert window[1] == "http://127.0.0.1:8765/"
    assert "8766" not in window[1]
    assert env["LOOP_STATIC_DIR"] == str(install / "dist")
    assert env["APP_DATA_DIR"] == str(tmp_path / "data")


def test_shell_commands_require_an_install(tmp_path: Path) -> None:
    with pytest.raises(ShellError) as blocked:
        shell_commands(tmp_path)
    assert "loop install" in str(blocked.value)
    assert not (tmp_path / "workspace.json").exists()


def test_package_python_follows_the_venv_that_contains_it(tmp_path: Path) -> None:
    installed = tmp_path / "venv" / "lib" / "python3.13" / "site-packages" / "agent_window" / "services" / "shell.py"
    installed.parent.mkdir(parents=True)
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("installed", encoding="utf-8")
    checkout = tmp_path / "backend" / "src" / "agent_window" / "services" / "shell.py"
    checkout.parent.mkdir(parents=True)
    repo_python = tmp_path / "backend" / ".venv" / "bin" / "python"
    repo_python.parent.mkdir(parents=True)
    repo_python.write_text("checkout", encoding="utf-8")
    assert python_for_package(installed) == str(venv_python)
    assert python_for_package(checkout) == str(repo_python)
    assert python_for_package(installed) != str(repo_python)


def test_agent_loop_does_not_import_the_shell_host() -> None:
    import agent_window.agent.loop as loop

    text = Path(loop.__file__).read_text(encoding="utf-8")
    assert "agent_window.host" not in text
    assert "run_shell" not in text
