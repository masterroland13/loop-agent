"""Persist a compaction summary onto the session tree (C1).

Folded messages stay in SQLite and JSONL. Only the active parent chain
skips them: summary.parent_id = first-folded.parent_id, first keep_recent
relinks onto the summary. leaf_id is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from agent_window.core.session_tree import (
    build_path_from_session,
    persistable_path_messages,
)
from agent_window.models import Role
from agent_window.services.compress import (
    DEFAULT_KEEP_FOLDED_USER_TOKENS,
    CompressMeta,
    find_cut_index,
    select_folded_user_originals,
)
from agent_window.services.storage import add_message, update_message_parent

logger = logging.getLogger(__name__)

_PERSISTABLE_METHODS = frozenset({"llm", "extractive"})


def persist_compaction_on_tree(
    db: Session,
    session,
    *,
    prior_path: list,
    new_user: Any | None,
    meta: Any,
    strict_align: bool = True,
) -> Optional[Any]:
    """Write compaction_summary and relink keep_recent. Returns the new row or None."""
    method = str(getattr(meta, "method", "") or "")
    if method not in _PERSISTABLE_METHODS:
        return None
    content = str(getattr(meta, "summary_content", "") or "").strip()
    if not content:
        return None
    cut = int(getattr(meta, "cut_index", 0) or 0)

    rest_rows = list(persistable_path_messages(prior_path))
    if new_user is not None:
        rest_rows.append(new_user)
    rest_count = int(getattr(meta, "rest_count", 0) or 0)
    if rest_count and rest_count != len(rest_rows):
        if strict_align:
            logger.warning(
                "compaction persist skipped: rest_count=%s rows=%s",
                rest_count,
                len(rest_rows),
            )
            return None
    if cut <= 0 or cut >= len(rest_rows):
        if strict_align:
            return None
        cut = max(1, len(rest_rows) - 4)
        if cut <= 0 or cut >= len(rest_rows):
            return None

    older = rest_rows[:cut]
    recent = rest_rows[cut:]
    first_recent = recent[0]
    first_older_parent = getattr(older[0], "parent_id", None) if older else None
    first_recent_id = getattr(first_recent, "id", None)
    if not first_recent_id:
        return None

    all_msgs = sorted(session.messages, key=lambda m: m.sequence)
    sequence = (all_msgs[-1].sequence + 1) if all_msgs else 1

    summary = add_message(
        db,
        session,
        Role.USER,
        content,
        sequence,
        parent_id=first_older_parent,
        entry_type="compaction_summary",
        update_leaf=False,
    )
    budget = int(
        getattr(meta, "keep_folded_user_tokens", None) or DEFAULT_KEEP_FOLDED_USER_TOKENS
    )
    kept_users = select_folded_user_originals(older, token_budget=budget)
    planned: list[tuple[Any, str | None]] = [
        (row, getattr(row, "parent_id", None)) for row in kept_users if getattr(row, "id", None)
    ]
    hang_from = summary.id
    relinked: list[tuple[str, str | None]] = []
    for row, previous_parent in planned:
        row_id = getattr(row, "id", None)
        updated_kept = update_message_parent(db, row_id, hang_from)
        if updated_kept is None:
            logger.warning("compaction persist: kept user %s missing; rolling back", row_id)
            _rollback_persist(db, session, summary, relinked)
            return None
        relinked.append((row_id, previous_parent))
        hang_from = row_id
    updated = update_message_parent(db, first_recent_id, hang_from)
    if updated is None:
        logger.warning(
            "compaction persist: keep_recent %s missing after summary write; rolling back",
            first_recent_id,
        )
        _rollback_persist(db, session, summary, relinked)
        return None
    db.refresh(session)
    return summary


def persist_compaction_from_tree(db: Session, session, meta: Any) -> Optional[Any]:
    """Fold the current leaf path using a cut computed on the tree, not working msgs.

    Mid-loop compress lists include tool blobs that are not rows. Reusing that
    cut/rest_count would write the wrong span. The summary text still comes from
    the compress that just ran.
    """
    method = str(getattr(meta, "method", "") or "")
    if method not in _PERSISTABLE_METHODS:
        return None
    content = str(getattr(meta, "summary_content", "") or "").strip()
    if not content:
        return None
    path = persistable_path_messages(build_path_from_session(session))
    if len(path) < 3:
        return None
    rest: list[dict] = []
    for row in path:
        role = getattr(row, "role", None)
        role_value = role.value if hasattr(role, "value") else str(role or "")
        rest.append({"role": role_value, "content": getattr(row, "content", None) or ""})
    cut = find_cut_index(rest)
    if cut <= 0 or cut >= len(path):
        return None
    aligned = CompressMeta(
        method=method,
        summary_preview=str(getattr(meta, "summary_preview", "") or ""),
        older_count=cut,
        used_previous_summary=bool(getattr(meta, "used_previous_summary", False)),
        cut_index=cut,
        rest_count=len(path),
        summary_content=content,
        kept_folded_user_count=int(getattr(meta, "kept_folded_user_count", 0) or 0),
        keep_folded_user_tokens=int(
            getattr(meta, "keep_folded_user_tokens", None) or DEFAULT_KEEP_FOLDED_USER_TOKENS
        ),
    )
    return persist_compaction_on_tree(
        db,
        session,
        prior_path=path,
        new_user=None,
        meta=aligned,
        strict_align=True,
    )


def _rollback_persist(db: Session, session, summary, relinked: list[tuple[str, str | None]]) -> None:
    """Undo this persist only. Folded originals stay in SQLite."""
    for row_id, previous_parent in reversed(relinked):
        update_message_parent(db, row_id, previous_parent)
    row = summary
    if row is not None:
        db.delete(row)
        db.commit()
        db.refresh(session)
