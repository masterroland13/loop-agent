"""M2/A4 compress: preserve Turn Goal; cut point; 6-section summary."""

from __future__ import annotations

import asyncio

from agent_window.agent.goal import GOAL_MARKER, inject_goal_into_messages
from agent_window.core.messages import COMPACTION_SUMMARY_MARKER
from agent_window.services.compress import (
    approx_messages_tokens,
    build_extractive_summary,
    compress_messages_if_needed,
    find_cut_index,
    find_previous_summary,
    messages_contain_goal,
)


def _long_history(*, n_pairs: int = 8) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "你是编码助手。"}]
    for i in range(n_pairs):
        msgs.append(
            {
                "role": "user",
                "content": f"第{i}轮：请详细解释一段很长的背景 " + ("背景" * 80),
            }
        )
        msgs.append(
            {
                "role": "assistant",
                "content": f"第{i}轮回复：" + ("内容" * 80),
            }
        )
    msgs.append(
        {
            "role": "user",
            "content": "backend 跑 pytest 报 ImportError: No module named 'agent_window'。请排查。",
        }
    )
    msgs.append({"role": "assistant", "content": "可能是 PYTHONPATH。建议设置 PYTHONPATH=src。"})
    msgs.append({"role": "user", "content": "好的，按你刚才的方向继续深挖，然后对照目标收工。"})
    return msgs


def _summary_msgs(out: list[dict]) -> list[dict]:
    return [
        m
        for m in out
        if isinstance(m.get("content"), str)
        and (
            COMPACTION_SUMMARY_MARKER in m["content"]
            or "压缩摘要" in m["content"]
        )
    ]


def test_compress_preserves_goal_in_system_block() -> None:
    goal = (
        "backend 跑 pytest 报 ImportError: No module named 'agent_window'。请排查。"
    )
    messages = _long_history()
    assert approx_messages_tokens(messages) > 200

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=None,
            preserve_goal=goal,
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed is True
    assert meta.method == "extractive"
    assert "（见原文）" not in meta.summary_preview
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
    assert "agent_window" in goal_blocks[0]["content"]


def test_compress_summary_header_pins_goal() -> None:
    goal = "修复 ImportError: No module named 'agent_window'"
    messages = _long_history()

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=goal,
        )

    out, compressed, _meta = asyncio.run(_run())
    assert compressed
    summary_msgs = _summary_msgs(out)
    assert summary_msgs
    assert summary_msgs[0]["role"] == "user"
    assert summary_msgs[0].get("entry_type") == "compaction_summary"
    assert summary_msgs[0]["role"] != "system"
    assert "本轮目标（压缩保留）" in summary_msgs[0]["content"]
    assert "ImportError" in summary_msgs[0]["content"]
    assert COMPACTION_SUMMARY_MARKER in summary_msgs[0]["content"]
    assert "（见原文）" not in summary_msgs[0]["content"]


def test_compress_without_goal_still_works() -> None:
    messages = _long_history()

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=None,
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed
    assert meta.method == "extractive"
    assert not any(
        isinstance(m.get("content"), str) and str(m["content"]).startswith(GOAL_MARKER)
        for m in out
    )
    assert _summary_msgs(out)
    assert "（见原文）" not in _summary_msgs(out)[0]["content"]


def test_compress_summarize_receives_goal_hint() -> None:
    goal = "排查 ImportError agent_window"
    messages = _long_history()
    seen: list[str] = []

    async def fake_summarize(blob: str) -> str:
        seen.append(blob)
        return (
            "## Goal\n排查 ImportError\n"
            "## Constraints\n无\n"
            "## Progress\n多次背景讨论\n"
            "## Key Decisions\n查 PYTHONPATH\n"
            "## Next Steps\n继续深挖\n"
            "## Critical Context\nagent_window 包路径"
        )

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=fake_summarize,
            preserve_goal=goal,
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed
    assert meta.method == "llm"
    assert seen
    assert "【必须保留的本轮目标】" in seen[0]
    assert "ImportError" in seen[0]
    assert "## Goal" in seen[0]
    assert "## Critical Context" in seen[0]
    assert messages_contain_goal(out, goal)
    summary = _summary_msgs(out)[0]
    assert "## Progress" in summary["content"]


