"""Whitelisted shell commands with approval gate (no exec until apply)."""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings
from agent_window.services.session_turns import wait_or_cancel
from agent_window.services.workspace import WorkspaceError, require_root, resolve_in_workspace

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SEC = 300
CMD_TIMEOUT_SEC = 60
MAX_OUTPUT_BYTES = 32_000

ALLOWED_BINARIES = {
    "python",
    "python3",
    "pytest",
    "npm",
    "npx",
    "node",
    "pnpm",
    "yarn",
    "uv",
    "cargo",
    "go",
    "make",
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "rg",
    "echo",
    "uname",
    "which",
    "git",
    "tsc",
    "oxlint",
}

# git subcommands that are relatively safe (no push/force/clean -fd)
GIT_ALLOWED_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "rev-parse",
    "remote",
    "describe",
    "shortlog",
    "blame",
    "ls-files",
}

BLOCKED_TOKENS = {
    "sudo",
    "su",
    "rm",
    "dd",
    "mkfs",
    "shutdown",
    "reboot",
    "chmod",
    "chown",
    "curl",
    "wget",
    "scp",
    "ssh",
}

# Interpreters that can execute arbitrary code via -c / --eval style flags.
INTERPRETER_BINARIES = {
    "python",
    "python3",
    "node",
    "nodejs",
}

# Exact argv tokens that enable inline code execution.
CODE_EXEC_FLAGS = {
    "-c",
    "--command",
    "-e",
    "--eval",
    "-p",
    "--print",
}


class ShellStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    FAILED = "failed"
    CANCELLED = "cancelled"


LISTABLE_SHELL_STATUSES = {
    ShellStatus.PENDING,
}


@dataclass
class PendingShell:
    id: str
    argv: List[str]
    cwd: str  # relative to workspace, or "."
    cwd_abs: str
    command_display: str
    status: ShellStatus = ShellStatus.PENDING
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None  # apply | reject | timeout | cancelled


_shells: Dict[str, PendingShell] = {}


def _persist_path() -> Path:
    return Path(settings.app_data_dir) / "pending_shells.json"


def _save_shells() -> None:
    """Persist only PENDING shells; decided outcomes live in the message history."""
    items = []
    for s in _shells.values():
        if s.status != ShellStatus.PENDING:
            continue
        items.append(
            {
                "id": s.id,
                "argv": s.argv,
                "cwd": s.cwd,
                "command_display": s.command_display,
                "status": s.status.value,
                "exit_code": s.exit_code,
                "stdout": s.stdout,
                "stderr": s.stderr,
                "truncated": s.truncated,
                "error": s.error,
                "created_at": s.created_at,
                "decision": s.decision,
            }
        )
    path = _persist_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("failed to persist shells")


def load_persisted_shells() -> int:
    path = _persist_path()
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read persisted shells")
        return 0
    if not isinstance(raw, list):
        return 0
    count = 0
    for item in raw:
        try:
            status = ShellStatus(item.get("status") or "pending")
        except ValueError:
            continue
        if status != ShellStatus.PENDING:
            continue
        sid = item.get("id")
        if not sid or sid in _shells:
            continue
        cwd_rel = item.get("cwd") or "."
        try:
            cwd_path = resolve_in_workspace(cwd_rel)
            cwd_abs = str(cwd_path)
        except Exception:
            cwd_abs = cwd_rel
        shell = PendingShell(
            id=sid,
            argv=list(item.get("argv") or []),
            cwd=cwd_rel,
            cwd_abs=cwd_abs,
            command_display=item.get("command_display") or shlex.join(list(item.get("argv") or [])),
            status=status,
            exit_code=item.get("exit_code"),
            stdout=item.get("stdout") or "",
            stderr=item.get("stderr") or "",
            truncated=bool(item.get("truncated")),
            error=item.get("error"),
            created_at=float(item.get("created_at") or time.time()),
            decision=item.get("decision"),
        )
        _shells[shell.id] = shell
        count += 1
    if count:
        logger.info("restored %s persisted shells", count)
    return count


