"""Persisted workspace root + path sandbox for local tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings

logger = logging.getLogger(__name__)

_CONFIG_NAME = "workspace.json"
MAX_READ_BYTES = 100_000
MAX_LIST_ENTRIES = 200
MAX_GREP_MATCHES = 40
MAX_GREP_FILE_BYTES = 1_000_000

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