def test_compress_noop_when_under_limit() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=10_000,
            preserve_goal="should not inject when not compressed",
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed is False
    assert meta.method == "none"
    assert out == messages


def test_compress_replaces_stale_goal_block() -> None:
    goal = "新目标：修好 pytest ImportError"
    messages = inject_goal_into_messages(_long_history(), "旧目标：别的事")

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal=goal,
        )

    out, compressed, _meta = asyncio.run(_run())
    assert compressed
    assert messages_contain_goal(out, goal)
    assert not messages_contain_goal(out, "旧目标：别的事")
    goal_blocks = [
        m
        for m in out
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and str(m["content"]).startswith(GOAL_MARKER)
    ]
    assert len(goal_blocks) == 1


def test_find_cut_index_snaps_to_user_assistant() -> None:
    rest = [
        {"role": "user", "content": "a" * 400},
        {"role": "assistant", "content": "b" * 400},
        {"role": "user", "content": "c" * 400},
        {"role": "assistant", "content": "d" * 400},
        {"role": "user", "content": "recent-user"},
        {"role": "assistant", "content": "recent-asst"},
    ]
    cut = find_cut_index(rest, keep_recent_tokens=50)
    assert 0 < cut < len(rest)
    assert rest[cut]["role"] in ("user", "assistant")
    assert rest[cut]["role"] != "system"
    # Recent tail kept
    assert any(m.get("content") == "recent-user" for m in rest[cut:])
    assert not any(m.get("content") == "recent-user" for m in rest[:cut])


def test_find_cut_index_all_fits_returns_zero() -> None:
    rest = [
        {"role": "user", "content": "short"},
        {"role": "assistant", "content": "ok"},
    ]
    assert find_cut_index(rest, keep_recent_tokens=10_000) == 0
    assert find_cut_index(rest, keep_recent_tokens=10_000) != 1


def test_compress_six_section_prompt_in_summarize() -> None:
    messages = _long_history()
    seen: list[str] = []

    async def fake_summarize(blob: str) -> str:
        seen.append(blob)
        return "## Goal\nx\n## Constraints\n\n## Progress\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=fake_summarize,
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed
    assert meta.method == "llm"
    assert seen
    for section in ("Goal", "Constraints", "Progress", "Key Decisions", "Next Steps", "Critical Context"):
        assert f"## {section}" in seen[0]
    summary = _summary_msgs(out)[0]
    assert summary["role"] == "user"
    assert summary.get("entry_type") == "compaction_summary"


def test_extractive_fallback_has_real_excerpts_not_placeholders() -> None:
    older = [
        {"role": "user", "content": "必须用 PYTHONPATH=src 跑 pytest，不要改仓库结构"},
        {"role": "assistant", "content": "先检查 backend/.venv 与 PYTHONPATH"},
        {"role": "tool", "name": "grep", "content": "found ImportError in backend/src/agent_window/agent/loop.py"},
        {"role": "user", "content": "继续深挖 ImportError agent_window"},
    ]
    text = build_extractive_summary(older, goal_text="修好 ImportError")
    assert "（见原文）" not in text
    assert "## Goal" in text
    assert "ImportError" in text or "PYTHONPATH" in text
    assert "grep" in text
    assert "loop.py" in text or "backend/src/agent_window/agent/loop.py" in text
    assert "Critical Context" in text
    constraints = text.split("## Constraints", 1)[1].split("##", 1)[0]
    assert "必须用 PYTHONPATH=src" in constraints or "不要改文件" in constraints
    assert "依次" not in constraints
    # Incomplete follow-up ask → keep a next-step pointer (not a full task paste)
    next_body = text.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "继续" in next_body or "等待用户下一指令" in next_body
    assert "list_dir" not in next_body


