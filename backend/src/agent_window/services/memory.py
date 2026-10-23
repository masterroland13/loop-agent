"""USER.md + MEMORY.md stores, approval-gated proposals, session freeze snapshots.

Hermes-scale curated memory (charter §3.5):
  USER.md    — preferences / profile (default ≤1375)
  MEMORY.md  — environment / project / lessons (default ≤2200)

M0: whole-file replace/append + dual freeze.
M1: entry ops add/replace/remove (+ batch operations) with ``\\n§\\n`` separators.

Dual-state: freeze at session start for system inject; mid-session writes update
disk + live immediately but do not refresh this session's system snapshot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

from agent_window.config import settings
from agent_window.services.attachment_context import get_turn_session_id
from agent_window.services.session_turns import wait_or_cancel
from agent_window.services.workspace import WorkspaceError

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SEC = settings.approval_timeout_sec
# Hermes-scale hard caps (no silent truncate).
USER_MD_CHAR_LIMIT = 1375
MEMORY_MD_CHAR_LIMIT = 2200
# Back-compat alias — USER proposal final body must be ≤ USER_MD_CHAR_LIMIT.
MAX_MEMORY_CHARS = USER_MD_CHAR_LIMIT

# Hermes-style entry delimiter (entries may be multi-line).
ENTRY_SEP = "\n§\n"

MemoryTarget = Literal["user", "memory"]
EntryAction = Literal["add", "replace", "remove"]
FileMode = Literal["replace", "append"]


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
    mode: str  # replace|append|add|remove|operations|…
    preview: str
    target: MemoryTarget = "user"
    status: MemoryStatus = MemoryStatus.PENDING
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None
    op_summary: str = ""
    session_id: Optional[str] = None


_memories: Dict[str, PendingMemory] = {}
# Process-local freeze: session_id → text at first load this session.
_frozen_user_by_session: Dict[str, str] = {}
_frozen_memory_by_session: Dict[str, str] = {}


def normalize_memory_target(raw: Any) -> MemoryTarget:
    key = str(raw or "user").strip().lower()
    if key in ("memory", "project", "env", "environment"):
        return "memory"
    return "user"


def get_user_md_char_limit() -> int:
    """Effective USER.md char limit (settings clamp 500–8000, default 1375)."""
    try:
        from agent_window.services.agent_settings import load_agent_settings

        raw = load_agent_settings().get("user_md_char_limit")
        if raw is None:
            return USER_MD_CHAR_LIMIT
        return max(500, min(8000, int(raw)))
    except Exception:
        return USER_MD_CHAR_LIMIT


def get_memory_md_char_limit() -> int:
    """Effective MEMORY.md char limit (settings clamp 500–8000, default 2200)."""
    try:
        from agent_window.services.agent_settings import load_agent_settings

        raw = load_agent_settings().get("memory_md_char_limit")
        if raw is None:
            return MEMORY_MD_CHAR_LIMIT
        return max(500, min(8000, int(raw)))
    except Exception:
        return MEMORY_MD_CHAR_LIMIT


def get_char_limit_for_target(target: MemoryTarget | str) -> int:
    t = normalize_memory_target(target)
    return get_memory_md_char_limit() if t == "memory" else get_user_md_char_limit()


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
                "target": m.target,
                "status": m.status.value,
                "error": m.error,
                "created_at": m.created_at,
                "decision": m.decision,
                "op_summary": m.op_summary or "",
                "session_id": m.session_id,
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
            target=normalize_memory_target(item.get("target")),
            status=status,
            error=item.get("error"),
            created_at=float(item.get("created_at") or time.time()),
            decision=item.get("decision"),
            op_summary=str(item.get("op_summary") or ""),
            session_id=(str(item["session_id"]) if item.get("session_id") else None),
        )
        _memories[mem.id] = mem
        count += 1
    if count:
        logger.info("restored %s persisted memories", count)
    return count


def _user_dir() -> Path:
    return Path(settings.app_data_dir) / "users" / settings.default_user_id


def user_md_path() -> Path:
    return _user_dir() / "USER.md"


def memory_md_path() -> Path:
    return _user_dir() / "MEMORY.md"


def path_for_target(target: MemoryTarget | str) -> Path:
    return memory_md_path() if normalize_memory_target(target) == "memory" else user_md_path()


def read_user_md() -> str:
    path = user_md_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def read_memory_md() -> str:
    path = memory_md_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def read_for_target(target: MemoryTarget | str) -> str:
    return read_memory_md() if normalize_memory_target(target) == "memory" else read_user_md()


def write_user_md(content: str) -> None:
    path = user_md_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_memory_md(content: str) -> None:
    path = memory_md_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_for_target(target: MemoryTarget | str, content: str) -> None:
    if normalize_memory_target(target) == "memory":
        write_memory_md(content)
    else:
        write_user_md(content)


def freeze_user_md_for_session(session_id: str, *, force: bool = False) -> str:
    """Freeze USER.md text for this session (first use / force refresh)."""
    sid = (session_id or "").strip()
    if not sid:
        return read_user_md()
    if not force and sid in _frozen_user_by_session:
        return _frozen_user_by_session[sid]
    text = read_user_md()
    _frozen_user_by_session[sid] = text
    return text


def freeze_memory_md_for_session(session_id: str, *, force: bool = False) -> str:
    """Freeze MEMORY.md text for this session (first use / force refresh)."""
    sid = (session_id or "").strip()
    if not sid:
        return read_memory_md()
    if not force and sid in _frozen_memory_by_session:
        return _frozen_memory_by_session[sid]
    text = read_memory_md()
    _frozen_memory_by_session[sid] = text
    return text


def get_frozen_user_md(session_id: str) -> str:
    """Return frozen USER.md for session; freeze from disk if missing."""
    return freeze_user_md_for_session(session_id, force=False)


def get_frozen_memory_md(session_id: str) -> str:
    """Return frozen MEMORY.md for session; freeze from disk if missing."""
    return freeze_memory_md_for_session(session_id, force=False)


def clear_memory_snapshot(session_id: str | None = None) -> None:
    """Clear freeze caches for one session, or all if session_id is None."""
    if session_id is None:
        _frozen_user_by_session.clear()
        _frozen_memory_by_session.clear()
        return
    sid = (session_id or "").strip()
    if sid:
        _frozen_user_by_session.pop(sid, None)
        _frozen_memory_by_session.pop(sid, None)


def _status_for_file(path: Path, content: str, limit: int) -> Dict[str, Any]:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    chars = len(content)
    usage_ratio = (chars / limit) if limit > 0 else 0.0
    return {
        "exists": exists,
        "path": str(path),
        "size": size,
        "preview": (content[:400] if exists else ""),
        "chars": chars,
        "limit": limit,
        "usage_ratio": usage_ratio,
    }


def memory_status() -> Dict[str, Any]:
    """Back-compat: USER.md status (plus nested ``memory_md`` for MEMORY.md)."""
    user = _status_for_file(user_md_path(), read_user_md(), get_user_md_char_limit())
    mem = _status_for_file(memory_md_path(), read_memory_md(), get_memory_md_char_limit())
    out = dict(user)
    out["target"] = "user"
    out["memory_md"] = {**mem, "target": "memory"}
    return out


def memory_status_for_target(target: MemoryTarget | str) -> Dict[str, Any]:
    t = normalize_memory_target(target)
    if t == "memory":
        return {**_status_for_file(memory_md_path(), read_memory_md(), get_memory_md_char_limit()), "target": "memory"}
    return {**_status_for_file(user_md_path(), read_user_md(), get_user_md_char_limit()), "target": "user"}


def _raise_memory_full(
    final_len: int,
    limit: int,
    *,
    target: MemoryTarget,
    entries: Optional[Sequence[str]] = None,
) -> None:
    label = "MEMORY.md" if target == "memory" else "USER.md"
    hint = (
        f"{label} would exceed {limit} chars ({final_len}/{limit}). "
        "MEMORY_FULL: do not append — propose_memory action=replace/remove "
        f"(or mode=replace) with target={target} to shrink, then add again; "
        "never silent truncate."
    )
    if entries is not None:
        preview = [e[:200] for e in entries[:12]]
        hint += " current_entries=" + json.dumps(preview, ensure_ascii=False)
    raise WorkspaceError(hint, "MEMORY_FULL")


def parse_memory_entries(text: str) -> List[str]:
    """Split curated memory into entries.

    Primary delimiter: ``\\n§\\n``. Legacy files without § that use blank-line
    separated blocks are treated as multiple entries so add/dedupe still work;
    the next write normalizes them to § separators.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    if ENTRY_SEP in raw:
        return [p.strip() for p in raw.split(ENTRY_SEP) if p.strip()]
    # Lone-line § (some editors) or § with surrounding blank lines
    if re.search(r"^\s*§\s*$", raw, flags=re.MULTILINE):
        parts = re.split(r"\n\s*§\s*\n", raw)
        return [p.strip() for p in parts if p.strip()]
    if "\n\n" in raw:
        parts = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
        if len(parts) > 1:
            return parts
    return [raw]


