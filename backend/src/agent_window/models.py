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
    is_favorite = Column(Boolean, default=False)
    summary = Column(Text, default="")
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


def get_db():
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
