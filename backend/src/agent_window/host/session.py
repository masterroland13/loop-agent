"""Process lifecycle for `loop shell`.

The window is the host. It does not import the agent loop. The backend it
starts uses the user data directory and does not receive a copied workspace.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping, Sequence

from agent_window.config import default_user_data_dir

BACKEND_PORT = 8765


class ShellError(Exception):
    pass


def is_checkout_tree(root: Path) -> bool:
    return (root / "backend" / "src" / "agent_window" / "__init__.py").is_file()


def checkout_root(start: Path) -> Path:
    here = start.resolve()
    for parent in (here, *here.parents):
        if is_checkout_tree(parent):
            return parent
    raise ShellError("安装要从仓库运行。当前这份 loop 已经是装好的程序。")


def repo_root() -> Path:
    return checkout_root(Path(__file__))


def shell_data_dir() -> Path:
    override = os.environ.get("LOOP_SHELL_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(default_user_data_dir())


def default_install_dir() -> Path:
    """Program files. Not the user data directory and not the git checkout."""
    return Path.home() / ".local" / "lib" / "loop-agent"


def shell_install_dir() -> Path:
    override = os.environ.get("LOOP_INSTALL_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return default_install_dir()


LAUNCHER_MARK = "# loop-agent launcher"


def default_bin_dir() -> Path:
    """Where the `loop` command lives. Not the install directory."""
    return Path.home() / ".local" / "bin"


def shell_bin_dir() -> Path:
    override = os.environ.get("LOOP_BIN_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return default_bin_dir()


def loop_command_text(python: Path) -> str:
    return (
        "#!/bin/sh\n"
        f"{LAUNCHER_MARK}\n"
        f'exec "{python}" -m agent_window.cli "$@"\n'
    )


def _assert_loop_command_writable(bin_dir: Path) -> None:
    target = bin_dir / "loop"
    if not target.exists():
        return
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ShellError(f"无法写入 loop 命令：{target}") from exc
    if LAUNCHER_MARK not in existing:
        raise ShellError(f"已经有别的 loop 命令：{target}")


def install_loop_command(install_dir: Path, bin_dir: Path) -> Path:
    """Write ~/.local/bin/loop so it uses the installed interpreter."""
    python = shell_python(install_dir)
    _assert_loop_command_writable(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "loop"
    target.write_text(loop_command_text(python), encoding="utf-8")
    os.chmod(target, 0o755)
    return target


DESKTOP_MARK = "# loop-agent desktop"


def default_applications_dir() -> Path:
    return Path.home() / ".local" / "share" / "applications"


def shell_applications_dir() -> Path:
    override = os.environ.get("LOOP_APPLICATIONS_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return default_applications_dir()


def desktop_entry_text(*, command: Path, icon: Path | None) -> str:
    lines = [
        DESKTOP_MARK,
        "[Desktop Entry]",
        "Type=Application",
        "Name=Loop Agent",
        "Comment=Loop Agent",
        f'Exec="{command}" shell',
        "Terminal=false",
        "Categories=Development;",
        "StartupNotify=true",
    ]
    if icon is not None:
        lines.append(f"Icon={icon}")
    return "\n".join(lines) + "\n"


def _desktop_path(applications_dir: Path) -> Path:
    return applications_dir / "loop-agent.desktop"


def _assert_desktop_writable(applications_dir: Path) -> None:
    target = _desktop_path(applications_dir)
    if not target.exists():
        return
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ShellError(f"无法写入桌面启动项：{target}") from exc
    if DESKTOP_MARK not in existing:
        raise ShellError(f"已经有别的桌面启动项：{target}")


def _install_icon(repo: Path, dest: Path) -> Path | None:
    for name in ("ouroboros-logo.png", "ouroboros-logo.svg"):
        source = repo / "public" / name
        if not source.is_file():
            continue
        target = dest / name
        shutil.copy2(source, target)
        return target
    return None


def install_desktop_entry(
    install_dir: Path, bin_dir: Path, applications_dir: Path, icon: Path | None
) -> Path:
    """Write the application menu entry. Exec uses the installed loop command."""
    _assert_desktop_writable(applications_dir)
    applications_dir.mkdir(parents=True, exist_ok=True)
    target = _desktop_path(applications_dir)
    target.write_text(
        desktop_entry_text(command=bin_dir / "loop", icon=icon),
        encoding="utf-8",
    )
    return target


def prepare_data_dir(data_dir: Path) -> Path:
    """Create the data directory. Do not write or copy workspace.json."""
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def backend_env(
    inherited: Mapping[str, str],
    data_dir: Path,
    static_dir: Path | None = None,
) -> dict[str, str]:
    env = {key: value for key, value in inherited.items() if isinstance(value, str)}
    env["APP_DATA_DIR"] = str(data_dir)
    # The shell imports the installed package. A checkout PYTHONPATH would win.
    env.pop("PYTHONPATH", None)
    # Child imports Settings before reading this; skip backend/.env (dev keys).
    env["LOOP_SHELL"] = "1"
    # WSLg WebKit otherwise composites a black window and never paints the UI.
    env["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
    env["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"
    env["WEBKIT_DISABLE_SANDBOX"] = "1"
    env["GDK_BACKEND"] = "x11"
    env["GDK_CORE_DEVICE_EVENTS"] = "1"
    # WSLg sets WAYLAND_DISPLAY; WebKit then uses AcceleratedBackingStoreWayland
    # and the cursor is drawn on a layer the pointer cannot sit on.
    env.pop("WAYLAND_DISPLAY", None)
    if static_dir is not None:
        env["LOOP_STATIC_DIR"] = str(static_dir)
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


def shell_port_is_free(host: str = "127.0.0.1", port: int = BACKEND_PORT) -> bool:
    """True when nothing is accepting connections on the shell backend port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def _wait_http(url: str, timeout: float, *, accept=None, proc=None) -> bool:
    if accept is None:
        accept = lambda status: status == 200
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if accept(response.status):
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    return False


