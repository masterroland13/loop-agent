"""C3: transform_context is the only compress entry (Goal pin + mid-loop)."""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

from agent_window.agent.goal import GOAL_MARKER
from agent_window.core.loop_config import LoopConfig
from agent_window.core.session_tree import build_path_from_session
from agent_window.models import Role, get_sessionmaker, init_db
from agent_window.services.compaction_persist import persist_compaction_on_tree
from agent_window.services.compress import messages_contain_goal
from agent_window.services.context_transform import (
    apply_transform_context,
    install_context_transform,
)
from agent_window.services.storage import add_message, create_session


def _long_history() -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "你是编码助手。"}]
    for i in range(8):
        msgs.append({"role": "user", "content": f"第{i}轮：" + ("背景" * 80)})
        msgs.append({"role": "assistant", "content": f"第{i}轮回复：" + ("内容" * 80)})
    msgs.append({"role": "user", "content": "请排查 ImportError agent_window"})
    return msgs


def test_goal_off_transform_does_not_inject_goal_block() -> None:
    cfg = install_context_transform(
        LoopConfig.default().with_goal_mode(False),
        auto_compress=True,
        context_limit=200,
    )
    goal = "不该出现的目标：修好 pytest"
    out, compressed, _meta = asyncio.run(
        apply_transform_context(cfg, _long_history(), preserve_goal=None)
    )
    assert compressed
    assert not messages_contain_goal(out, goal)
    assert not any(
        m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and str(m["content"]).startswith(GOAL_MARKER)
        for m in out
    )
    assert any(
        isinstance(m.get("content"), str) and "【对话压缩摘要】" in m["content"]
        for m in out
    )


def test_goal_on_transform_pins_goal_after_compress() -> None:
    goal = "backend 跑 pytest 报 ImportError: No module named 'agent_window'。请排查。"
    cfg = install_context_transform(
        LoopConfig.default().with_goal_mode(True),
        auto_compress=True,
        context_limit=200,
    )
    out, compressed, _meta = asyncio.run(
        apply_transform_context(cfg, _long_history(), preserve_goal=goal)
    )
    assert compressed
    assert messages_contain_goal(out, goal)
    goal_blocks = [
        m
        for m in out
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and str(m["content"]).startswith(GOAL_MARKER)
    ]
    assert len(goal_blocks) == 1
    assert "ImportError" in goal_blocks[0]["content"]
    assert not any(
        m.get("role") == "system" and "质量条" in str(m.get("content") or "")
        for m in out
    )


def test_loop_and_routes_do_not_copy_find_cut_index() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "agent_window"
    loop_src = (root / "agent" / "loop.py").read_text(encoding="utf-8")
    routes_src = (root / "api" / "routes.py").read_text(encoding="utf-8")
    assert "find_cut_index" not in loop_src
    assert "find_cut_index" not in routes_src
    assert "apply_transform_context" in loop_src
    assert "apply_transform_context" in routes_src
    # Manual compact (C5) may call compress; send/regenerate still go through transform.
    send_src = routes_src.split("async def compact_session_endpoint")[0]
    assert "compress_messages_if_needed" not in send_src
    compress_tree = ast.parse((root / "services" / "compress.py").read_text(encoding="utf-8"))
    defs = [n.name for n in ast.walk(compress_tree) if isinstance(n, ast.FunctionDef)]
    assert defs.count("find_cut_index") == 1


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


def test_mid_loop_second_transform_persists_on_tree(
    tree_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_window.agent import loop as loop_mod
    from agent_window.services.provider import provider

    db = get_sessionmaker()()
    try:
        session = create_session(db, title="c3")
        parent = None
        seq = 1
        for i in range(12):
            parent = add_message(
                db,
                session,
                Role.USER,
                f"tree ask {i} " + ("问" * 800),
                seq,
                parent_id=parent.id if parent else None,
            )
            seq += 1
            parent = add_message(
                db,
                session,
                Role.ASSISTANT,
                f"tree reply {i} " + ("答" * 800),
                seq,
                parent_id=parent.id,
            )
            seq += 1
        u2 = add_message(db, session, Role.USER, "second ask", seq, parent_id=parent.id)

        persisted: list = []

        def on_compressed(_out, meta) -> None:
            from agent_window.services.compaction_persist import persist_compaction_from_tree

            row = persist_compaction_on_tree(
                db,
                session,
                prior_path=build_path_from_session(session),
                new_user=None,
                meta=meta,
            )
            if row is None:
                row = persist_compaction_from_tree(db, session, meta)
            persisted.append(row)

        cfg = install_context_transform(
            LoopConfig.default(),
            auto_compress=True,
            context_limit=80,
            on_compressed=on_compressed,
        )

        chat_calls = 0

        async def fake_chat(messages, tools=None, model=None):
            nonlocal chat_calls
            chat_calls += 1
            if chat_calls == 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {"id": "tc1", "name": "list_dir", "arguments": '{"path":"."}'},
                    ],
                }
            return {"content": "收口。", "tool_calls": []}

        async def fake_tool(name: str, raw_args) -> str:
            return json.dumps({"entries": ["blob" * 200]}, ensure_ascii=False)

        monkeypatch.setattr(provider, "chat_complete", fake_chat)
        monkeypatch.setattr(loop_mod, "handle_function_call", fake_tool)
        monkeypatch.setattr(
            loop_mod,
            "load_agent_settings",
            lambda: {
                "disabled_tools": [],
                "max_tool_iters": 8,
                "checkpoint_every_n_tools": 4,
            },
        )

        class _Reg:
            def get_openai_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {"name": "list_dir", "parameters": {"type": "object"}},
                    }
                ]

        monkeypatch.setattr(loop_mod, "registry", _Reg())

        working = _long_history()

        async def _run() -> list[dict]:
            events: list[dict] = []
            async for ev in loop_mod.run_agent_loop(working, config=cfg):
                events.append(ev)
            return events

        events = asyncio.run(_run())
        assert chat_calls == 2
        assert len(persisted) >= 2
        assert persisted[-1] is not None
        db.refresh(session)
        path = build_path_from_session(session)
        assert any(getattr(m, "entry_type", "") == "compaction_summary" for m in path)
        assert any(ev.get("type") == "done" for ev in events)
        assert not any(ev.get("type") == "error" for ev in events)
        assert u2.id in {m.id for m in session.messages}
    finally:
        db.close()