def join_memory_entries(entries: Sequence[str]) -> str:
    cleaned = [e.strip() for e in entries if e and str(e).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0].strip() + "\n"
    return ENTRY_SEP.join(cleaned).strip() + "\n"


def _reject_duplicate_entries(entries: Sequence[str]) -> None:
    seen: set[str] = set()
    for e in entries:
        key = e.strip()
        if not key:
            continue
        if key in seen:
            raise WorkspaceError(
                "duplicate entry: identical content already present",
                "DUPLICATE",
            )
        seen.add(key)


def normalize_memory_body(text: str) -> str:
    """Parse entries (incl. legacy blank lines) and re-join with §."""
    entries = parse_memory_entries(text)
    _reject_duplicate_entries(entries)
    return join_memory_entries(entries)


def _find_unique_entry_index(entries: Sequence[str], old_text: str) -> int:
    needle = (old_text or "").strip()
    if not needle:
        raise WorkspaceError("old_text is required for replace/remove", "INVALID")
    matches = [i for i, e in enumerate(entries) if needle in e]
    if not matches:
        raise WorkspaceError(
            "old_text matched no entry; read current memory or use a longer unique substring",
            "NOT_FOUND",
        )
    if len(matches) > 1:
        raise WorkspaceError(
            "old_text matched multiple entries; use a longer unique substring",
            "AMBIGUOUS",
        )
    return matches[0]


