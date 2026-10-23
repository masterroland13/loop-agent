"""S0a: turn activity reducer — Explored / Edited / Thought grouping."""

from __future__ import annotations

from agent_window.agent.turn_activity import (
    ActivityBuilder,
    build_turn_activity,
    classify_tool,
    count_diff_lines,
    group_activity_items,
)


def test_classify_tool_buckets():
    assert classify_tool("read_file") == "explore"
    assert classify_tool("grep") == "explore"
    assert classify_tool("list_dir") == "explore"
    assert classify_tool("propose_edit") == "edit"
    assert classify_tool("propose_delete") == "edit"
    assert classify_tool("propose_shell") == "run"
    assert classify_tool("propose_memory") == "note"
    assert classify_tool("propose_memory") != "edit"
    assert classify_tool("unknown_tool") is None


def test_count_diff_lines_ignores_headers():
    diff = (
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,2 +1,3 @@\n"
        " keep\n"
        "-old\n"
        "+new\n"
        "+extra\n"
    )
    add, delete = count_diff_lines(diff)
    assert add == 2
    assert delete == 1
    assert count_diff_lines("") == (0, 0)
    assert count_diff_lines(None) == (0, 0)


def test_consecutive_explores_merge_thought_breaks():
    events = [
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"a.py","offset":1,"limit":10}',
            "tool_call_id": "c1",
        },
        {"type": "tool_result", "name": "read_file", "status": "done", "tool_call_id": "c1"},
        {
            "type": "tool_start",
            "name": "grep",
            "arguments": '{"path":"tests","query":"foo"}',
            "tool_call_id": "c2",
        },
        {"type": "tool_result", "name": "grep", "status": "done", "tool_call_id": "c2"},
        {
            "type": "thought",
            "phase": "end",
            "text": "I should edit next",
            "duration_ms": 18000,
        },
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"b.py"}',
            "tool_call_id": "c3",
        },
        {"type": "tool_result", "name": "read_file", "status": "done", "tool_call_id": "c3"},
    ]
    snap = build_turn_activity(events)
    kinds = [s["kind"] for s in snap["segments"]]
    assert kinds == ["explored", "thought", "explored"]
    assert kinds != ["explored"]
    assert "Explored 1 file, 1 search" in snap["segments"][0]["summary"]
    assert snap["segments"][1]["summary"] == "Thought 18s"
    assert "I should edit next" in (snap["segments"][1]["items"][0].get("text") or "")
    assert snap["segments"][2]["summary"] == "Explored 1 file"
    assert snap["stats"]["has_thought"] is True


def test_short_thoughts_nest_into_explored_in_order():
    """Cursor-style: short thoughts nest under Explored in stream order; not dropped."""
    events = [
        {
            "type": "thought",
            "phase": "end",
            "text": "leading plan",
            "duration_ms": 800,
        },
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"a.py"}',
            "tool_call_id": "c1",
        },
        {"type": "tool_result", "name": "read_file", "status": "done", "tool_call_id": "c1"},
        {
            "type": "thought",
            "phase": "end",
            "text": "mid think",
            "duration_ms": 2000,
        },
        {
            "type": "tool_start",
            "name": "grep",
            "arguments": '{"path":".","query":"x"}',
            "tool_call_id": "c2",
        },
        {"type": "tool_result", "name": "grep", "status": "done", "tool_call_id": "c2"},
        {
            "type": "thought",
            "phase": "end",
            "text": "trailing",
            "duration_ms": 3000,
        },
    ]
    snap = build_turn_activity(events)
    assert [s["kind"] for s in snap["segments"]] == ["explored"]
    assert [s["kind"] for s in snap["segments"]] != ["thought", "explored", "thought", "explored", "thought"]
    items = snap["segments"][0]["items"]
    kinds = [i["kind"] for i in items]
    assert kinds == ["thought", "explore", "thought", "explore", "thought"]
    assert kinds != ["explore", "explore", "thought", "thought", "thought"]
    texts = [i.get("text") for i in items if i["kind"] == "thought"]
    assert texts == ["leading plan", "mid think", "trailing"]
    assert "Explored 1 file, 1 search" in snap["segments"][0]["summary"]
    assert snap["stats"]["has_thought"] is True


