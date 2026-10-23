"""Process lifecycle for `loop shell`.

The window is the host. It does not import the agent loop. The backend it
starts uses the user data directory and does not receive a copied workspace.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping, Sequence

from agent_window.config import default_user_data_dir

BACKEND_PORT = 8765
UI_PORT = 8766


class ShellError(Exception):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def shell_data_dir() -> Path:
    override = os.environ.get("LOOP_SHELL_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(default_user_data_dir())


def prepare_data_dir(data_dir: Path) -> Path:
    """Create the data directory. Do not write or copy workspace.json."""
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def backend_env(inherited: Mapping[str, str], data_dir: Path) -> dict[str, str]:
    env = {key: value for key, value in inherited.items() if isinstance(value, str)}
    env["APP_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = "src"
    # Child imports Settings before reading this; skip backend/.env (dev keys).
    env["LOOP_SHELL"] = "1"
    return env


def start_process(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    log_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("ab")
    proc = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(env),
        stdout=log_handle or subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log_handle else subprocess.DEVNULL,
        start_new_session=True,
    )
    if log_handle is not None:
        log_handle.close()
    return proc


def stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=3)


def run_until_window_exits(
    commands: Sequence[Sequence[str]],
    window: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
) -> int:
    """Run side processes until `window` exits, then stop them."""
    procs = [start_process(cmd, env=env, cwd=cwd) for cmd in commands]
    win = start_process(window, env=env, cwd=cwd)
    try:
        code = win.wait()
        return int(code or 0)
    finally:
        stop_process(win)
        for proc in procs:
            stop_process(proc)


def _wait_http(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    return False


def _is_linux_executable(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _find_node() -> str:
    """Linux node. The ~/.local/bin/node shim runs Windows node.exe and drops WSL ports."""
    import shutil

    candidates = sorted(Path.home().glob(".nvm/versions/node/*/bin/node"))
    found = shutil.which("node")
    if found:
        candidates.append(Path(found))
    candidates.append(Path.home() / ".local" / "bin" / "node")
    for candidate in reversed(candidates):
        if candidate.is_file() and _is_linux_executable(candidate):
            return str(candidate)
    raise ShellError("找不到 Linux 版 node，无法打开界面。")


def ensure_window_binary(root: Path) -> Path:
    source = root / "shell" / "loop-window.c"
    binary = root / "shell" / "loop-window"
    if not source.is_file():
        raise ShellError(f"缺少窗口程序源码：{source}")
    if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary
    cflags = subprocess.check_output(
        ["pkg-config", "--cflags", "webkit2gtk-4.1"], text=True
    ).split()
    libs = subprocess.check_output(
        ["pkg-config", "--libs", "webkit2gtk-4.1"], text=True
    ).split()
    subprocess.check_call(
        ["gcc", "-O2", *cflags, str(source), "-o", str(binary), *libs]
    )
    return binary


def run_shell() -> int:
    root = repo_root()
    data_dir = prepare_data_dir(shell_data_dir())
    env = backend_env(os.environ, data_dir)
    backend_cwd = root / "backend"
    ui_env = dict(env)
    ui_env["PORT"] = str(UI_PORT)
    ui_env["BACKEND_URL"] = f"http://127.0.0.1:{BACKEND_PORT}"
    log_dir = Path("/tmp")
    backend = start_process(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agent_window.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ],
        env=env,
        cwd=backend_cwd,
        log_path=log_dir / "loop-shell-backend.log",
    )
    ui = start_process(
        [_find_node(), str(root / "scripts" / "preview-server.mjs")],
        env=ui_env,
        cwd=root,
        log_path=log_dir / "loop-shell-ui.log",
    )
    window: subprocess.Popen[bytes] | None = None
    try:
        if not _wait_http(f"http://127.0.0.1:{BACKEND_PORT}/health", 25):
            raise ShellError("后端没有在用户数据目录里起来。")
        if not _wait_http(f"http://127.0.0.1:{UI_PORT}/", 25):
            raise ShellError("界面没有起来。")
        binary = ensure_window_binary(root)
        window = start_process(
            [str(binary), f"http://127.0.0.1:{UI_PORT}/"],
            env=env,
            cwd=root,
        )
        code = window.wait()
        return int(code or 0)
    finally:
        if window is not None:
            stop_process(window)
        stop_process(ui)
        stop_process(backend)
