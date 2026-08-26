import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from agent_window.config import settings
from agent_window.models import Message, Role, Session as SessionModel


def sanitize_filename(text: str) -> str:
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[^\w\-_.]", "", text)
    return text[:64] or "untitled"


def ensure_user_data_dir(user_id: str = settings.default_user_id) -> Path:
    data_dir = Path(settings.app_data_dir) / "users" / user_id / "sessions"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def create_session(
    db: Session,
    title: str,
    user_id: str = settings.default_user_id,
    workspace_root: str | None = None,
) -> SessionModel:
    data_dir = ensure_user_data_dir(user_id)
    session_id = f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    session_path = data_dir / session_id
    session_path.mkdir(parents=True, exist_ok=True)

    root = (workspace_root or "").strip() or None

    session = SessionModel(
        id=session_id,
        user_id=user_id,
        title=title,
        data_path=str(session_path.relative_to(Path(settings.app_data_dir))),
        workspace_root=root,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_path(session: SessionModel) -> Path:
    return Path(settings.app_data_dir) / session.data_path


def write_turn_blob(session: SessionModel, assistant_id: str, seq: int, text: str) -> str:
    """
    Spill oversized turn payload under session.data_path/turns/{assistant}/e{n}.txt.

    Returns a file: relative ref (posix) suitable for TurnEvent.full_ref.
    """
    from agent_window.agent.turn_event import FILE_REF_PREFIX

    safe_asst = sanitize_filename(assistant_id) or "assistant"
    rel = Path("turns") / safe_asst / f"e{int(seq)}.txt"
    abs_path = get_session_path(session) / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text, encoding="utf-8")
    return f"{FILE_REF_PREFIX}{rel.as_posix()}"


def resolve_session_blob_path(session: SessionModel, rel_path: str) -> Path:
    """Resolve a relative path under session.data_path; reject traversal."""
    cleaned = (rel_path or "").replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("invalid blob path")
    root = get_session_path(session).resolve()
    target = (root / cleaned).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("blob path escapes session data_path") from exc
    return target


def read_session_blob(session: SessionModel, file_ref: str) -> str:
    """Read a file: ref written by write_turn_blob."""
    from agent_window.agent.turn_event import file_ref_path

    rel = file_ref_path(file_ref)
    path = resolve_session_blob_path(session, rel)
    if not path.is_file():
        raise FileNotFoundError(rel)
    return path.read_text(encoding="utf-8")


def append_message_to_markdown(session: SessionModel, message: Message) -> None:
    session_path = get_session_path(session)
    session_md = session_path / "session.md"

    header = f"""---
session_id: {session.id}
title: {session.title}
updated_at: {datetime.utcnow().isoformat()}
---

"""

    if not session_md.exists():
        session_md.write_text(header, encoding="utf-8")

    prefix = "## User" if message.role == Role.USER else "## Agent"
    timestamp = message.created_at.isoformat() if message.created_at else datetime.utcnow().isoformat()
    block = f"\n{prefix} ({message.id}) at {timestamp}\n\n{message.content}\n\n"

    with session_md.open("a", encoding="utf-8") as f:
        f.write(block)


def list_sessions(db: Session, user_id: str = settings.default_user_id) -> List[SessionModel]:
    return db.query(SessionModel).filter(SessionModel.user_id == user_id).order_by(SessionModel.updated_at.desc()).all()


def get_session(db: Session, session_id: str) -> Optional[SessionModel]:
    return db.query(SessionModel).filter(SessionModel.id == session_id).first()


def update_session_title(db: Session, session: SessionModel, title: str) -> SessionModel:
    session.title = title
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


def add_message(
    db: Session,
    session: SessionModel,
    role: Role,
    content: str,
    sequence: int,
    *,
    summary: str = "",
    trace: str = "[]",
    attachments: str = "[]",
) -> Message:
    message = Message(
        session_id=session.id,
        role=role,
        content=content,
        sequence=sequence,
        summary=summary,
        trace=trace,
        attachments=attachments,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    append_message_to_markdown(session, message)
    session.updated_at = datetime.utcnow()
    db.commit()
    return message


def delete_session(db: Session, session: SessionModel) -> None:
    session_path = get_session_path(session)
    # Delete messages explicitly so SQLite/ORM never tries to NULL session_id.
    db.query(Message).filter(Message.session_id == session.id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    if session_path.exists():
        shutil.rmtree(session_path, ignore_errors=True)


def get_message(db: Session, message_id: str) -> Optional[Message]:
    return db.query(Message).filter(Message.id == message_id).first()


def delete_message(db: Session, message: Message) -> None:
    db.delete(message)
    db.commit()


def toggle_message_favorite(db: Session, message: Message, is_favorite: bool) -> Message:
    message.is_favorite = is_favorite
    db.commit()
    db.refresh(message)
    return message


def list_favorites(db: Session, user_id: str = settings.default_user_id) -> List[dict]:
    favorited = (
        db.query(Message)
        .join(SessionModel)
        .filter(SessionModel.user_id == user_id, Message.is_favorite.is_(True), Message.role == Role.USER)
        .order_by(Message.created_at.desc())
        .all()
    )

    results: List[dict] = []
    for user_message in favorited:
        session = user_message.session
        assistant = (
            db.query(Message)
            .filter(
                Message.session_id == user_message.session_id,
                Message.role == Role.ASSISTANT,
                Message.sequence == user_message.sequence + 1,
            )
            .first()
        )
        results.append(
            {
                "id": user_message.id,
                "session_id": session.id,
                "session_title": session.title,
                "user_content": user_message.content,
                "assistant_content": assistant.content if assistant else "",
                "created_at": user_message.created_at,
            }
        )
    return results
