"""Pending file patches with approval gate (no disk write until apply)."""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
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

MAX_EDIT_BYTES = 200_000
APPROVAL_TIMEOUT_SEC = 300


class PatchStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIONABLE_STATUSES = {
    PatchStatus.PENDING,
    PatchStatus.FAILED,
    PatchStatus.REJECTED,
    PatchStatus.TIMEOUT,
}


@dataclass
class PendingPatch:
    id: str
    path: str  # relative to workspace
    old_content: str
    new_content: str
    unified_diff: str
    is_new_file: bool
    status: PatchStatus = PatchStatus.PENDING
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None  # apply | reject | timeout | cancelled


_patches: Dict[str, PendingPatch] = {}


def _persist_path() -> Path:
    return Path(settings.app_data_dir) / "pending_patches.json"


def _save_patches() -> None:
    """Persist only PENDING patches; decided outcomes live in the message history."""
    items = []
    for p in _patches.values():
        if p.status != PatchStatus.PENDING:
            continue
        items.append(
            {
                "id": p.id,
                "path": p.path,
                "old_content": p.old_content,
                "new_content": p.new_content,
                "unified_diff": p.unified_diff,
                "is_new_file": p.is_new_file,
                "status": p.status.value,
                "error": p.error,
                "created_at": p.created_at,
                "decision": p.decision,
            }
        )
    path = _persist_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("failed to persist patches")


def load_persisted_patches() -> int:
    """Restore actionable patches after process restart. Returns count loaded."""
    path = _persist_path()
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read persisted patches")
        return 0
    if not isinstance(raw, list):
        return 0
    count = 0
    for item in raw:
        try:
            status = PatchStatus(item.get("status") or "pending")
        except ValueError:
            continue
        if status != PatchStatus.PENDING:
            continue
        pid = item.get("id")
        if not pid or pid in _patches:
            continue
        patch = PendingPatch(
            id=pid,
            path=item.get("path") or "",
            old_content=item.get("old_content") or "",
            new_content=item.get("new_content") or "",
            unified_diff=item.get("unified_diff") or "",
            is_new_file=bool(item.get("is_new_file")),
            status=status,
            error=item.get("error"),
            created_at=float(item.get("created_at") or time.time()),
            decision=item.get("decision"),
        )
        _patches[patch.id] = patch
        count += 1
    if count:
        logger.info("restored %s persisted patches", count)
    return count


def build_unified_diff(path: str, old: str, new: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    if old and not old.endswith("\n"):
        # difflib nicety
        pass
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="\n",
    )
    text = "".join(diff)
    return text or f"--- a/{path}\n+++ b/{path}\n@@ (no textual diff) @@\n"


def create_patch_from_replace(
    path: str,
    old_string: str,
    new_string: str,
) -> PendingPatch:
    """Search-replace style edit (or create if file missing and old_string empty)."""
    require_root()
    rel = path.strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        # still allow resolve_in_workspace to validate; just normalize
        pass

    target = resolve_in_workspace(rel)
    root = require_root()
    rel_path = str(target.relative_to(root)).replace("\\", "/")

    is_new = not target.exists()
    if is_new:
        if old_string:
            raise WorkspaceError("file does not exist; old_string must be empty for create", "NOT_FOUND")
        old_content = ""
        new_content = new_string
    else:
        if not target.is_file():
            raise WorkspaceError(f"not a file: {rel_path}", "NOT_A_FILE")
        raw = target.read_bytes()
        if len(raw) > MAX_EDIT_BYTES:
            raise WorkspaceError("file too large to edit", "TOO_LARGE")
        if b"\x00" in raw[:4096]:
            raise WorkspaceError("binary file; refuse to edit", "BINARY")
        old_content = raw.decode("utf-8", errors="replace")
        if old_string not in old_content:
            raise WorkspaceError("old_string not found in file", "NO_MATCH")
        count = old_content.count(old_string)
        if count > 1:
            raise WorkspaceError(
                f"old_string matched {count} times; make it unique",
                "AMBIGUOUS",
            )
        new_content = old_content.replace(old_string, new_string, 1)

    if len(new_content.encode("utf-8")) > MAX_EDIT_BYTES:
        raise WorkspaceError("new content too large", "TOO_LARGE")

    if old_content == new_content:
        raise WorkspaceError("no changes", "NO_CHANGE")

    patch = PendingPatch(
        id=str(uuid.uuid4()),
        path=rel_path,
        old_content=old_content,
        new_content=new_content,
        unified_diff=build_unified_diff(rel_path, old_content, new_content),
        is_new_file=is_new,
    )
    _patches[patch.id] = patch
    _save_patches()
    return patch


def create_patch_from_content(path: str, content: str) -> PendingPatch:
    """Full-file write / create."""
    require_root()
    target = resolve_in_workspace(path)
    root = require_root()
    rel_path = str(target.relative_to(root)).replace("\\", "/")

    is_new = not target.exists()
    if is_new:
        old_content = ""
    else:
        if not target.is_file():
            raise WorkspaceError(f"not a file: {rel_path}", "NOT_A_FILE")
        raw = target.read_bytes()
        if len(raw) > MAX_EDIT_BYTES:
            raise WorkspaceError("file too large to edit", "TOO_LARGE")
        if b"\x00" in raw[:4096]:
            raise WorkspaceError("binary file; refuse to edit", "BINARY")
        old_content = raw.decode("utf-8", errors="replace")

    new_content = content if content is not None else ""
    if len(new_content.encode("utf-8")) > MAX_EDIT_BYTES:
        raise WorkspaceError("new content too large", "TOO_LARGE")
    if old_content == new_content:
        raise WorkspaceError("no changes", "NO_CHANGE")

    patch = PendingPatch(
        id=str(uuid.uuid4()),
        path=rel_path,
        old_content=old_content,
        new_content=new_content,
        unified_diff=build_unified_diff(rel_path, old_content, new_content),
        is_new_file=is_new,
    )
    _patches[patch.id] = patch
    _save_patches()
    return patch