def apply_entry_operation(entries: List[str], op: Dict[str, Any]) -> List[str]:
    """Apply one entry op to a working list; returns new list (may mutate copy)."""
    action = str(op.get("action") or "").strip().lower()
    if action not in ("add", "replace", "remove"):
        raise WorkspaceError(
            "action must be add, replace, or remove",
            "INVALID",
        )
    out = list(entries)
    if action == "add":
        content = str(op.get("content") or "").strip()
        if not content:
            raise WorkspaceError("content is required for add", "INVALID")
        if any(e.strip() == content for e in out):
            raise WorkspaceError(
                "duplicate entry: identical content already present",
                "DUPLICATE",
            )
        out.append(content)
        return out
    if action == "remove":
        idx = _find_unique_entry_index(out, str(op.get("old_text") or ""))
        out.pop(idx)
        return out
    # replace
    idx = _find_unique_entry_index(out, str(op.get("old_text") or ""))
    content = str(op.get("content") or "").strip()
    if not content:
        raise WorkspaceError("content is required for replace", "INVALID")
    out[idx] = content
    return out


def apply_entry_operations(entries: List[str], ops: Sequence[Dict[str, Any]]) -> List[str]:
    working = list(entries)
    if not ops:
        raise WorkspaceError("operations must be a non-empty list", "INVALID")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise WorkspaceError(f"operations[{i}] must be an object", "INVALID")
        working = apply_entry_operation(working, op)
    return working


def _finalize_proposal(
    *,
    final: str,
    mode: str,
    target: MemoryTarget,
    op_summary: str = "",
) -> PendingMemory:
    limit = get_char_limit_for_target(target)
    # Always normalize separators + reject duplicate blocks (even mode=replace).
    normalized = normalize_memory_body(final) if final.strip() else ""
    entries = parse_memory_entries(normalized)
    if len(normalized) > limit:
        _raise_memory_full(len(normalized), limit, target=target, entries=entries)
    item = PendingMemory(
        id=str(uuid.uuid4()),
        content=normalized,
        mode=mode,
        preview=(normalized[:1200] if normalized else "(empty)"),
        target=target,
        op_summary=op_summary,
        session_id=get_turn_session_id(),
    )
    if not item.content.strip():
        item.content = ""
        item.preview = "(empty)"
    _memories[item.id] = item
    _save_memories()
    return item