def _binary_name(token: str) -> str:
    return Path(token).name


def validate_argv(argv: List[str]) -> List[str]:
    if not argv or not isinstance(argv, list):
        raise WorkspaceError("argv must be a non-empty list", "INVALID_ARGV")
    cleaned = [str(a) for a in argv if str(a).strip() != ""]
    if not cleaned:
        raise WorkspaceError("argv must be a non-empty list", "INVALID_ARGV")

    for part in cleaned:
        low = part.lower()
        if any(ch in part for ch in (";", "|", "&", "`", "\n", "\r", "$(", "${")):
            raise WorkspaceError("shell metacharacters are not allowed", "BLOCKED")
        if low in BLOCKED_TOKENS:
            raise WorkspaceError(f"blocked token: {part}", "BLOCKED")

    binary = _binary_name(cleaned[0])
    if binary not in ALLOWED_BINARIES:
        raise WorkspaceError(
            f"binary not in whitelist: {binary}. Allowed: {', '.join(sorted(ALLOWED_BINARIES))}",
            "NOT_ALLOWED",
        )

    if binary in INTERPRETER_BINARIES:
        for part in cleaned[1:]:
            low = part.lower()
            flag = low.split("=", 1)[0]
            glued_c = low.startswith("-c") and len(low) > 2 and not low.startswith("--")
            if flag in CODE_EXEC_FLAGS or glued_c:
                raise WorkspaceError(
                    f"inline code execution flag not allowed for {binary}: {part}",
                    "NOT_ALLOWED",
                )

    if binary == "git":
        if len(cleaned) < 2:
            raise WorkspaceError("git requires a subcommand", "NOT_ALLOWED")
        sub = cleaned[1].lstrip("-")
        # allow `git -C`? no — keep simple
        if cleaned[1].startswith("-"):
            raise WorkspaceError("git flags before subcommand are not allowed", "NOT_ALLOWED")
        if cleaned[1] not in GIT_ALLOWED_SUBCOMMANDS:
            raise WorkspaceError(
                f"git subcommand not allowed: {cleaned[1]}. "
                f"Allowed: {', '.join(sorted(GIT_ALLOWED_SUBCOMMANDS))}",
                "NOT_ALLOWED",
            )

    return cleaned


def create_shell_proposal(argv: List[str], cwd: str = ".") -> PendingShell:
    require_root()
    cleaned = validate_argv(argv)
    cwd_rel = (cwd or ".").strip() or "."
    cwd_path = resolve_in_workspace(cwd_rel)
    if not cwd_path.is_dir():
        raise WorkspaceError(f"cwd is not a directory: {cwd_rel}", "NOT_A_DIR")

    root = require_root()
    rel = str(cwd_path.relative_to(root)).replace("\\", "/") if cwd_path != root else "."

    item = PendingShell(
        id=str(uuid.uuid4()),
        argv=cleaned,
        cwd=rel,
        cwd_abs=str(cwd_path),
        command_display=shlex.join(cleaned),
    )
    _shells[item.id] = item
    _save_shells()
    return item


def get_shell(shell_id: str) -> Optional[PendingShell]:
    return _shells.get(shell_id)


def shell_to_public(item: PendingShell) -> Dict[str, Any]:
    return {
        "id": item.id,
        "argv": item.argv,
        "cwd": item.cwd,
        "command": item.command_display,
        "status": item.status.value,
        "exit_code": item.exit_code,
        "stdout": item.stdout,
        "stderr": item.stderr,
        "truncated": item.truncated,
        "error": item.error,
    }


def list_pending_shells() -> List[Dict[str, Any]]:
    return [
        shell_to_public(s)
        for s in _shells.values()
        if s.status in LISTABLE_SHELL_STATUSES
    ]


