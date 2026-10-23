"""Persisted workspace root + path sandbox for local tools."""

from __future__ import annotations

import io
import json
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings

logger = logging.getLogger(__name__)

_CONFIG_NAME = "workspace.json"
MAX_READ_BYTES = 100_000
MAX_LIST_ENTRIES = 200
MAX_GREP_MATCHES = 40
MAX_GREP_FILE_BYTES = 1_000_000
# Human Files editor — larger than agent read_file window; still bounded.
MAX_EDITOR_BYTES = 2_000_000

_SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}


class WorkspaceError(Exception):
    def __init__(self, message: str, code: str = "WORKSPACE_ERROR"):
        super().__init__(message)
        self.code = code


def _config_path() -> Path:
    return Path(settings.app_data_dir) / _CONFIG_NAME


def get_workspace_root() -> Optional[Path]:
    path = _config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        root = (data.get("root") or "").strip()
        if not root:
            return None
        p = Path(root).expanduser().resolve()
        if not p.is_dir():
            return None
        return p
    except Exception:
        logger.exception("failed to load workspace config")
        return None


def set_workspace_root(root: str) -> Path:
    raw = (root or "").strip()
    if not raw:
        raise WorkspaceError("workspace root is required", "INVALID_ROOT")
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        raise WorkspaceError(f"path does not exist: {p}", "NOT_FOUND")
    if not p.is_dir():
        raise WorkspaceError(f"not a directory: {p}", "NOT_A_DIR")

    cfg = _config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"root": str(p)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def clear_workspace_root() -> None:
    cfg = _config_path()
    if cfg.exists():
        cfg.unlink()


def require_root() -> Path:
    root = get_workspace_root()
    if not root:
        raise WorkspaceError(
            "未配置工作区。请先在 This PC 中设置本地目录。",
            "NO_WORKSPACE",
        )
    return root


def resolve_in_workspace(user_path: str | None) -> Path:
    root = require_root()
    rel = (user_path or ".").strip() or "."
    candidate = Path(rel).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except Exception as e:
        raise WorkspaceError(f"invalid path: {e}", "INVALID_PATH") from e

    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise WorkspaceError("path escapes workspace root", "PATH_ESCAPE") from e
    return resolved


def workspace_status() -> Dict[str, Any]:
    root = get_workspace_root()
    return {
        "configured": root is not None,
        "root": str(root) if root else None,
        "name": root.name if root else None,
    }


def list_directory(path: str = ".", max_entries: int = MAX_LIST_ENTRIES) -> Dict[str, Any]:
    target = resolve_in_workspace(path)
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    if not target.is_dir():
        raise WorkspaceError(f"not a directory: {path}", "NOT_A_DIR")

    root = require_root()
    entries: List[Dict[str, Any]] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as e:
        raise WorkspaceError(str(e), "PERMISSION") from e

    for child in children:
        if len(entries) >= max_entries:
            break
        if child.name in _SKIP_DIR_NAMES:
            continue
        try:
            rel = str(child.relative_to(root)).replace("\\", "/")
            item: Dict[str, Any] = {
                "name": child.name,
                "path": rel,
                "type": "dir" if child.is_dir() else "file",
            }
            if child.is_file():
                item["size"] = child.stat().st_size
            entries.append(item)
        except OSError:
            continue

    return {
        "path": str(target.relative_to(root)).replace("\\", "/") if target != root else ".",
        "entries": entries,
        "truncated": len(entries) >= max_entries,
    }


