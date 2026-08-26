"""Audit event emitter and listing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from agent_window.models import AuditEvent


def emit_audit(
    db: Session,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        id=str(uuid.uuid4()),
        session_id=session_id,
        event_type=event_type,
        payload=json.dumps(payload or {}, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_audit_events(
    db: Session,
    limit: int = 50,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> List[AuditEvent]:
    q = db.query(AuditEvent).order_by(AuditEvent.created_at.desc())
    if session_id:
        q = q.filter(AuditEvent.session_id == session_id)
    if event_type:
        # Exact match or prefix ("turn." → turn.complete / turn.start)
        if event_type.endswith("."):
            q = q.filter(AuditEvent.event_type.startswith(event_type))
        else:
            q = q.filter(AuditEvent.event_type == event_type)
    return q.limit(max(1, min(500, limit))).all()


def list_audit_session_summaries(db: Session, *, limit: int = 50) -> List[Dict[str, Any]]:
    """Sessions that have audit rows, newest activity first."""
    rows = (
        db.query(
            AuditEvent.session_id,
            func.count(AuditEvent.id).label("event_count"),
            func.max(AuditEvent.created_at).label("last_at"),
        )
        .filter(AuditEvent.session_id.isnot(None))
        .filter(AuditEvent.session_id != "")
        .group_by(AuditEvent.session_id)
        .order_by(func.max(AuditEvent.created_at).desc())
        .limit(max(1, min(200, limit)))
        .all()
    )
    out: List[Dict[str, Any]] = []
    for session_id, event_count, last_at in rows:
        out.append(
            {
                "session_id": session_id,
                "event_count": int(event_count or 0),
                "last_at": last_at,
            }
        )
    return out


def audit_to_public(event: AuditEvent) -> Dict[str, Any]:
    try:
        payload = json.loads(event.payload or "{}")
    except Exception:
        payload = {"raw": event.payload}
    return {
        "id": event.id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "payload": payload,
        "created_at": event.created_at,
    }
