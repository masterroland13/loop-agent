"""F6 middle tier: placeholder assistant + incremental TurnEvent persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from agent_window.agent.turn_event import event_from_sse, parse_trace, serialize_trace
from agent_window.models import Message, Role, Session as SessionModel
from agent_window.services.storage import add_message, write_turn_blob


class TurnTraceWriter:
    """Persists turn events and streaming content onto a placeholder assistant row."""

    def __init__(self, db: Session, session: SessionModel, assistant: Message) -> None:
        self.db = db
        self.session = session
        self.assistant = assistant
        self._events: list[dict[str, Any]] = parse_trace(assistant.trace)
        self._content_parts: list[str] = [assistant.content or ""]
        if self._content_parts == [""]:
            self._content_parts = []
        self._token_commit_counter = 0
        self._blob_seq = sum(
            1
            for e in self._events
            if isinstance(e.get("full_ref"), str) and str(e["full_ref"]).startswith("file:")
        )

    @classmethod
    def create_placeholder(
        cls,
        db: Session,
        session: SessionModel,
        sequence: int,
    ) -> TurnTraceWriter:
        assistant = add_message(
            db,
            session,
            Role.ASSISTANT,
            "",
            sequence,
            summary="",
            trace="[]",
        )
        return cls(db, session, assistant)

    @property
    def assistant_id(self) -> str:
        return self.assistant.id

    def _spill(self, text: str) -> str:
        self._blob_seq += 1
        return write_turn_blob(self.session, self.assistant.id, self._blob_seq, text)

    def note_sse(self, event: dict[str, Any]) -> dict[str, Any] | None:
        mapped = event_from_sse(event, spill=self._spill)
        if mapped:
            self._events.append(mapped)
            self._commit_trace()

        etype = event.get("type")
        if etype == "token" and event.get("content"):
            self._content_parts.append(str(event["content"]))
            self._token_commit_counter += 1
            if self._token_commit_counter >= 8:
                self._commit_content()

        if etype == "error":
            self._events.append(
                {
                    "type": "error",
                    "ts": event.get("ts"),
                    "status": event.get("code") or "error",
                    "summary": event.get("message") or "error",
                }
            )
            self._commit_trace()

        return mapped

    def _commit_trace(self) -> None:
        self.assistant.trace = serialize_trace(self._events)
        self.db.add(self.assistant)
        self.db.commit()
        self.db.refresh(self.assistant)

    def _commit_content(self) -> None:
        self.assistant.content = "".join(self._content_parts)
        self.db.add(self.assistant)
        self.db.commit()
        self.db.refresh(self.assistant)
        self._token_commit_counter = 0

    def finalize(self, *, summary: str, content: str | None = None) -> Message:
        final_content = (content if content is not None else "".join(self._content_parts)).strip()
        self.assistant.content = final_content
        self.assistant.summary = summary
        self.assistant.trace = serialize_trace(self._events)
        self.session.updated_at = datetime.utcnow()
        self.db.add(self.assistant)
        self.db.add(self.session)
        self.db.commit()
        self.db.refresh(self.assistant)
        return self.assistant

    def finalize_interrupted(self, *, code: str, message: str) -> Message:
        """Persist partial trace/content when a turn ends with error or cancel."""
        if not any(e.get("type") == "error" for e in self._events):
            self._events.append(
                {
                    "type": "error",
                    "status": code,
                    "summary": message,
                }
            )
        partial = "".join(self._content_parts).strip()
        if code == "TURN_CANCELLED":
            summary_type = "turn_cancelled"
        else:
            summary_type = "turn_failed"
        summary = json.dumps(
            {"type": summary_type, "code": code, "message": message, "message_id": self.assistant.id},
            ensure_ascii=False,
        )
        self.assistant.content = partial or message
        self.assistant.summary = summary
        self.assistant.trace = serialize_trace(self._events)
        self.session.updated_at = datetime.utcnow()
        self.db.add(self.assistant)
        self.db.add(self.session)
        self.db.commit()
        self.db.refresh(self.assistant)
        return self.assistant

    def delete_placeholder(self) -> None:
        self.db.delete(self.assistant)
        self.db.commit()


def trace_for_response(message: Message) -> list[dict[str, Any]]:
    return parse_trace(message.trace)


def is_turn_in_progress(message: Message, *, session_active: bool) -> bool:
    if not session_active:
        return False
    if message.summary:
        try:
            parsed = json.loads(message.summary)
            if isinstance(parsed, dict) and parsed.get("type") in (
                "turn_meta",
                "turn_cancelled",
                "turn_failed",
            ):
                return False
        except (json.JSONDecodeError, TypeError):
            pass
    events = parse_trace(message.trace)
    return bool(events) or not (message.content or "").strip()