def test_extractive_hard_constraints_not_task_paste() -> None:
    from agent_window.services.compress import extract_hard_constraints

    users = [
        "请只读、不要改文件。依次做：1) list_dir 2) read_file README.md 3) grep compress",
        "继续只读：把 docs/architecture-charter.md 读一段",
    ]
    bits = extract_hard_constraints(users)
    assert "只读" in bits
    assert "不要改文件" in bits
    joined = " ".join(bits)
    assert "list_dir" not in joined
    assert "README" not in joined


def test_extractive_next_waiting_when_request_covered() -> None:
    older = [
        {
            "role": "user",
            "content": "只读读 README.md 和 docs/foundation-status.md，不要改文件",
        },
        {
            "role": "tool",
            "name": "read_file",
            "content": "README.md ok",
        },
        {
            "role": "tool",
            "name": "read_file",
            "content": "docs/foundation-status.md ok",
        },
        {
            "role": "assistant",
            "content": "只读任务已完成，未改任何文件。以下为短总结。",
        },
    ]
    text = build_extractive_summary(older, goal_text="只读探查")
    constraints = text.split("## Constraints", 1)[1].split("##", 1)[0]
    assert "只读" in constraints
    assert "不要改文件" in constraints
    assert "依次" not in constraints
    decisions = text.split("## Key Decisions", 1)[1].split("##", 1)[0]
    assert "短总结" not in decisions
    assert "（无）" in decisions
    next_body = text.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "等待用户下一指令" in next_body
    assert "继续完成用户未完成项" not in next_body
    progress = text.split("## Progress", 1)[1].split("##", 1)[0]
    assert "触及路径" in progress or "read_file" in progress
    assert "短总结" not in progress
    assert "尚未开始" not in progress
    assert "未见工具结果" not in progress


def test_extractive_next_skips_meta_followup() -> None:
    older = [
        {
            "role": "user",
            "content": "只读读 README.md，不要改文件，写 150 字短总结",
        },
        {"role": "tool", "name": "read_file", "content": "README.md ok"},
        {
            "role": "user",
            "content": "把本会话压缩摘要按六节原样贴出来（不要改写）。",
        },
    ]
    text = build_extractive_summary(older, goal_text="只读调查")
    next_body = text.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "原样贴出" not in next_body
    assert "六节" not in next_body
    # Skipped meta ask; task user was covered by read_file → waiting is correct
    assert "等待用户下一指令" in next_body


def test_extractive_progress_honest_when_no_tools_in_window() -> None:
    """Early cut: older is mostly the user ask — do not claim task never started / waiting."""
    older = [
        {
            "role": "user",
            "content": (
                "请只读、不要改文件。依次做：1) list_dir 仓库根 "
                "2) read_file README.md 3) grep compress（docs 与 backend）"
            ),
        },
    ]
    text = build_extractive_summary(older, goal_text="只读调查 compress")
    progress = text.split("## Progress", 1)[1].split("##", 1)[0]
    assert "未见工具结果" in progress
    assert "尚未开始" not in progress
    assert "尚无已执行" not in progress
    assert "README.md" in progress or "用户已点名" in progress
    next_body = text.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "等待用户下一指令" not in next_body
    assert "继续" in next_body


def test_coerce_replaces_false_idle_progress() -> None:
    from agent_window.services.compress import coerce_six_sections

    goal = "只读调查 compress，输出短总结"
    extractive = (
        f"## Goal\n{goal}\n"
        "## Constraints\n- 只读\n"
        "## Progress\n摘要窗口内未见工具结果（近端可能仍有未压入的工具轮）\n"
        "用户已点名路径：README.md；backend/\n"
        "## Key Decisions\n- （无）\n"
        "## Next Steps\n- 继续推进最近用户请求中尚未完成的部分（见 Goal）\n"
        "## Critical Context\n- README.md\n"
    )
    llm = (
        f"## Goal\n{goal}\n"
        "## Constraints\n- 只读\n"
        "## Progress\n（尚无已执行工具；任务仅收到指令，尚未开始）\n"
        "## Key Decisions\n- （无）\n"
        "## Next Steps\n- （无未完成项；等待用户下一指令）\n"
        "## Critical Context\n- README.md\n"
    )
    out = coerce_six_sections(llm, extractive=extractive)
    progress = out.split("## Progress", 1)[1].split("##", 1)[0]
    assert "尚未开始" not in progress
    assert "未见工具结果" in progress
    next_body = out.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "等待用户下一指令" not in next_body
    assert "继续" in next_body


