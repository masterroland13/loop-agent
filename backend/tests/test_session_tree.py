"""A4: Session Tree — parent chain, path walk, regenerate = branch."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_window.core.session_tree import (
    build_path_from_session,
    walk_to_root,
)
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.storage import add_message, create_session


@pytest.fixture()
def tree_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(tmp_path))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(tmp_path))
    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    return tmp_path


def test_backfill_parent_chain_and_leaf(tree_db: Path) -> None:
    """New messages form a parent chain; leaf_id tracks tip."""
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="tree")
        assert session.leaf_id is None

        u1 = add_message(db, session, Role.USER, "hi", 1, parent_id=None)
        assert u1.parent_id is None
        assert session.leaf_id == u1.id

        a1 = add_message(db, session, Role.ASSISTANT, "hello", 2, parent_id=u1.id)
        assert a1.parent_id == u1.id
        assert session.leaf_id == a1.id
        assert session.leaf_id != u1.id

        u2 = add_message(db, session, Role.USER, "more", 3, parent_id=a1.id)
        a2 = add_message(db, session, Role.ASSISTANT, "ok", 4, parent_id=u2.id)

        path = build_path_from_session(session)
        assert [m.id for m in path] == [u1.id, a1.id, u2.id, a2.id]
        assert path[0].parent_id is None
        assert path[-1].id == session.leaf_id
        # Reverse: should not skip middle or include unknowns
        assert len(path) == 4
        assert path[1].role == Role.ASSISTANT
    finally:
        db.close()


def test_walk_to_root_order(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="walk")
        u = add_message(db, session, Role.USER, "u", 1)
        a = add_message(db, session, Role.ASSISTANT, "a", 2, parent_id=u.id)
        by_id = {u.id: u, a.id: a}
        path = walk_to_root(by_id, a.id)
        assert [m.id for m in path] == [u.id, a.id]
        assert [m.id for m in path] != [a.id, u.id]
    finally:
        db.close()


def test_regenerate_branch_leaves_old_assistant_off_path(tree_db: Path) -> None:
    """New assistant siblings under same user; leaf path excludes abandoned branch."""
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="branch")
        u = add_message(db, session, Role.USER, "question", 1)
        old_a = add_message(db, session, Role.ASSISTANT, "first answer", 2, parent_id=u.id)
        assert session.leaf_id == old_a.id

        # Branch regenerate: new sibling under same user
        new_a = add_message(db, session, Role.ASSISTANT, "second answer", 3, parent_id=u.id)
        assert new_a.parent_id == u.id
        assert old_a.parent_id == u.id
        assert session.leaf_id == new_a.id
        assert session.leaf_id != old_a.id

        # Both assistants still in DB
        db.refresh(session)
        all_ids = {m.id for m in session.messages}
        assert old_a.id in all_ids
        assert new_a.id in all_ids

        path = build_path_from_session(session)
        path_ids = [m.id for m in path]
        assert u.id in path_ids
        assert new_a.id in path_ids
        assert old_a.id not in path_ids
        assert path[-1].content == "second answer"
        assert "first answer" not in [m.content for m in path]
    finally:
        db.close()


def test_message_list_exposes_parent_id(tree_db: Path) -> None:
    from fastapi.testclient import TestClient

    from agent_window.main import app

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="api-tree")
        u = add_message(db, session, Role.USER, "hi", 1)
        a = add_message(db, session, Role.ASSISTANT, "yo", 2, parent_id=u.id)
        sid = session.id
        leaf_id = a.id
        user_id = u.id
    finally:
        db.close()

    client = TestClient(app)
    rows = client.get(f"/api/sessions/{sid}/messages").json()
    assert len(rows) == 2
    assert rows[0]["parent_id"] is None
    assert rows[1]["parent_id"] == rows[0]["id"]
    assert rows[0]["entry_type"] == "message"
    assert rows[1]["parent_id"] == user_id
    assert rows[1]["parent_id"] != rows[1]["id"]

    sessions = client.get("/api/sessions").json()
    match = next(s for s in sessions if s["id"] == sid)
    assert match["leaf_id"] == leaf_id
    assert match["leaf_id"] is not None


def test_messages_view_active_hides_abandoned_sibling(tree_db: Path) -> None:
    """view=active returns leaf path only — not the abandoned regenerate sibling."""
    from fastapi.testclient import TestClient

    from agent_window.main import app

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="active-view")
        u = add_message(db, session, Role.USER, "question", 1)
        old_a = add_message(db, session, Role.ASSISTANT, "first answer", 2, parent_id=u.id)
        new_a = add_message(db, session, Role.ASSISTANT, "second answer", 3, parent_id=u.id)
        sid = session.id
        old_id = old_a.id
        new_id = new_a.id
        user_id = u.id
    finally:
        db.close()

    client = TestClient(app)
    all_rows = client.get(f"/api/sessions/{sid}/messages").json()
    assert len(all_rows) == 3
    assert {r["id"] for r in all_rows} == {user_id, old_id, new_id}

    active = client.get(f"/api/sessions/{sid}/messages", params={"view": "active"}).json()
    active_ids = [r["id"] for r in active]
    assert active_ids == [user_id, new_id]
    assert old_id not in active_ids
    assert active[-1]["content"] == "second answer"
    assert active[-1]["content"] != "first answer"

    bad = client.get(f"/api/sessions/{sid}/messages", params={"view": "nope"})
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "INVALID_VIEW"