def create_memory_proposal(
    content: str = "",
    mode: str = "replace",
    target: MemoryTarget | str = "user",
    *,
    action: Optional[str] = None,
    old_text: Optional[str] = None,
    operations: Optional[Sequence[Dict[str, Any]]] = None,
) -> PendingMemory:
    """Create a pending memory write (whole-file M0 or entry ops M1)."""
    t = normalize_memory_target(target)
    limit = get_char_limit_for_target(t)

    # M1 batch
    if operations is not None:
        existing = parse_memory_entries(read_for_target(t))
        new_entries = apply_entry_operations(existing, list(operations))
        _reject_duplicate_entries(new_entries)
        final = join_memory_entries(new_entries)
        if len(final) > limit:
            _raise_memory_full(len(final), limit, target=t, entries=new_entries)
        summary = f"{len(operations)} ops → {len(new_entries)} entries"
        return _finalize_proposal(final=final, mode="operations", target=t, op_summary=summary)

    # M1 single entry action (mode=append is an alias for action=add)
    file_mode = (mode or "replace").strip().lower()
    act = (action or "").strip().lower()
    if not act and file_mode == "append":
        act = "add"
    if act in ("add", "replace", "remove"):
        existing = parse_memory_entries(read_for_target(t))
        op: Dict[str, Any] = {"action": act, "content": content, "old_text": old_text}
        new_entries = apply_entry_operation(existing, op)
        _reject_duplicate_entries(new_entries)
        final = join_memory_entries(new_entries)
        if len(final) > limit:
            _raise_memory_full(len(final), limit, target=t, entries=new_entries)
        return _finalize_proposal(
            final=final,
            mode=act,
            target=t,
            op_summary=f"{act} → {len(new_entries)} entries",
        )

    # M0 whole-file replace only (append already aliased to add above)
    text = (content or "").strip()
    if file_mode != "replace":
        raise WorkspaceError(
            "mode must be replace (or use action=add|replace|remove / mode=append→add)",
            "INVALID",
        )
    final = (text + "\n") if text else ""
    if text and len(text) > limit:
        _raise_memory_full(len(text), limit, target=t)
    # normalize_memory_body inside finalize rejects duplicate paragraphs
    if len(final) > limit:
        _raise_memory_full(len(final), limit, target=t, entries=parse_memory_entries(final))
    return _finalize_proposal(final=final, mode="replace", target=t, op_summary="replace")


def get_memory(proposal_id: str) -> Optional[PendingMemory]:
    return _memories.get(proposal_id)


def memory_to_public(item: PendingMemory) -> Dict[str, Any]:
    return {
        "id": item.id,
        "mode": item.mode,
        "preview": item.preview,
        "content": item.content,
        "target": item.target,
        "status": item.status.value,
        "error": item.error,
        "op_summary": item.op_summary or "",
        "session_id": item.session_id,
    }


def list_pending_memories(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    sid = (session_id or "").strip() or None
    out: List[Dict[str, Any]] = []
    for m in _memories.values():
        if m.status not in LISTABLE_MEMORY_STATUSES:
            continue
        if sid is not None and (m.session_id or "") != sid:
            continue
        out.append(memory_to_public(m))
    return out


def cancel_pending_memories(session_id: Optional[str] = None) -> int:
    sid = (session_id or "").strip() or None
    n = 0
    for item in _memories.values():
        if item.status != MemoryStatus.PENDING:
            continue
        if sid is not None and (item.session_id or "") != sid:
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
        write_for_target(item.target, item.content)
        item.status = MemoryStatus.APPLIED
    except Exception as e:
        item.status = MemoryStatus.FAILED
        item.error = str(e)
    item.event.set()
    _save_memories()
    return item


async def wait_for_memory_decision(
    proposal_id: str,
    timeout: float | None = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> PendingMemory:
    if timeout is None:
        from agent_window.services.agent_settings import load_agent_settings

        timeout = float(load_agent_settings().get("approval_timeout_sec") or APPROVAL_TIMEOUT_SEC)
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


# Short stable guidance injected into system (M0+M1).
MEMORY_GUIDANCE = (
    "## Memory guidance\n"
    "- Preferences, address forms, communication habits → propose_memory target=user (USER.md).\n"
    "- Workspace conventions, common commands, pitfalls, durable project facts → "
    "propose_memory target=memory (MEMORY.md).\n"
    "- ALWAYS prefer action=add|replace|remove (old_text = unique substring for "
    "replace/remove). Do NOT use mode=replace to add a fact — that overwrites the whole file.\n"
    "- mode=append is treated as action=add. Entries are stored with a § separator.\n"
    "- Exact-duplicate add is rejected (DUPLICATE). Ephemeral progress / PR numbers → do NOT "
    "write memory (Goal checkpoints or chat only).\n"
    "- How-to procedures → Skills, not MEMORY.md.\n"
    "- When MEMORY_FULL: action=replace/remove to shrink, then add; never silent truncate.\n"
    "- Mid-session applies update disk immediately; this session's system snapshot stays frozen "
    "until a new session."
)