def test_coerce_rejects_constraint_task_paste_and_decision_dump() -> None:
    from agent_window.services.compress import coerce_six_sections

    goal = "请只读、不要改文件。依次做：1) list_dir 2) read README.md"
    extractive = (
        f"## Goal\n{goal}\n"
        "## Constraints\n- 只读\n- 不要改文件\n"
        "## Progress\n触及路径：README.md\n"
        "## Key Decisions\n- （无）\n"
        "## Next Steps\n- （无未完成项；等待用户下一指令）\n"
        "## Critical Context\n- README.md\n"
    )
    llm = (
        f"## Goal\n{goal}\n"
        f"## Constraints\n{goal}\n继续只读：把 docs/architecture-charter.md 读一段\n"
        "## Progress\n助手：只读任务已完成。以下为短总结。" + ("内容" * 40) + "\n"
        "## Key Decisions\n- 只读任务已完成，未改任何文件。以下为短总结。压缩相关代码集中在 compress.py\n"
        f"## Next Steps\n继续完成用户未完成项：{goal}\n"
        f"## Critical Context\n{goal}\n"
    )
    out = coerce_six_sections(llm, extractive=extractive)
    constraints = out.split("## Constraints", 1)[1].split("##", 1)[0]
    assert "只读" in constraints
    assert "list_dir" not in constraints
    decisions = out.split("## Key Decisions", 1)[1].split("##", 1)[0]
    assert "短总结" not in decisions
    next_body = out.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "等待用户下一指令" in next_body
    progress = out.split("## Progress", 1)[1].split("##", 1)[0]
    assert "短总结" not in progress or "触及路径" in progress


def test_collect_touched_paths_dedupes_order() -> None:
    from agent_window.services.compress import collect_touched_paths

    msgs = [
        {"role": "user", "content": "读 README.md 和 docs/architecture-charter.md"},
        {
            "role": "tool",
            "name": "read_file",
            "content": "ok backend/src/agent_window/services/compress.py and README.md again",
        },
    ]
    paths = collect_touched_paths(msgs)
    assert "README.md" in paths
    assert any("architecture-charter.md" in p for p in paths)
    assert any("compress.py" in p for p in paths)
    assert paths.count("README.md") == 1


def test_extractive_critical_lists_paths() -> None:
    older = [
        {"role": "user", "content": "只读，读 README.md"},
        {
            "role": "tool",
            "name": "read_file",
            "content": "file=docs/foundation-status.md\n# status",
        },
        {
            "role": "tool",
            "name": "read_file",
            "content": "backend/src/agent_window/services/compress.py full",
        },
    ]
    text = build_extractive_summary(older, goal_text="只读探查压缩")
    crit = text.split("## Critical Context", 1)[1]
    assert "README.md" in crit
    assert "compress.py" in crit or "foundation-status.md" in crit
    assert "（无路径）" not in crit


def test_coerce_replaces_goal_echo_and_fills_paths() -> None:
    from agent_window.services.compress import coerce_six_sections

    goal = "只读探查：读 README.md、grep compress、总结触发条件"
    extractive = (
        f"## Goal\n{goal}\n"
        "## Constraints\n只读\n"
        "## Progress\n- read_file: README.md\n"
        "## Key Decisions\n- （无）\n"
        "## Next Steps\n- 继续完成用户未完成项：写总结\n"
        "## Critical Context\n- README.md\n- backend/src/agent_window/services/compress.py\n"
    )
    llm = (
        f"## Goal\n{goal}\n"
        f"## Constraints\n{goal}\n"
        f"## Progress\n{goal}\n"
        "## Key Decisions\n（无）\n"
        f"## Next Steps\n{goal}\n"
        f"## Critical Context\n{goal}\n"
    )
    out = coerce_six_sections(llm, extractive=extractive)
    assert "## Progress" in out
    progress = out.split("## Progress", 1)[1].split("##", 1)[0]
    assert goal not in progress.strip() or "read_file" in progress
    assert "README.md" in out
    assert "compress.py" in out
    next_body = out.split("## Next Steps", 1)[1].split("##", 1)[0]
    assert "继续完成用户未完成项" in next_body or "写总结" in next_body