def test_short_thought_alone_stays_top_level():
    snap = build_turn_activity(
        [{"type": "thought", "phase": "end", "text": "solo", "duration_ms": 500}]
    )
    assert [s["kind"] for s in snap["segments"]] == ["thought"]
    assert snap["segments"][0]["items"][0]["text"] == "solo"


def test_short_thought_between_explore_and_edit_stays_in_order():
    events = [
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"a.py"}',
            "tool_call_id": "c1",
        },
        {"type": "tool_result", "name": "read_file", "status": "done", "tool_call_id": "c1"},
        {"type": "thought", "phase": "end", "text": "then edit", "duration_ms": 1500},
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "a.py",
            "status": "applied",
            "unified_diff": "--- a\n+++ b\n@@\n+x\n",
        },
    ]
    snap = build_turn_activity(events)
    kinds = [s["kind"] for s in snap["segments"]]
    assert kinds == ["explored", "edited"]
    assert snap["segments"][0]["items"][-1]["kind"] == "thought"
    assert snap["segments"][0]["items"][-1]["text"] == "then edit"
    assert all(i["kind"] != "thought" for i in snap["segments"][1]["items"])
    # Nested thought must not inflate edit counts
    assert snap["segments"][1]["applied_file_count"] == 1
    assert snap["stats"]["applied_file_count"] == 1
    assert snap["stats"]["applied_file_count"] != 0


def test_pending_edit_not_in_applied_stats():
    events = [
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "src/App.tsx",
            "status": "pending",
            "unified_diff": "--- a\n+++ b\n@@\n-old\n+new\n+line2\n",
        }
    ]
    snap = build_turn_activity(events)
    assert snap["stats"]["pending_file_count"] == 1
    assert snap["stats"]["applied_file_count"] == 0
    assert snap["stats"]["add_total"] == 0
    assert snap["stats"]["del_total"] == 0
    assert snap["stats"]["applied_file_count"] != 1
    seg = snap["segments"][0]
    assert seg["kind"] == "edited"
    assert "proposed" in seg["summary"].lower()
    assert "+2" not in seg["summary"]  # pending must not inflate title +/-


def test_applied_edit_counts_plus_minus():
    events = [
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "x.py",
            "status": "pending",
            "unified_diff": "--- a\n+++ b\n@@\n-old\n+new\n+extra\n",
        },
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "x.py",
            "status": "applied",
            "unified_diff": "--- a\n+++ b\n@@\n-old\n+new\n+extra\n",
        },
    ]
    snap = build_turn_activity(events)
    assert len(snap["items"]) == 1  # same patch_id updates in place
    assert snap["stats"]["applied_file_count"] == 1
    assert snap["stats"]["pending_file_count"] == 0
    assert snap["stats"]["add_total"] == 2
    assert snap["stats"]["del_total"] == 1
    assert "+2 −1" in snap["segments"][0]["summary"]
    assert "Edited 1 file" in snap["segments"][0]["summary"]


def test_propose_memory_is_note_not_edited():
    events = [
        {
            "type": "tool_result",
            "name": "propose_memory",
            "status": "applied",
            "summary": "added entry",
            "tool_call_id": "m1",
        }
    ]
    snap = build_turn_activity(events)
    assert snap["items"][0]["kind"] == "note"
    assert snap["items"][0]["kind"] != "edit"
    assert snap["segments"][0]["kind"] == "note"
    assert snap["stats"]["applied_file_count"] == 0


def test_memory_sse_event_is_note():
    snap = build_turn_activity(
        [{"type": "memory", "status": "pending", "target": "user"}]
    )
    assert snap["items"][0]["kind"] == "note"
    assert snap["items"][0]["note_type"] == "propose_memory"
    assert "Edited" not in snap["segments"][0]["summary"]


