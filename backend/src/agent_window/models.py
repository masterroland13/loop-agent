import enum
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from agent_window.config import settings

Base = declarative_base()


class Role(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=False, default=settings.default_user_id)
    title = Column(String(255), nullable=False)
    data_path = Column(String(512), nullable=False)
    workspace_root = Column(String(1024), nullable=True)
    goal_mode = Column(Boolean, nullable=False, default=False)
    pinned_goal = Column(Text, nullable=True)
    leaf_id = Column(String(36), nullable=True)
    profile_id = Column(String(64), nullable=True)
    model_id = Column(String(128), nullable=True)
    # True after the user renames the chat. Auto titles must not replace it.
    title_locked = Column(Boolean, nullable=False, default=False)
    # Sidebar clock. Set from the latest user instruction only.
    last_prompt_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "Message",
        back_populates="session",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(Role), nullable=False)
    content = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)
    parent_id = Column(String(36), nullable=True, index=True)
    entry_type = Column(String(32), nullable=False, default="message")
    is_favorite = Column(Boolean, default=False)
    summary = Column(Text, default="")
    trace = Column(Text, default="[]")
    attachments = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="messages")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        data_dir = Path(settings.app_data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "agent_window.db"
        _engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

        from sqlalchemy import event

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db():
    Base.metadata.create_all(bind=get_engine())
    _migrate_messages_trace()
    _migrate_messages_attachments()
    _migrate_sessions_workspace_root()
    _migrate_sessions_goal_mode()
    _migrate_sessions_pinned_goal()
    _migrate_messages_parent_id()
    _migrate_messages_entry_type()
    _migrate_sessions_leaf_id()
    _migrate_sessions_model_binding()
    _migrate_sessions_title_locked()
    _migrate_sessions_last_prompt_at()
    _backfill_message_tree()


def _migrate_messages_trace() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        names = {row[1] for row in cols}
        if "trace" not in names:
            conn.execute(text("ALTER TABLE messages ADD COLUMN trace TEXT DEFAULT '[]'"))
            conn.commit()


def _migrate_messages_attachments() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        names = {row[1] for row in cols}
        if "attachments" not in names:
            conn.execute(text("ALTER TABLE messages ADD COLUMN attachments TEXT DEFAULT '[]'"))
            conn.commit()




def _migrate_sessions_workspace_root() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "workspace_root" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN workspace_root VARCHAR(1024)"))
            conn.commit()


def _migrate_sessions_goal_mode() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "goal_mode" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN goal_mode BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()


def _migrate_sessions_pinned_goal() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "pinned_goal" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN pinned_goal TEXT"))
            conn.commit()


def _migrate_messages_parent_id() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        names = {row[1] for row in cols}
        if "parent_id" not in names:
            conn.execute(text("ALTER TABLE messages ADD COLUMN parent_id VARCHAR(36)"))
            conn.commit()
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_parent_id ON messages (parent_id)"))
        conn.commit()


def _migrate_messages_entry_type() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        names = {row[1] for row in cols}
        if "entry_type" not in names:
            conn.execute(
                text("ALTER TABLE messages ADD COLUMN entry_type VARCHAR(32) NOT NULL DEFAULT 'message'")
            )
            conn.commit()


def _migrate_sessions_leaf_id() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "leaf_id" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN leaf_id VARCHAR(36)"))
            conn.commit()


def _migrate_sessions_model_binding() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "profile_id" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN profile_id VARCHAR(64)"))
        if "model_id" not in names:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN model_id VARCHAR(128)"))
        conn.commit()


def _migrate_sessions_title_locked() -> None:
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "title_locked" in names:
            return
        conn.execute(
            text("ALTER TABLE sessions ADD COLUMN title_locked BOOLEAN NOT NULL DEFAULT 0")
        )
        conn.execute(
            text(
                "UPDATE sessions SET title_locked = 1 "
                "WHERE title IS NOT NULL AND trim(title) NOT IN ('新对话', 'New Chat')"
            )
        )
        conn.commit()


def _migrate_sessions_last_prompt_at() -> None:
    """Add sessions.last_prompt_at and backfill from the latest user message."""
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        names = {row[1] for row in cols}
        if "last_prompt_at" in names:
            return
        conn.execute(text("ALTER TABLE sessions ADD COLUMN last_prompt_at DATETIME"))
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        if "messages" in tables:
            conn.execute(
                text(
                    "UPDATE sessions SET last_prompt_at = ("
                    " SELECT MAX(created_at) FROM messages"
                    " WHERE messages.session_id = sessions.id"
                    " AND lower(messages.role) = 'user'"
                    " AND coalesce(messages.entry_type, 'message') = 'message'"
                    " )"
                )
            )
        conn.commit()


def _backfill_message_tree() -> None:
    """Linearize legacy sessions into a parent chain; set leaf_id to last message."""
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        sessions = conn.execute(text("SELECT id, leaf_id FROM sessions")).fetchall()
        for session_id, leaf_id in sessions:
            rows = conn.execute(
                text(
                    "SELECT id, parent_id FROM messages "
                    "WHERE session_id = :sid ORDER BY sequence ASC, created_at ASC"
                ),
                {"sid": session_id},
            ).fetchall()
            if not rows:
                continue
            prev_id = None
            for msg_id, parent_id in rows:
                if parent_id is None and prev_id is not None:
                    conn.execute(
                        text("UPDATE messages SET parent_id = :pid WHERE id = :mid"),
                        {"pid": prev_id, "mid": msg_id},
                    )
                elif parent_id is None and prev_id is None:
                    # root stays null
                    pass
                prev_id = msg_id
            if leaf_id is None and prev_id is not None:
                conn.execute(
                    text("UPDATE sessions SET leaf_id = :lid WHERE id = :sid"),
                    {"lid": prev_id, "sid": session_id},
                )
        conn.commit()


def get_db():
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