def test_summary_message_includes_handoff_prefix() -> None:
    messages = _long_history()
    # Ensure tool-like path appears in older for extractive richness
    messages.insert(
        4,
        {
            "role": "tool",
            "name": "read_file",
            "content": "README.md contents...",
        },
    )

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            preserve_goal="排查 ImportError",
        )

    out, compressed, _meta = asyncio.run(_run())
    assert compressed
    body = _summary_msgs(out)[0]["content"]
    from agent_window.services.compress import COMPACTION_HANDOFF_PREFIX

    assert COMPACTION_HANDOFF_PREFIX in body
    assert "勿重复" in body
    assert COMPACTION_SUMMARY_MARKER in body


def test_six_section_prompt_is_handoff_oriented() -> None:
    messages = _long_history()
    seen: list[str] = []

    async def fake_summarize(blob: str) -> str:
        seen.append(blob)
        return (
            "## Goal\nx\n"
            "## Constraints\n\n"
            "## Progress\nread README.md\n"
            "## Key Decisions\n（无）\n"
            "## Next Steps\n写总结\n"
            "## Critical Context\n- README.md\n"
        )

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=fake_summarize,
        )

    _out, compressed, meta = asyncio.run(_run())
    assert compressed
    assert meta.method == "llm"
    assert seen
    assert "CONTEXT CHECKPOINT" in seen[0] or "交接" in seen[0]
    assert "禁止" in seen[0] or "勿" in seen[0]
    assert "路径" in seen[0]


def test_compress_includes_previous_summary_for_incremental_merge() -> None:
    messages = _long_history()
    prev = (
        f"{COMPACTION_SUMMARY_MARKER}\n"
        "## Goal\n旧目标保留\n"
        "## Constraints\n保留约束X\n"
        "## Progress\n早先进度\n"
        "## Key Decisions\n\n## Next Steps\n\n## Critical Context\n关键文件 foo.py"
    )
    # Inject a prior compaction into the middle so it lands in the older slice
    messages.insert(3, {"role": "user", "content": prev, "entry_type": "compaction_summary"})
    assert find_previous_summary(messages) is not None
    seen: list[str] = []

    async def fake_summarize(blob: str) -> str:
        seen.append(blob)
        return (
            "## Goal\n合并后目标\n"
            "## Constraints\n保留约束X\n"
            "## Progress\n更新\n"
            "## Key Decisions\n\n## Next Steps\n\n## Critical Context\nfoo.py"
        )

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=fake_summarize,
        )

    _out, compressed, meta = asyncio.run(_run())
    assert compressed
    assert meta.used_previous_summary is True
    assert seen
    assert "【上一轮压缩摘要，请增量合并勿丢失】" in seen[0]
    assert "关键文件 foo.py" in seen[0] or "foo.py" in seen[0]


def test_compress_rejects_placeholder_llm_output() -> None:
    messages = _long_history()

    async def junk_summarize(_blob: str) -> str:
        return (
            "## Goal\n（见原文）\n"
            "## Constraints\n（见原文）\n"
            "## Progress\n（见原文）\n"
            "## Key Decisions\n（见原文）\n"
            "## Next Steps\n（见原文）\n"
            "## Critical Context\n（见原文）"
        )

    async def _run():
        return await compress_messages_if_needed(
            messages,
            auto_compress=True,
            context_limit=200,
            summarize=junk_summarize,
            preserve_goal="排查 ImportError",
        )

    out, compressed, meta = asyncio.run(_run())
    assert compressed
    # coerce should replace junk with extractive
    body = _summary_msgs(out)[0]["content"]
    assert "（见原文）" not in body
    assert "ImportError" in body or "排查" in body
    assert meta.method == "llm"  # LLM ran; coerce repaired body