def test_edit_and_run_merge_into_edited_segment():
    events = [
        {
            "type": "diff",
            "patch_id": "p1",
            "path": "a.py",
            "status": "applied",
            "unified_diff": "--- a\n+++ b\n@@\n+x\n",
        },
        {
            "type": "shell",
            "shell_id": "s1",
            "command": "pytest -q",
            "status": "done",
            "exit_code": 0,
        },
    ]
    snap = build_turn_activity(events)
    assert len(snap["segments"]) == 1
    assert snap["segments"][0]["kind"] == "edited"
    assert "ran 1 command" in snap["segments"][0]["summary"]
    assert snap["segments"][0]["command_count"] == 1


def test_no_fake_thought_from_tools_only():
    events = [
        {
            "type": "tool_start",
            "name": "list_dir",
            "arguments": '{"path":"."}',
            "tool_call_id": "c1",
        },
        {"type": "tool_result", "name": "list_dir", "status": "done", "tool_call_id": "c1"},
    ]
    snap = build_turn_activity(events)
    assert snap["stats"]["has_thought"] is False
    assert all(s["kind"] != "thought" for s in snap["segments"])
    assert all(i["kind"] != "thought" for i in snap["items"])


def test_thought_streaming_delta_then_end():
    b = ActivityBuilder()
    b.apply({"type": "thought", "phase": "start"})
    b.apply({"type": "thought", "phase": "delta", "text": "Hello"})
    b.apply({"type": "thought", "phase": "delta", "text": " world"})
    b.apply({"type": "thought", "phase": "end", "duration_ms": 500})
    snap = b.snapshot()
    assert len(snap["items"]) == 1
    assert snap["items"][0]["text"] == "Hello world"
    assert snap["segments"][0]["summary"] == "Thought briefly"


def test_edit_nudge_is_note_not_thought():
    snap = build_turn_activity(
        [{"type": "edit_nudge", "reason": "missing_propose_edit"}]
    )
    assert snap["items"][0]["kind"] == "note"
    assert snap["items"][0]["kind"] != "thought"
    assert snap["items"][0]["note_type"] == "edit_nudge"


def test_merge_false_keeps_singleton_segments():
    events = [
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"a.py"}',
            "tool_call_id": "c1",
        },
        {
            "type": "tool_start",
            "name": "read_file",
            "arguments": '{"path":"b.py"}',
            "tool_call_id": "c2",
        },
    ]
    snap = build_turn_activity(events, merge=False)
    assert len(snap["segments"]) == 2
    assert all(s["kind"] == "explored" for s in snap["segments"])


def test_persisted_tool_field_and_full_ref_args():
    """TurnEvent persistence uses tool= and full_ref for args."""
    events = [
        {
            "type": "tool_start",
            "tool": "read_file",
            "full_ref": '{"path":"src/utils/turnTrace.ts","offset":1,"limit":50}',
            "tool_call_id": "t1",
        },
        {"type": "tool_result", "tool": "read_file", "status": "done", "tool_call_id": "t1"},
    ]
    snap = build_turn_activity(events)
    item = snap["items"][0]
    assert item["path"] == "src/utils/turnTrace.ts"
    assert item["lines"] == "L1–50"
    assert "Read turnTrace.ts" in item["summary"]


def test_edit_from_tool_result_without_diff_sse():
    """Refresh/hydrate path: propose_edit tool_result carries patch_id."""
    snap = build_turn_activity(
        [
            {
                "type": "tool_result",
                "name": "propose_edit",
                "status": "done",
                "content": '{"status":"applied","patch_id":"p9","path":"a.py"}',
            }
        ]
    )
    assert snap["items"][0]["kind"] == "edit"
    assert snap["items"][0]["status"] == "applied"
    assert snap["stats"]["applied_file_count"] == 1
    assert snap["stats"]["add_total"] == 0  # no unified_diff on hydrate


