"""USER.md memory store + approval-gated proposals."""

from __future__ import annotations

import asyncio
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
from agent_window.services.workspace import WorkspaceError

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SEC = settings.approval_timeout_sec
MAX_MEMORY_CHARS = 20_000


class MemoryStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    FAILED = "failed"
    CANCELLED = "cancelled"


LISTABLE_MEMORY_STATUSES = {
    MemoryStatus.PENDING,
}


@dataclass
class PendingMemory:
    id: str
    content: str
    mode: str  # replace | append
    preview: str
    status: MemoryStatus = MemoryStatus.PENDING
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None


_memories: Dict[str, PendingMemory] = {}


def _persist_path() -> Path:
    return Path(settings.app_data_dir) / "pending_memories.json"


def _save_memories() -> None:
    """Persist only PENDING memories; decided outcomes live in the message history."""
    items = []
    for m in _memories.values():
        if m.status != MemoryStatus.PENDING:
            continue
        items.append(
            {
                "id": m.id,
                "content": m.content,
                "mode": m.mode,
                "preview": m.preview,
                "status": m.status.value,
                "error": m.error,
                "created_at": m.created_at,
                "decision": m.decision,
            }
        )
    path = _persist_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("failed to persist memories")


def load_persisted_memories() -> int:
    path = _persist_path()
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read persisted memories")
        return 0
    if not isinstance(raw, list):
        return 0
    count = 0
    for item in raw:
        try:
            status = MemoryStatus(item.get("status") or "pending")
        except ValueError:
            continue
        if status != MemoryStatus.PENDING:
            continue
        mid = item.get("id")
        if not mid or mid in _memories:
            continue
        mem = PendingMemory(
            id=mid,
            content=item.get("content") or "",
            mode=item.get("mode") or "replace",
            preview=item.get("preview") or "",
            status=status,
            error=item.get("error"),
            created_at=float(item.get("created_at") or time.time()),
            decision=item.get("decision"),
        )
        _memories[mem.id] = mem
        count += 1
    if count:
        logger.info("restored %s persisted memories", count)
    return count


def user_md_path() -> Path:
    return Path(settings.app_data_dir) / "users" / settings.default_user_id / "USER.md"


def read_user_md() -> str:
    path = user_md_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def write_user_md(content: str) -> None:
    path = user_md_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def memory_status() -> Dict[str, Any]:
    path = user_md_path()
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    return {
        "exists": exists,
        "path": str(path),
        "size": size,
        "preview": (read_user_md()[:400] if exists else ""),
    }


def create_memory_proposal(content: str, mode: str = "replace") -> PendingMemory:
    text = (content or "").strip()
    if not text:
        raise WorkspaceError("memory content is required", "INVALID")
    if len(text) > MAX_MEMORY_CHARS:
        raise WorkspaceError("memory content too large", "TOO_LARGE")
    mode = (mode or "replace").strip().lower()
    if mode not in ("replace", "append"):
        raise WorkspaceError("mode must be replace or append", "INVALID")

    if mode == "append":
        existing = read_user_md().rstrip()
        final = (existing + "\n\n" + text).strip() + "\n" if existing else text.strip() + "\n"
    else:
        final = text.strip() + "\n"

    item = PendingMemory(
        id=str(uuid.uuid4()),
        content=final,
        mode=mode,
        preview=final[:1200],
    )
    _memories[item.id] = item
    _save_memories()
    return item


def get_memory(proposal_id: str) -> Optional[PendingMemory]:
    return _memories.get(proposal_id)


def memory_to_public(item: PendingMemory) -> Dict[str, Any]:
    return {
        "id": item.id,
        "mode": item.mode,
        "preview": item.preview,
        "content": item.content,
        "status": item.status.value,
        "error": item.error,
    }


def list_pending_memories() -> List[Dict[str, Any]]:
    return [
        memory_to_public(m)
        for m in _memories.values()
        if m.status in LISTABLE_MEMORY_STATUSES
    ]


def cancel_pending_memories() -> int:
    n = 0
    for item in _memories.values():
        if item.status != MemoryStatus.PENDING:
            continue
        item.status = MemoryStatus.CANCELLED
        item.decision = "cancelled"
        item.error = "turn cancelled"
        item.event.set()
        n += 1
    if n:
        _save_memories()
    return n


async def decide_memory(proposal_id: str, decision: str) -> PendingMemory:
    item = _memories.get(proposal_id)
    if not item:
        raise WorkspaceError("memory proposal not found", "NOT_FOUND")
    if item.status != MemoryStatus.PENDING:
        raise WorkspaceError(f"memory already {item.status.value}", "ALREADY_DECIDED")

    decision = decision.strip().lower()
    if decision not in ("apply", "reject"):
        raise WorkspaceError("decision must be apply or reject", "INVALID")

    item.decision = decision
    if decision == "reject":
        item.status = MemoryStatus.REJECTED
        item.event.set()
        _save_memories()
        return item

    try:
        write_user_md(item.content)
        item.status = MemoryStatus.APPLIED
    except Exception as e:
        item.status = MemoryStatus.FAILED
        item.error = str(e)
    item.event.set()
    _save_memories()
    return item


async def wait_for_memory_decision(
    proposal_id: str,
    timeout: float = APPROVAL_TIMEOUT_SEC,
    cancel_event: Optional[asyncio.Event] = None,
) -> PendingMemory:
    item = _memories.get(proposal_id)
    if not item:
        raise WorkspaceError("memory proposal not found", "NOT_FOUND")
    outcome = await wait_or_cancel(item.event, cancel_event, timeout)
    if outcome == "timeout":
        if item.status == MemoryStatus.PENDING:
            item.status = MemoryStatus.TIMEOUT
            item.decision = "timeout"
            item.event.set()
            _save_memories()
    elif outcome == "cancelled":
        if item.status == MemoryStatus.PENDING:
            item.status = MemoryStatus.CANCELLED
            item.decision = "cancelled"
            item.error = "turn cancelled"
            item.event.set()
            _save_memories()
    return item