def _stop_shell_on_signal(signum: int, _frame) -> None:
    raise SystemExit(128 + signum)


def _is_linux_executable(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


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


def _materialize_package(source_venv: Path, package_src: Path, dest_venv: Path) -> None:
    """Copy the checkout venv, then put a real package in place of the editable link."""
    if dest_venv.exists():
        shutil.rmtree(dest_venv)
    shutil.copytree(
        source_venv,
        dest_venv,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    sites = list(dest_venv.glob("lib/python*/site-packages"))
    if not sites:
        raise ShellError("虚拟环境里没有 site-packages。")
    site = sites[0]
    for pointer in site.glob("_editable_impl_*.pth"):
        pointer.unlink()
    installed = site / "agent_window"
    if installed.exists() or installed.is_symlink():
        if installed.is_dir() and not installed.is_symlink():
            shutil.rmtree(installed)
        else:
            installed.unlink()
    shutil.copytree(
        package_src,
        installed,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def install_shell_assets(
    repo: Path,
    dest: Path,
    bin_dir: Path | None = None,
    applications_dir: Path | None = None,
) -> Path:
    """Copy the UI, window program, and backend venv; put `loop` on PATH."""
    index = repo / "dist" / "index.html"
    package_src = repo / "backend" / "src" / "agent_window"
    source_venv = repo / "backend" / ".venv"
    if not is_checkout_tree(repo):
        raise ShellError("安装要从仓库运行。当前这份 loop 已经是装好的程序。")
    if not index.is_file():
        raise ShellError("仓库里没有构建好的界面。先在仓库根目录运行 npm run build。")
    if not (package_src / "__init__.py").is_file():
        raise ShellError("仓库里没有后端包。")
    if not (source_venv / "pyvenv.cfg").is_file():
        raise ShellError("仓库里没有后端虚拟环境。")
    command_dir = bin_dir if bin_dir is not None else shell_bin_dir()
    app_dir = (
        applications_dir if applications_dir is not None else shell_applications_dir()
    )
    _assert_loop_command_writable(command_dir)
    _assert_desktop_writable(app_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target_dist = dest / "dist"
    if target_dist.exists():
        shutil.rmtree(target_dist)
    shutil.copytree(repo / "dist", target_dist)
    binary_src = repo / "shell" / "loop-window"
    if not _is_linux_executable(binary_src):
        binary_src = ensure_window_binary(repo)
    shutil.copy2(binary_src, dest / "loop-window")
    os.chmod(dest / "loop-window", 0o755)
    _materialize_package(source_venv, package_src, dest / "venv")
    install_loop_command(dest, command_dir)
    icon = _install_icon(repo, dest)
    install_desktop_entry(dest, command_dir, app_dir, icon)
    return dest


def _looks_like_install(install_dir: Path) -> bool:
    return (
        (install_dir / "dist" / "index.html").is_file()
        or (install_dir / "loop-window").is_file()
        or (install_dir / "venv" / "pyvenv.cfg").is_file()
    )


def _remove_marked_file(path: Path, mark: str) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if mark not in text:
        return False
    path.unlink()
    return True


def uninstall_shell_assets(
    install_dir: Path,
    bin_dir: Path,
    applications_dir: Path,
    data_dir: Path,
) -> list[Path]:
    """Remove program files. Leave the user data directory and workspace."""
    removed: list[Path] = []
    dest = install_dir.resolve()
    data = data_dir.resolve()
    if dest == data:
        raise ShellError("安装目录和用户数据目录相同，没有卸载。")
    if dest == Path.home().resolve() or dest == (Path.home() / ".local").resolve():
        raise ShellError("安装目录不安全，没有卸载。")
    if is_checkout_tree(dest):
        raise ShellError("安装目录看起来是仓库，没有卸载。")
    if dest.exists():
        if not _looks_like_install(dest):
            raise ShellError("安装目录里没有 Loop Agent。")
        shutil.rmtree(dest)
        removed.append(dest)
    if _remove_marked_file(bin_dir / "loop", LAUNCHER_MARK):
        removed.append(bin_dir / "loop")
    if _remove_marked_file(_desktop_path(applications_dir), DESKTOP_MARK):
        removed.append(_desktop_path(applications_dir))
    return removed


def shell_python(install_dir: Path) -> Path:
    for candidate in (
        install_dir / "venv" / "bin" / "python",
        install_dir / "venv" / "Scripts" / "python.exe",
    ):
        if candidate.is_file() or candidate.is_symlink():
            return candidate
    raise ShellError("安装目录里没有 Python。先运行 loop install。")


def shell_commands(install_dir: Path) -> tuple[list[str], list[str]]:
    """Backend argv and window argv. The page is served by the backend."""
    if not (install_dir / "dist" / "index.html").is_file():
        raise ShellError("安装目录里没有界面。先运行 loop install。")
    binary = install_dir / "loop-window"
    if not binary.is_file():
        raise ShellError("安装目录里没有窗口程序。先运行 loop install。")
    python = shell_python(install_dir)
    backend = [
        str(python),
        "-m",
        "uvicorn",
        "agent_window.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(BACKEND_PORT),
    ]
    window = [str(binary), f"http://127.0.0.1:{BACKEND_PORT}/"]
    return backend, window


def launch_plan(
    install_dir: Path, data_dir: Path, inherited: Mapping[str, str]
) -> tuple[list[str], list[str], dict[str, str], Path]:
    """Argv, env, and cwd for the shell backend. cwd is the install directory."""
    backend, window = shell_commands(install_dir)
    env = backend_env(inherited, data_dir, static_dir=install_dir / "dist")
    return backend, window, env, install_dir


def run_shell() -> int:
    install = shell_install_dir()
    data_dir = prepare_data_dir(shell_data_dir())
    backend_argv, window_argv, env, cwd = launch_plan(install, data_dir, os.environ)
    if not shell_port_is_free():
        raise ShellError(f"{BACKEND_PORT} 已经被占用。先关掉另一份 Loop Agent 窗口。")
    previous_term = signal.signal(signal.SIGTERM, _stop_shell_on_signal)
    previous_hup = signal.getsignal(signal.SIGHUP)
    try:
        signal.signal(signal.SIGHUP, _stop_shell_on_signal)
    except (OSError, ValueError):
        previous_hup = None
    log_dir = Path("/tmp")
    backend = start_process(
        backend_argv,
        env=env,
        cwd=cwd,
        log_path=log_dir / "loop-shell-backend.log",
    )
    window: subprocess.Popen[bytes] | None = None
    try:
        if not _wait_http(
            f"http://127.0.0.1:{BACKEND_PORT}/health",
            25,
            proc=backend,
        ):
            raise ShellError("后端没有在用户数据目录里起来。")
        if not _wait_http(
            f"http://127.0.0.1:{BACKEND_PORT}/",
            25,
            accept=lambda status: status == 200,
            proc=backend,
        ):
            raise ShellError("界面没有起来。")
        window = start_process(
            window_argv,
            env=env,
            cwd=install,
            log_path=log_dir / "loop-shell-window.log",
        )
        code = window.wait()
        return int(code or 0)
    finally:
        if window is not None:
            stop_process(window)
        stop_process(backend)
        signal.signal(signal.SIGTERM, previous_term)
        if previous_hup is not None:
            try:
                signal.signal(signal.SIGHUP, previous_hup)
            except (OSError, ValueError):
                pass