def test_hydrate_legacy_gate_diff_becomes_edited():
    """F6 historically persisted diff SSE as type=gate; reload must still show Edited."""
    import json

    body = {
        "type": "diff",
        "patch_id": "p-gate",
        "path": "dogfood_cot_probe.txt",
        "unified_diff": "--- /dev/null\n+++ b/dogfood_cot_probe.txt\n@@\n+DOGFOOD_OK\n",
        "status": "applied",
        "is_new_file": True,
    }
    snap = build_turn_activity(
        [
            {
                "type": "gate",
                "tool": "propose_edit",
                "status": "applied",
                "summary": "propose_edit · applied · dogfood_cot_probe.txt",
                "full_ref": json.dumps(body, ensure_ascii=False),
            }
        ]
    )
    assert snap["stats"]["applied_file_count"] == 1
    assert snap["stats"]["applied_file_count"] != 0
    kinds = [s["kind"] for s in snap["segments"]]
    assert "edited" in kinds
    assert "edited" in kinds and kinds != ["thought"]


def test_hydrate_legacy_gate_shell_becomes_ran():
    import json

    body = {
        "type": "shell",
        "shell_id": "s1",
        "command": "echo DOGFOOD_SHELL",
        "status": "done",
        "exit_code": 0,
    }
    snap = build_turn_activity(
        [
            {
                "type": "gate",
                "tool": "propose_shell",
                "status": "done",
                "summary": "propose_shell · done · echo DOGFOOD_SHELL",
                "full_ref": json.dumps(body, ensure_ascii=False),
            }
        ]
    )
    runs = [i for i in snap["items"] if i["kind"] == "run"]
    assert len(runs) == 1
    assert runs[0]["status"] == "done"
    assert "DOGFOOD_SHELL" in runs[0]["summary"]
    assert runs[0]["kind"] != "explore"


def test_edit_from_tool_result_full_ref_not_content():
    """Persisted tool_result keeps JSON in full_ref; content is omitted."""
    import json

    payload = {"status": "applied", "patch_id": "p-fr", "path": "a.py"}
    snap = build_turn_activity(
        [
            {
                "type": "tool_result",
                "tool": "propose_edit",
                "status": "applied",
                "summary": "propose_edit · 大输出已落盘（999 字符）",
                "full_ref": json.dumps(payload, ensure_ascii=False),
            }
        ]
    )
    assert snap["items"][0]["kind"] == "edit"
    assert snap["items"][0]["status"] == "applied"
    assert snap["items"][0]["patch_id"] == "p-fr"
    assert snap["stats"]["applied_file_count"] == 1
    assert snap["stats"]["pending_file_count"] == 0


def test_run_from_tool_result_full_ref():
    import json

    payload = {
        "status": "done",
        "shell_id": "sh-9",
        "command": "echo DOGFOOD_SHELL",
        "exit_code": 0,
    }
    snap = build_turn_activity(
        [
            {
                "type": "tool_result",
                "tool": "propose_shell",
                "status": "done",
                "summary": "ok",
                "full_ref": json.dumps(payload, ensure_ascii=False),
            }
        ]
    )
    assert snap["items"][0]["kind"] == "run"
    assert snap["items"][0]["shell_id"] == "sh-9"
    assert "Ran" in snap["items"][0]["summary"] or "echo" in snap["items"][0]["summary"]


def test_memory_duplicate_tool_result_readable_note():
    import json

    snap = build_turn_activity(
        [
            {
                "type": "tool_result",
                "name": "propose_memory",
                "status": "failed",
                "full_ref": json.dumps(
                    {
                        "error": "duplicate entry: identical content already present",
                        "code": "DUPLICATE",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )
    assert snap["items"][0]["kind"] == "note"
    assert "duplicate" in snap["items"][0]["summary"].lower()
    assert "{" not in snap["items"][0]["summary"]
    assert snap["items"][0]["summary"] != '{"error": "duplicate entry: identical content already present", "code": "DUPLICATE"}'
