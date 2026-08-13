"""Audit event emitter and listing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

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
) -> List[AuditEvent]:
    q = db.query(AuditEvent).order_by(AuditEvent.created_at.desc())
    if session_id:
        q = q.filter(AuditEvent.session_id == session_id)
    return q.limit(max(1, min(200, limit))).all()


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