def read_file(
    path: str,
    offset: int = 1,
    limit: int = 200,
) -> Dict[str, Any]:
    target = resolve_in_workspace(path)
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    if not target.is_file():
        raise WorkspaceError(f"not a file: {path}", "NOT_A_FILE")

    size = target.stat().st_size
    if size > MAX_READ_BYTES * 4:
        # Still allow reading a window, but warn
        pass

    try:
        raw = target.read_bytes()
    except OSError as e:
        raise WorkspaceError(str(e), "READ_ERROR") from e

    if b"\x00" in raw[:4096]:
        raise WorkspaceError("binary file; refuse to read", "BINARY")

    text = raw[:MAX_READ_BYTES].decode("utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    start = max(1, int(offset or 1))
    lim = max(1, min(int(limit or 200), 500))
    end = min(total, start + lim - 1)
    window = lines[start - 1 : end]
    numbered = "\n".join(f"{i}|{line}" for i, line in enumerate(window, start=start))

    root = require_root()
    return {
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "offset": start,
        "limit": lim,
        "total_lines": total,
        "bytes_read": min(len(raw), MAX_READ_BYTES),
        "truncated": len(raw) > MAX_READ_BYTES or end < total,
        "content": numbered,
    }


def read_text_file(path: str) -> Dict[str, Any]:
    """Full-file UTF-8 read for the human Files panel (no line-number prefixes).

    Does not replace agent ``read_file``, which returns numbered windows.
    """
    target = resolve_in_workspace(path)
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    if not target.is_file():
        raise WorkspaceError(f"not a file: {path}", "NOT_A_FILE")

    try:
        st = target.stat()
        raw = target.read_bytes()
    except OSError as e:
        raise WorkspaceError(str(e), "READ_ERROR") from e

    if b"\x00" in raw[:4096]:
        raise WorkspaceError("binary file; refuse to read", "BINARY")

    if len(raw) > MAX_EDITOR_BYTES:
        raise WorkspaceError(
            f"file too large for editor (>{MAX_EDITOR_BYTES} bytes)",
            "TOO_LARGE",
        )

    text = raw.decode("utf-8", errors="replace")
    root = require_root()
    return {
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "content": text,
        "mtime_ns": int(st.st_mtime_ns),
        "size": int(st.st_size),
        "encoding": "utf-8",
    }


def is_docx_editor_path(path: str) -> bool:
    return path.lower().endswith(".docx")


def _docx_bytes_to_html(raw: bytes) -> str:
    import mammoth

    result = mammoth.convert_to_html(io.BytesIO(raw))
    return result.value


def read_docx_file(path: str) -> Dict[str, Any]:
    """Convert .docx to HTML for the Files panel (human editor, not agent tools)."""
    target = resolve_in_workspace(path)
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    if not target.is_file():
        raise WorkspaceError(f"not a file: {path}", "NOT_A_FILE")

    try:
        st = target.stat()
        raw = target.read_bytes()
    except OSError as e:
        raise WorkspaceError(str(e), "READ_ERROR") from e

    if len(raw) > MAX_EDITOR_BYTES:
        raise WorkspaceError(
            f"file too large for editor (>{MAX_EDITOR_BYTES} bytes)",
            "TOO_LARGE",
        )

    try:
        html = _docx_bytes_to_html(raw)
    except Exception as e:
        raise WorkspaceError(f"docx read failed: {e}", "READ_ERROR") from e

    root = require_root()
    return {
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "content": html,
        "mtime_ns": int(st.st_mtime_ns),
        "size": int(st.st_size),
        "encoding": "docx-html",
    }


def read_editor_file(path: str) -> Dict[str, Any]:
    if is_docx_editor_path(path):
        return read_docx_file(path)
    return read_text_file(path)


def write_text_file(
    path: str,
    content: str,
    if_match_mtime_ns: int | None = None,
    if_match_base_content: str | None = None,
) -> Dict[str, Any]:
    """Direct UTF-8 write for the human Files panel (scheme A — not propose_edit)."""
    if content is None:
        raise WorkspaceError("content is required", "INVALID")
    if not isinstance(content, str):
        raise WorkspaceError("content must be a string", "INVALID")

    target = resolve_in_workspace(path)
    root = require_root()

    if target.exists() and target.is_dir():
        raise WorkspaceError(f"not a file: {path}", "NOT_A_FILE")

    if if_match_mtime_ns is not None:
        if not target.exists():
            raise WorkspaceError("file disappeared; abort", "CONFLICT")
        try:
            current = int(target.stat().st_mtime_ns)
        except OSError as e:
            raise WorkspaceError(str(e), "READ_ERROR") from e
        if current != int(if_match_mtime_ns):
            if if_match_base_content is None:
                raise WorkspaceError(
                    "file changed on disk since last read; abort",
                    "CONFLICT",
                )
            try:
                disk_text = target.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                raise WorkspaceError(str(e), "READ_ERROR") from e
            if disk_text != if_match_base_content:
                raise WorkspaceError(
                    "file changed on disk since last read; abort",
                    "CONFLICT",
                )

    data = content.encode("utf-8")
    if len(data) > MAX_EDITOR_BYTES:
        raise WorkspaceError(
            f"content too large for editor (>{MAX_EDITOR_BYTES} bytes)",
            "TOO_LARGE",
        )

    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise WorkspaceError(f"parent directory not found: {path}", "NOT_FOUND")

    try:
        target.write_bytes(data)
        st = target.stat()
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e

    return {
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "mtime_ns": int(st.st_mtime_ns),
        "size": int(st.st_size),
    }


def write_docx_file(
    path: str,
    html_content: str,
    if_match_mtime_ns: int | None = None,
    if_match_base_content: str | None = None,
) -> Dict[str, Any]:
    """Write HTML body back to .docx (simple documents; layout may shift)."""
    if html_content is None:
        raise WorkspaceError("content is required", "INVALID")
    if not isinstance(html_content, str):
        raise WorkspaceError("content must be a string", "INVALID")

    target = resolve_in_workspace(path)
    root = require_root()

    if target.exists() and target.is_dir():
        raise WorkspaceError(f"not a file: {path}", "NOT_A_FILE")

    if if_match_mtime_ns is not None:
        if not target.exists():
            raise WorkspaceError("file disappeared; abort", "CONFLICT")
        try:
            current = int(target.stat().st_mtime_ns)
        except OSError as e:
            raise WorkspaceError(str(e), "READ_ERROR") from e
        if current != int(if_match_mtime_ns):
            if if_match_base_content is None:
                raise WorkspaceError(
                    "file changed on disk since last read; abort",
                    "CONFLICT",
                )
            try:
                disk_html = _docx_bytes_to_html(target.read_bytes())
            except OSError as e:
                raise WorkspaceError(str(e), "READ_ERROR") from e
            if disk_html != if_match_base_content:
                raise WorkspaceError(
                    "file changed on disk since last read; abort",
                    "CONFLICT",
                )

    from docx import Document
    from htmldocx import HtmlToDocx

    document = Document()
    HtmlToDocx().add_html_to_document(html_content, document)

    buf = io.BytesIO()
    try:
        document.save(buf)
        data = buf.getvalue()
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e

    if len(data) > MAX_EDITOR_BYTES:
        raise WorkspaceError(
            f"content too large for editor (>{MAX_EDITOR_BYTES} bytes)",
            "TOO_LARGE",
        )

    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise WorkspaceError(f"parent directory not found: {path}", "NOT_FOUND")

    try:
        target.write_bytes(data)
        st = target.stat()
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e

    return {
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "mtime_ns": int(st.st_mtime_ns),
        "size": int(st.st_size),
    }


def write_editor_file(
    path: str,
    content: str,
    if_match_mtime_ns: int | None = None,
    if_match_base_content: str | None = None,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    enc = (encoding or "utf-8").strip().lower()
    if enc == "docx-html" or is_docx_editor_path(path):
        return write_docx_file(
            path,
            content,
            if_match_mtime_ns=if_match_mtime_ns,
            if_match_base_content=if_match_base_content,
        )
    return write_text_file(
        path,
        content,
        if_match_mtime_ns=if_match_mtime_ns,
        if_match_base_content=if_match_base_content,
    )


def mkdir_directory(path: str) -> Dict[str, Any]:
    """Create a single directory under the workspace (parent must exist)."""
    target = resolve_in_workspace(path)
    root = require_root()
    if target.exists():
        raise WorkspaceError(f"already exists: {path}", "EXISTS")
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise WorkspaceError(f"parent directory not found: {path}", "NOT_FOUND")
    try:
        target.mkdir(parents=False)
    except FileExistsError:
        raise WorkspaceError(f"already exists: {path}", "EXISTS") from None
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e
    rel = str(target.relative_to(root)).replace("\\", "/")
    return {"path": rel}


def rename_entry(from_path: str, to_path: str) -> Dict[str, Any]:
    """Rename a file or directory within the workspace."""
    src_rel = (from_path or "").strip()
    dst_rel = (to_path or "").strip()
    if not src_rel or not dst_rel:
        raise WorkspaceError("from and to paths are required", "INVALID")
    if src_rel == dst_rel:
        resolved = resolve_in_workspace(src_rel)
        root = require_root()
        if not resolved.exists():
            raise WorkspaceError(f"not found: {src_rel}", "NOT_FOUND")
        rel = str(resolved.relative_to(root)).replace("\\", "/")
        return {"from": src_rel, "path": rel}

    src = resolve_in_workspace(src_rel)
    dst = resolve_in_workspace(dst_rel)
    root = require_root()
    if not src.exists():
        raise WorkspaceError(f"not found: {src_rel}", "NOT_FOUND")
    if dst.exists():
        raise WorkspaceError(f"already exists: {dst_rel}", "EXISTS")
    _assert_destination_parent(dst)
    _assert_not_descendant_move(src, dst)
    try:
        src.rename(dst)
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e
    rel = str(dst.relative_to(root)).replace("\\", "/")
    return {"from": src_rel, "path": rel}


def _rel_to_root(target: Path, root: Path) -> str:
    return str(target.relative_to(root)).replace("\\", "/")


def _assert_destination_parent(dst: Path) -> None:
    parent = dst.parent
    if not parent.exists() or not parent.is_dir():
        raise WorkspaceError(f"parent directory not found: {dst}", "NOT_FOUND")


def _assert_not_descendant_move(src: Path, dst: Path) -> None:
    if src == dst:
        raise WorkspaceError("source and destination are the same", "INVALID")
    if not src.is_dir():
        return
    try:
        dst.relative_to(src)
    except ValueError:
        return
    raise WorkspaceError(
        "cannot move or copy a directory into itself or its descendant",
        "INVALID",
    )


def tree_stats(path: str) -> Dict[str, Any]:
    """Count files and subdirectories under a workspace directory."""
    target = resolve_in_workspace(path)
    root = require_root()
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    if not target.is_dir():
        raise WorkspaceError(f"not a directory: {path}", "NOT_A_DIR")

    file_count = 0
    dir_count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(target):
            dir_count += len(dirnames)
            file_count += len(filenames)
    except OSError as e:
        raise WorkspaceError(str(e), "READ_ERROR") from e

    return {
        "path": _rel_to_root(target, root),
        "file_count": file_count,
        "dir_count": dir_count,
    }


def copy_entry(from_path: str, to_path: str) -> Dict[str, Any]:
    """Copy a file or directory tree within the workspace."""
    src_rel = (from_path or "").strip()
    dst_rel = (to_path or "").strip()
    if not src_rel or not dst_rel:
        raise WorkspaceError("from and to paths are required", "INVALID")

    src = resolve_in_workspace(src_rel)
    dst = resolve_in_workspace(dst_rel)
    root = require_root()
    if not src.exists():
        raise WorkspaceError(f"not found: {src_rel}", "NOT_FOUND")
    if dst.exists():
        raise WorkspaceError(f"already exists: {dst_rel}", "EXISTS")
    _assert_destination_parent(dst)
    _assert_not_descendant_move(src, dst)

    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    except OSError as e:
        raise WorkspaceError(str(e), "WRITE_ERROR") from e

    return {"from": src_rel, "path": _rel_to_root(dst, root)}


def delete_entry(path: str, recursive: bool = False) -> Dict[str, Any]:
    """Delete a file or directory within the workspace."""
    target = resolve_in_workspace(path)
    root = require_root()
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")
    rel = _rel_to_root(target, root)
    if target.is_dir():
        try:
            children = list(target.iterdir())
        except OSError as e:
            raise WorkspaceError(str(e), "READ_ERROR") from e
        if children and not recursive:
            raise WorkspaceError(f"directory not empty: {path}", "NOT_EMPTY")
        try:
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        except OSError as e:
            raise WorkspaceError(str(e), "WRITE_ERROR") from e
    else:
        try:
            target.unlink()
        except OSError as e:
            raise WorkspaceError(str(e), "WRITE_ERROR") from e
    return {"path": rel, "recursive": bool(recursive)}


def _in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _to_windows_path(linux_path: str) -> str | None:
    wslpath = shutil.which("wslpath")
    if not wslpath:
        return None
    try:
        proc = subprocess.run(
            [wslpath, "-w", linux_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def _explorer_exe() -> str | None:
    found = shutil.which("explorer.exe")
    if found:
        return found
    win_explorer = Path("/mnt/c/Windows/explorer.exe")
    if win_explorer.is_file():
        return str(win_explorer)
    return None


def _reveal_argv(target: Path) -> list[str]:
    """Build argv for opening the host file manager."""
    abs_path = str(target.resolve())
    is_file = target.is_file()
    system = platform.system()

    if system == "Windows":
        if is_file:
            return ["explorer", "/select,", abs_path]
        return ["explorer", abs_path]

    if system == "Darwin":
        return ["open", "-R", abs_path]

    # Linux — WSL should open Windows Explorer, not xdg-open (often missing).
    if _in_wsl():
        win_path = _to_windows_path(abs_path)
        explorer = _explorer_exe()
        if win_path and explorer:
            if is_file:
                return [explorer, "/select,", win_path]
            return [explorer, win_path]

    reveal = str(target.parent.resolve() if is_file else target.resolve())
    xdg = shutil.which("xdg-open")
    if xdg:
        return [xdg, reveal]
    gio = shutil.which("gio")
    if gio:
        return [gio, "open", reveal]

    raise WorkspaceError(
        "无法在资源管理器中打开：未找到 explorer.exe / xdg-open / gio",
        "REVEAL_FAILED",
    )


def reveal_in_explorer(path: str) -> Dict[str, Any]:
    """Open the OS file manager and highlight the workspace path."""
    target = resolve_in_workspace(path)
    root = require_root()
    if not target.exists():
        raise WorkspaceError(f"not found: {path}", "NOT_FOUND")

    argv = _reveal_argv(target)
    try:
        subprocess.Popen(argv, close_fds=True)  # noqa: S603
    except OSError as e:
        raise WorkspaceError(str(e), "REVEAL_FAILED") from e

    abs_path = str(target.resolve())
    return {"path": _rel_to_root(target, root), "revealed": abs_path}


def grep_search(
    pattern: str,
    path: str = ".",
    glob: str = "*",
    case_insensitive: bool = False,
) -> Dict[str, Any]:
    import fnmatch
    import os
    import re

    if not (pattern or "").strip():
        raise WorkspaceError("pattern is required", "INVALID_PATTERN")

    target = resolve_in_workspace(path)
    root = require_root()
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise WorkspaceError(f"invalid regex: {e}", "INVALID_PATTERN") from e

    matches: List[Dict[str, Any]] = []
    files_scanned = 0

    def collect_files() -> List[Path]:
        if target.is_file():
            return [target]
        out: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
            for name in filenames:
                out.append(Path(dirpath) / name)
        return out

    for fp in collect_files():
        if len(matches) >= MAX_GREP_MATCHES:
            break
        if glob and glob != "*" and not fnmatch.fnmatch(fp.name, glob):
            continue
        try:
            if fp.stat().st_size > MAX_GREP_FILE_BYTES:
                continue
            raw = fp.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        files_scanned += 1
        text = raw.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                try:
                    rel = str(fp.relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel = str(fp)
                matches.append({"path": rel, "line": i, "text": line[:300]})
                if len(matches) >= MAX_GREP_MATCHES:
                    break

    return {
        "pattern": pattern,
        "path": path or ".",
        "glob": glob,
        "files_scanned": files_scanned,
        "match_count": len(matches),
        "truncated": len(matches) >= MAX_GREP_MATCHES,
        "matches": matches,
    }


def create_browse_directory(parent: str, name: str) -> Path:
    """Create a folder under a This PC path. Does not bind it as the workspace."""
    raw_name = (name or "").strip()
    if (
        not raw_name
        or raw_name in {".", ".."}
        or "/" in raw_name
        or "\\" in raw_name
    ):
        raise WorkspaceError("invalid folder name", "INVALID_NAME")
    parent_path = Path(parent).expanduser().resolve()
    if not parent_path.is_dir():
        raise WorkspaceError(f"not a directory: {parent_path}", "NOT_A_DIR")
    dest = (parent_path / raw_name).resolve()
    if dest.parent != parent_path:
        raise WorkspaceError("invalid folder name", "INVALID_NAME")
    if dest.exists() and not dest.is_dir():
        raise WorkspaceError(f"not a directory: {dest}", "NOT_A_DIR")
    dest.mkdir(parents=False, exist_ok=True)
    return dest


def browse_directory(path: str | None = None) -> Dict[str, Any]:
    """List directories for the This PC picker (dirs only, absolute)."""
    if path:
        target = Path(path).expanduser().resolve()
    else:
        root = get_workspace_root()
        target = root if root else Path.home().resolve()

    if not target.exists() or not target.is_dir():
        raise WorkspaceError(f"not a directory: {target}", "NOT_A_DIR")

    dirs: List[Dict[str, str]] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and not child.name.startswith("."):
                dirs.append({"name": child.name, "path": str(child.resolve())})
    except PermissionError as e:
        raise WorkspaceError(str(e), "PERMISSION") from e

    parent = str(target.parent.resolve()) if target.parent != target else None
    return {
        "path": str(target),
        "parent": parent,
        "directories": dirs[:300],
    }
