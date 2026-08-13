from pathlib import Path

from sqlalchemy import create_engine, text

from agent_window.config import settings

db = Path(settings.app_data_dir) / "agent_window.db"
print("db", db.resolve(), db.exists())
engine = create_engine(f"sqlite:///{db}")
with engine.begin() as conn:
    rows = conn.execute(
        text(
            "SELECT id, session_id, role, length(content) "
            "FROM messages WHERE trim(content) = '' OR content IS NULL"
        )
    ).fetchall()
    print("empty_count", len(rows))
    for row in rows:
        print(row)
    deleted = conn.execute(
        text("DELETE FROM messages WHERE trim(content) = '' OR content IS NULL")
    ).rowcount
    print("deleted", deleted)