def cancel_pending_shells() -> int:
    n = 0
    for item in _shells.values():
        if item.status != ShellStatus.PENDING:
            continue
        item.status = ShellStatus.CANCELLED
        item.decision = "cancelled"
        item.error = "turn cancelled"
        item.event.set()
        n += 1
    if n:
        _save_shells()
    return n


def _truncate(text: str) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= MAX_OUTPUT_BYTES:
        return text, False
    return raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n…[truncated]", True


async def run_shell_command(item: PendingShell) -> None:
    item.status = ShellStatus.RUNNING
    try:
        proc = await asyncio.create_subprocess_exec(
            *item.argv,
            cwd=item.cwd_abs,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=None,  # inherit; no secrets injection
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=CMD_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            item.status = ShellStatus.TIMEOUT
            item.error = f"command timed out after {CMD_TIMEOUT_SEC}s"
            item.exit_code = None
            return

        out, t1 = _truncate(out_b.decode("utf-8", errors="replace"))
        err, t2 = _truncate(err_b.decode("utf-8", errors="replace"))
        item.stdout = out
        item.stderr = err
        item.truncated = t1 or t2
        item.exit_code = proc.returncode
        item.status = ShellStatus.DONE
    except FileNotFoundError:
        item.status = ShellStatus.FAILED
        item.error = f"executable not found: {item.argv[0]}"
    except Exception as e:
        logger.exception("shell failed")
        item.status = ShellStatus.FAILED
        item.error = str(e)
    finally:
        _save_shells()


async def decide_shell(shell_id: str, decision: str) -> PendingShell:
    item = _shells.get(shell_id)
    if not item:
        raise WorkspaceError("shell proposal not found", "NOT_FOUND")
    if item.status != ShellStatus.PENDING:
        raise WorkspaceError(f"shell already {item.status.value}", "ALREADY_DECIDED")

    decision = decision.strip().lower()
    if decision not in ("apply", "reject"):
        raise WorkspaceError("decision must be apply or reject", "INVALID")

    item.decision = decision
    if decision == "reject":
        item.status = ShellStatus.REJECTED
        item.error = None
        item.event.set()
        _save_shells()
        return item

    await run_shell_command(item)
    item.event.set()
    return item


async def retry_shell(shell_id: str) -> PendingShell:
    """Retry a shell that previously failed, timed out, or was rejected.

    - REJECTED: reset to PENDING so the user can review and decide again.
    - FAILED / TIMEOUT: run the command immediately.
    """
    item = _shells.get(shell_id)
    if not item:
        raise WorkspaceError("shell proposal not found", "NOT_FOUND")
    if item.status not in (ShellStatus.FAILED, ShellStatus.TIMEOUT, ShellStatus.REJECTED):
        raise WorkspaceError(f"shell status {item.status.value} cannot be retried", "INVALID")

    item.error = None
    item.stdout = ""
    item.stderr = ""
    item.exit_code = None
    item.truncated = False
    item.decision = None
    item.event = asyncio.Event()

    if item.status == ShellStatus.REJECTED:
        item.status = ShellStatus.PENDING
        _save_shells()
        return item

    item.status = ShellStatus.PENDING
    await run_shell_command(item)
    return item


async def wait_for_shell_decision(
    shell_id: str,
    timeout: float = APPROVAL_TIMEOUT_SEC,
    cancel_event: Optional[asyncio.Event] = None,
) -> PendingShell:
    item = _shells.get(shell_id)
    if not item:
        raise WorkspaceError("shell proposal not found", "NOT_FOUND")
    outcome = await wait_or_cancel(item.event, cancel_event, timeout)
    if outcome == "timeout":
        if item.status == ShellStatus.PENDING:
            item.status = ShellStatus.TIMEOUT
            item.decision = "timeout"
            item.event.set()
            _save_shells()
    elif outcome == "cancelled":
        if item.status == ShellStatus.PENDING:
            item.status = ShellStatus.CANCELLED
            item.decision = "cancelled"
            item.error = "turn cancelled"
            item.event.set()
            _save_shells()
    return item