def get_patch(patch_id: str) -> Optional[PendingPatch]:
    return _patches.get(patch_id)


def patch_to_public(patch: PendingPatch) -> Dict[str, Any]:
    return {
        "id": patch.id,
        "path": patch.path,
        "unified_diff": patch.unified_diff,
        "is_new_file": patch.is_new_file,
        "status": patch.status.value,
        "error": patch.error,
    }


def list_pending() -> List[Dict[str, Any]]:
    """Pending + retryable patches for UI restore after refresh/restart."""
    return [
        patch_to_public(p)
        for p in _patches.values()
        if p.status in ACTIONABLE_STATUSES
    ]


def cancel_pending_patches() -> int:
    """Mark all pending patches cancelled and wake waiters. Returns count."""
    n = 0
    for patch in _patches.values():
        if patch.status != PatchStatus.PENDING:
            continue
        patch.status = PatchStatus.CANCELLED
        patch.decision = "cancelled"
        patch.error = "turn cancelled"
        patch.event.set()
        n += 1
    if n:
        _save_patches()
    return n


def apply_patch_to_disk(patch: PendingPatch) -> None:
    target = resolve_in_workspace(patch.path)
    # Re-check old content for non-new files (prevent clobber if changed underfoot)
    if patch.is_new_file:
        if target.exists():
            raise WorkspaceError("file was created meanwhile; abort", "CONFLICT")
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        if not target.exists():
            raise WorkspaceError("file disappeared; abort", "CONFLICT")
        current = target.read_text(encoding="utf-8", errors="replace")
        if current != patch.old_content:
            raise WorkspaceError("file changed on disk since proposal; abort", "CONFLICT")

    target.write_text(patch.new_content, encoding="utf-8")


async def decide_patch(patch_id: str, decision: str) -> PendingPatch:
    """User decision: apply | reject. Wakes waiter."""
    patch = _patches.get(patch_id)
    if not patch:
        raise WorkspaceError("patch not found", "NOT_FOUND")
    if patch.status != PatchStatus.PENDING:
        raise WorkspaceError(f"patch already {patch.status.value}", "ALREADY_DECIDED")

    decision = decision.strip().lower()
    if decision not in ("apply", "reject"):
        raise WorkspaceError("decision must be apply or reject", "INVALID")

    if decision == "apply":
        try:
            apply_patch_to_disk(patch)
            patch.status = PatchStatus.APPLIED
            patch.error = None
        except Exception as e:
            # Keep FAILED as a normal outcome so HTTP/SSE stay in sync with patch status.
            patch.status = PatchStatus.FAILED
            patch.error = str(e)
        patch.decision = "apply"
    else:
        patch.status = PatchStatus.REJECTED
        patch.error = None
        patch.decision = "reject"

    patch.event.set()
    _save_patches()
    return patch


async def retry_patch(patch_id: str) -> PendingPatch:
    """Retry a patch that previously failed or was rejected.

    - REJECTED: reset to PENDING so the user can review and decide again.
    - FAILED / TIMEOUT: attempt to apply immediately.
    """
    patch = _patches.get(patch_id)
    if not patch:
        raise WorkspaceError("patch not found", "NOT_FOUND")
    if patch.status not in (PatchStatus.FAILED, PatchStatus.REJECTED, PatchStatus.TIMEOUT):
        raise WorkspaceError(f"patch status {patch.status.value} cannot be retried", "INVALID")

    if patch.status == PatchStatus.REJECTED:
        patch.status = PatchStatus.PENDING
        patch.error = None
        patch.decision = None
        patch.event = asyncio.Event()
        _save_patches()
        return patch

    # FAILED / TIMEOUT: try applying again right away.
    patch.status = PatchStatus.PENDING
    patch.error = None
    patch.decision = None
    patch.event = asyncio.Event()
    try:
        apply_patch_to_disk(patch)
        patch.status = PatchStatus.APPLIED
        patch.decision = "apply"
    except Exception as e:
        patch.status = PatchStatus.FAILED
        patch.error = str(e)
        patch.decision = "apply"
    _save_patches()
    return patch


async def wait_for_decision(
    patch_id: str,
    timeout: float = APPROVAL_TIMEOUT_SEC,
    cancel_event: Optional[asyncio.Event] = None,
) -> PendingPatch:
    patch = _patches.get(patch_id)
    if not patch:
        raise WorkspaceError("patch not found", "NOT_FOUND")
    outcome = await wait_or_cancel(patch.event, cancel_event, timeout)
    if outcome == "timeout":
        if patch.status == PatchStatus.PENDING:
            patch.status = PatchStatus.TIMEOUT
            patch.decision = "timeout"
            patch.event.set()
            _save_patches()
    elif outcome == "cancelled":
        if patch.status == PatchStatus.PENDING:
            patch.status = PatchStatus.CANCELLED
            patch.decision = "cancelled"
            patch.error = "turn cancelled"
            patch.event.set()
            _save_patches()
    return patch
