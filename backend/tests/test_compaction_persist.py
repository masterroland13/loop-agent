"""C1: compaction summary on the session tree; folded rows stay in DB/JSONL."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_window.core.messages import COMPACTION_SUMMARY_MARKER
from agent_window.core.session_tree import (
    build_llm_messages,
    build_path_from_session,
    persistable_path_messages,
)
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.compaction_persist import (
    persist_compaction_from_tree,
    persist_compaction_on_tree,
)
from agent_window.services.compress import CompressMeta
from agent_window.services.session_transcript import read_transcript_events
from agent_window.services.storage import add_message, create_session


TOOL_ORIGINAL = "grep src/foo.py TOOL_ORIGINAL_TOKEN"


@pytest.fixture()
def tree_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("agent_window.models.settings.app_data_dir", str(tmp_path))
    monkeypatch.setattr("agent_window.services.storage.settings.app_data_dir", str(tmp_path))
    monkeypatch.setattr(
        "agent_window.services.session_transcript.settings.app_data_dir",
        str(tmp_path),
    )
    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    return tmp_path


def _seed_linear(db):
    session = create_session(db, title="c1")
    u1 = add_message(db, session, Role.USER, "first ask", 1)
    a1 = add_message(db, session, Role.ASSISTANT, TOOL_ORIGINAL, 2, parent_id=u1.id)
    u2 = add_message(db, session, Role.USER, "keep this user", 3, parent_id=a1.id)
    a2 = add_message(db, session, Role.ASSISTANT, "recent reply", 4, parent_id=u2.id)
    u3 = add_message(db, session, Role.USER, "current ask", 5, parent_id=a2.id)
    a3 = add_message(db, session, Role.ASSISTANT, "current reply", 6, parent_id=u3.id)
    return session, u1, a1, u2, a2, u3, a3


def _summary_meta(
    *,
    cut_index: int,
    rest_count: int,
    method: str = "extractive",
    keep_folded_user_tokens: int = 8192,
) -> CompressMeta:
    return CompressMeta(
        method=method,
        cut_index=cut_index,
        rest_count=rest_count,
        summary_content=f"{COMPACTION_SUMMARY_MARKER}\nGoal: keep going\nProgress: older tool output folded",
        keep_folded_user_tokens=keep_folded_user_tokens,
    )


def test_persistable_path_skips_empty_assistant(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="empty")
        u = add_message(db, session, Role.USER, "q", 1)
        empty = add_message(db, session, Role.ASSISTANT, "", 2, parent_id=u.id)
        path = build_path_from_session(session)
        kept = persistable_path_messages(path)
        assert [m.id for m in kept] == [u.id]
        assert empty.id not in [m.id for m in kept]
    finally:
        db.close()


def test_persist_writes_summary_and_drops_folded_from_path(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session, u1, a1, u2, a2, u3, a3 = _seed_linear(db)
        prior = [u1, a1, u2, a2]
        summary = persist_compaction_on_tree(
            db,
            session,
            prior_path=prior,
            new_user=u3,
            meta=_summary_meta(cut_index=2, rest_count=5),
        )
        assert summary is not None
        assert summary.entry_type == "compaction_summary"
        assert session.leaf_id == a3.id
        assert session.leaf_id != summary.id

        db.refresh(session)
        path = build_path_from_session(session)
        path_ids = [m.id for m in path]
        path_text = "\n".join(m.content or "" for m in path)
        assert summary.id in path_ids
        assert u1.id in path_ids
        assert u2.id in path_ids
        assert a2.id in path_ids
        assert u3.id in path_ids
        assert a3.id in path_ids
        assert a1.id not in path_ids
        assert TOOL_ORIGINAL not in path_text
        assert COMPACTION_SUMMARY_MARKER in path_text
        assert "first ask" in path_text
        assert "keep this user" in path_text
        assert "current ask" in path_text

        llm = build_llm_messages(path)
        llm_blob = "\n".join(str(m.get("content") or "") for m in llm)
        assert COMPACTION_SUMMARY_MARKER in llm_blob
        assert TOOL_ORIGINAL not in llm_blob
        assert not any(m.get("role") == "compaction_summary" for m in llm)

        all_ids = {m.id for m in session.messages}
        assert u1.id in all_ids
        assert a1.id in all_ids
        assert summary.id in all_ids
        folded = [m for m in session.messages if m.id in {u1.id, a1.id}]
        assert folded
        assert all(m.entry_type != "compaction_summary" for m in folded)

        events = read_transcript_events(session)
        blob = "\n".join(str(item.get("content") or "") for item in events)
        assert TOOL_ORIGINAL in blob
        assert any(item.get("entry_type") == "compaction_summary" for item in events)
    finally:
        db.close()


def test_regenerate_after_persist_keeps_summary_and_leaf(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session, u1, a1, u2, a2, u3, a3 = _seed_linear(db)
        persist_compaction_on_tree(
            db,
            session,
            prior_path=[u1, a1, u2, a2],
            new_user=u3,
            meta=_summary_meta(cut_index=2, rest_count=5),
        )
        new_a = add_message(
            db,
            session,
            Role.ASSISTANT,
            "second answer",
            8,
            parent_id=u3.id,
        )
        assert session.leaf_id == new_a.id
        db.refresh(session)
        path = build_path_from_session(session)
        path_ids = [m.id for m in path]
        assert new_a.id in path_ids
        assert a3.id not in path_ids
        assert u1.id in path_ids
        assert a1.id not in path_ids
        assert any(getattr(m, "entry_type", "") == "compaction_summary" for m in path)
        assert path[-1].content == "second answer"
        assert "first ask" in [m.content for m in path]
        assert TOOL_ORIGINAL not in [m.content for m in path]
        assert {u1.id, a1.id, a3.id}.issubset({m.id for m in session.messages})
    finally:
        db.close()


def test_no_fake_summary_when_compress_off_or_failed(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session, u1, a1, u2, a2, u3, a3 = _seed_linear(db)
        prior = [u1, a1, u2, a2]
        assert (
            persist_compaction_on_tree(
                db,
                session,
                prior_path=prior,
                new_user=u3,
                meta=CompressMeta(),
            )
            is None
        )
        assert (
            persist_compaction_on_tree(
                db,
                session,
                prior_path=prior,
                new_user=u3,
                meta=CompressMeta(method="tail_trim", older_count=2, rest_count=5),
            )
            is None
        )
        assert (
            persist_compaction_on_tree(
                db,
                session,
                prior_path=prior,
                new_user=u3,
                meta=CompressMeta(
                    method="extractive",
                    cut_index=0,
                    rest_count=5,
                    summary_content=f"{COMPACTION_SUMMARY_MARKER}\nhalf",
                ),
            )
            is None
        )
        assert (
            persist_compaction_on_tree(
                db,
                session,
                prior_path=prior,
                new_user=u3,
                meta=CompressMeta(
                    method="extractive",
                    cut_index=2,
                    rest_count=99,
                    summary_content=f"{COMPACTION_SUMMARY_MARKER}\nhalf",
                ),
            )
            is None
        )
        db.refresh(session)
        types = [m.entry_type for m in session.messages]
        assert "compaction_summary" not in types
        path = build_path_from_session(session)
        assert [m.id for m in path] == [u1.id, a1.id, u2.id, a2.id, u3.id, a3.id]
    finally:
        db.close()


def test_relink_failure_rolls_back_summary_and_kept_parents(tree_db: Path, monkeypatch) -> None:
    from agent_window.services import compaction_persist as persist_mod
    from agent_window.services.storage import update_message_parent as real_update

    db = get_sessionmaker()()
    try:
        session, u1, a1, u2, a2, u3, a3 = _seed_linear(db)
        u2_parent = u2.parent_id
        u1_parent = u1.parent_id

        def flaky(db_sess, message_id, parent_id):
            if message_id == u2.id:
                return None
            return real_update(db_sess, message_id, parent_id)

        monkeypatch.setattr(persist_mod, "update_message_parent", flaky)
        row = persist_compaction_on_tree(
            db,
            session,
            prior_path=[u1, a1, u2, a2],
            new_user=u3,
            meta=_summary_meta(cut_index=2, rest_count=5),
        )
        assert row is None
        db.refresh(session)
        db.refresh(u1)
        db.refresh(u2)
        assert "compaction_summary" not in [m.entry_type for m in session.messages]
        assert u1.parent_id == u1_parent
        assert u2.parent_id == u2_parent
        path = build_path_from_session(session)
        assert [m.id for m in path] == [u1.id, a1.id, u2.id, a2.id, u3.id, a3.id]
        assert session.leaf_id == a3.id
        assert a1.id in {m.id for m in session.messages}
    finally:
        db.close()


def test_persist_uses_compress_token_budget_for_kept_users(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="c2-budget")
        far = add_message(db, session, Role.USER, "FAR_USER_ORIGINAL " + ("远" * 400), 1)
        a1 = add_message(db, session, Role.ASSISTANT, TOOL_ORIGINAL, 2, parent_id=far.id)
        near = add_message(db, session, Role.USER, "NEAR_USER_ORIGINAL 请修", 3, parent_id=a1.id)
        a2 = add_message(db, session, Role.ASSISTANT, "recent reply", 4, parent_id=near.id)
        tip = add_message(db, session, Role.USER, "current ask", 5, parent_id=a2.id)
        meta = _summary_meta(cut_index=3, rest_count=5, keep_folded_user_tokens=40)
        summary = persist_compaction_on_tree(
            db,
            session,
            prior_path=[far, a1, near, a2],
            new_user=tip,
            meta=meta,
        )
        assert summary is not None
        db.refresh(session)
        path = build_path_from_session(session)
        path_text = "\n".join(m.content or "" for m in path)
        assert "NEAR_USER_ORIGINAL" in path_text
        assert "FAR_USER_ORIGINAL" not in path_text
        assert far.id in {m.id for m in session.messages}
        assert far.id not in [m.id for m in path]
        assert near.id in [m.id for m in path]
    finally:
        db.close()


def test_persist_from_tree_ignores_working_rest_count(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session = create_session(db, title="c3-tree")
        parent = None
        seq = 1
        first_user = None
        for i in range(12):
            parent = add_message(
                db,
                session,
                Role.USER,
                f"ask {i} " + ("问" * 800),
                seq,
                parent_id=parent.id if parent else None,
            )
            if first_user is None:
                first_user = parent
            seq += 1
            parent = add_message(
                db,
                session,
                Role.ASSISTANT,
                f"reply {i} " + ("答" * 800),
                seq,
                parent_id=parent.id,
            )
            seq += 1
        # Working-list meta: rest_count does not match the tree.
        meta = _summary_meta(cut_index=4, rest_count=99)
        aligned = persist_compaction_on_tree(
            db,
            session,
            prior_path=build_path_from_session(session),
            new_user=None,
            meta=meta,
        )
        assert aligned is None
        row = persist_compaction_from_tree(db, session, meta)
        assert row is not None
        assert row.entry_type == "compaction_summary"
        db.refresh(session)
        path = build_path_from_session(session)
        assert row.id in [m.id for m in path]
        assert first_user is not None
        assert first_user.id in {m.id for m in session.messages}
        assert session.leaf_id != row.id
    finally:
        db.close()


def test_persist_from_tree_skips_short_path(tree_db: Path) -> None:
    db = get_sessionmaker()()
    try:
        session, u1, a1, u2, a2, u3, a3 = _seed_linear(db)
        row = persist_compaction_from_tree(db, session, _summary_meta(cut_index=2, rest_count=5))
        assert row is None
        db.refresh(session)
        assert "compaction_summary" not in [m.entry_type for m in session.messages]
        assert [m.id for m in build_path_from_session(session)] == [
            u1.id,
            a1.id,
            u2.id,
            a2.id,
            u3.id,
            a3.id,
        ]
    finally:
        db.close()
