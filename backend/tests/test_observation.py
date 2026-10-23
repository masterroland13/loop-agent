"""F4 observation slimming — formatters + loop integration."""

from __future__ import annotations

import json

import pytest

from agent_window.agent.observation import (
    GATE_STDIO_PREVIEW,
    GREP_MATCHES_MAX,
    LIST_DIR_ENTRIES_MAX,
    READ_FILE_CONTENT_MAX,
    SLIM_TOOL_RESULT_MAX_CHARS,
    ObservationResult,
    observe_tool_result,
    slim_tool_result,
    truncate_head_tail,
)


def _loads(s: str) -> dict:
    return json.loads(s)


def test_error_result_structured_with_hint() -> None:
    raw = json.dumps({"error": "not found: foo", "code": "NOT_FOUND"})
    slim = _loads(slim_tool_result("read_file", raw))
    assert slim["status"] == "failed"
    assert "not found" in slim["error"]
    assert slim["code"] == "NOT_FOUND"
    assert "hint" in slim
    assert "path" in slim["hint"] or "workspace" in slim["hint"]


def test_read_file_truncates_content_not_path() -> None:
    content = "\n".join(f"{i}|line {i}" for i in range(1, 501))
    raw = json.dumps(
        {
            "path": "src/main.py",
            "offset": 1,
            "limit": 500,
            "total_lines": 500,
            "truncated": False,
            "content": content,
        }
    )
    slim = _loads(slim_tool_result("read_file", raw))
    assert slim["status"] == "ok"
    assert slim["path"] == "src/main.py"
    assert len(slim["content"]) < len(content)
    assert slim["truncated"] is True
    assert "hint" in slim
    assert "offset" not in slim or slim["offset"] == 1
    # Head+tail: start and end of content survive.
    assert slim["content"].startswith("1|line 1")
    assert "500|line 500" in slim["content"]
    assert "省略" in slim["content"]
    assert slim.get("content_chars") == len(content)


def test_grep_limits_matches() -> None:
    matches = [{"path": f"a/{i}.py", "line": i, "text": f"hit {i}"} for i in range(40)]
    raw = json.dumps(
        {
            "pattern": "hit",
            "path": ".",
            "match_count": 40,
            "truncated": True,
            "matches": matches,
        }
    )
    slim = _loads(slim_tool_result("grep", raw))
    assert len(slim["matches"]) <= GREP_MATCHES_MAX
    assert slim["match_count"] == 40
    assert slim["truncated"] is True
    # Head + tail of match list.
    assert slim["matches"][0]["line"] == 0
    assert slim["matches"][-1]["line"] == 39
    assert slim.get("matches_omitted", 0) > 0
    assert "省略" in slim["hint"]


def test_list_dir_limits_entries() -> None:
    entries = [{"name": f"f{i}.py", "path": f"src/f{i}.py", "type": "file"} for i in range(80)]
    raw = json.dumps({"path": "src", "entries": entries, "truncated": False})
    slim = _loads(slim_tool_result("list_dir", raw))
    assert len(slim["entries"]) <= LIST_DIR_ENTRIES_MAX
    assert slim["entry_count"] == 80
    assert slim["truncated"] is True
    assert slim["entries"][0]["name"] == "f0.py"
    assert slim["entries"][-1]["name"] == "f79.py"
    assert slim.get("entries_omitted", 0) > 0
    assert "省略" in slim["hint"]


def test_gate_shell_strips_full_stdio() -> None:
    stdout = "HEADSTART" + ("x" * 4000) + "TAILEND!!"
    raw = json.dumps(
        {
            "status": "done",
            "shell_id": "s1",
            "command": "pytest -q",
            "exit_code": 0,
            "stdout": stdout,
            "stderr": "",
        }
    )
    slim = _loads(slim_tool_result("propose_shell", raw))
    assert slim["status"] == "done"
    assert "stdout" not in slim
    assert "stdout_preview" in slim
    assert len(slim["stdout_preview"]) <= GATE_STDIO_PREVIEW
    assert slim.get("stdout_truncated") is True
    assert slim["stdout_chars"] == len(stdout)
    assert slim["stdout_preview"].startswith("HEADSTART")
    assert slim["stdout_preview"].endswith("TAILEND!!")
    assert "省略" in slim["stdout_preview"]


def test_truncate_head_tail_keeps_ends_and_count() -> None:
    text = "AAAA" + ("m" * 200) + "ZZZZ"
    out, truncated = truncate_head_tail(text, 40)
    assert truncated is True
    assert len(out) <= 40
    assert out.startswith("AAAA")
    assert out.endswith("ZZZZ")
    assert "省略" in out
    # Marker reports omitted middle chars.
    assert "196" in out or "省略" in out
    short, no_cut = truncate_head_tail("hi", 40)
    assert no_cut is False
    assert short == "hi"


def test_read_file_head_tail_within_budget() -> None:
    head = "BEGIN_MARKER\n"
    tail = "\nEND_MARKER"
    content = head + ("body\n" * 2000) + tail
    raw = json.dumps(
        {
            "path": "huge.py",
            "offset": 1,
            "limit": 2000,
            "total_lines": 2002,
            "content": content,
        }
    )
    slim = _loads(slim_tool_result("read_file", raw))
    assert len(slim["content"]) <= READ_FILE_CONTENT_MAX
    assert slim["content"].startswith("BEGIN_MARKER")
    assert "END_MARKER" in slim["content"]
    assert "省略" in slim["content"]
    assert "头尾保留" in slim["hint"]


def test_gate_preserves_continue_hint() -> None:
    raw = json.dumps(
        {
            "status": "timeout",
            "patch_id": "p1",
            "path": "a.py",
            "continue_hint": "请立刻换手段重试一次",
            "loop_continue": True,
        }
    )
    slim = _loads(slim_tool_result("propose_edit", raw))
    assert slim["continue_hint"] == "请立刻换手段重试一次"
    assert slim["loop_continue"] is True


def test_slim_shorter_than_full_for_large_read() -> None:
    raw = json.dumps({"path": "big.txt", "content": "y" * 8000, "offset": 1, "limit": 200})
    slim_text = slim_tool_result("read_file", raw)
    assert len(slim_text) < len(raw)
    assert len(slim_text) <= SLIM_TOOL_RESULT_MAX_CHARS


def test_slim_respects_global_cap() -> None:
    raw = json.dumps({"note": "z" * 10000, "ok": True})
    slim_text = slim_tool_result("ping", raw)
    assert len(slim_text) <= SLIM_TOOL_RESULT_MAX_CHARS


def test_non_json_fallback_truncates() -> None:
    raw = "plain text " * 800
    slim = slim_tool_result("unknown", raw)
    assert len(slim) <= SLIM_TOOL_RESULT_MAX_CHARS
    assert "plain text" in slim


def test_observe_tool_result_contract_fields() -> None:
    content = "line\n" * 900
    raw = json.dumps({"path": "big.txt", "content": content, "offset": 1, "limit": 900})
    obs = observe_tool_result("read_file", raw)

    assert isinstance(obs, ObservationResult)
    assert obs.truncated is True
    assert obs.total_chars == len(raw)
    assert obs.display_summary == "read_file big.txt (truncated)"
    assert obs.full_ref == raw
    assert len(obs.model_payload) < len(raw)
    assert json.loads(obs.model_payload)["path"] == "big.txt"


def test_observe_no_full_ref_when_not_truncated() -> None:
    raw = json.dumps({"path": "tiny.txt", "content": "hello", "offset": 1, "limit": 10})
    obs = observe_tool_result("read_file", raw)
    assert obs.truncated is False
    assert obs.full_ref is None
    assert obs.display_summary == "read_file tiny.txt"


def test_slim_tool_result_matches_observe_model_payload() -> None:
    raw = json.dumps({"status": "done", "shell_id": "s1", "command": "echo hi", "exit_code": 0})
    assert slim_tool_result("propose_shell", raw) == observe_tool_result("propose_shell", raw).model_payload


def test_observe_spills_oversized_to_file_ref() -> None:
    from agent_window.agent.turn_event import INLINE_FULL_MAX, is_file_ref

    content = "HEAD" + ("m" * (INLINE_FULL_MAX + 100)) + "TAIL"
    raw = json.dumps({"path": "big.txt", "content": content, "offset": 1, "limit": 10})
    spills: list[str] = []

    def spill(text: str) -> str:
        spills.append(text)
        return "file:turns/asst/e1.txt"

    obs = observe_tool_result("read_file", raw, spill=spill)
    assert obs.truncated is True
    assert is_file_ref(obs.full_ref)
    assert obs.full_ref == "file:turns/asst/e1.txt"
    assert spills and spills[0] == raw
    payload = json.loads(obs.model_payload)
    assert payload["full_ref"] == "file:turns/asst/e1.txt"
    assert "完整输出已落盘" in payload["hint"]
    # Slim must not re-embed the full body.
    assert content not in obs.model_payload


def test_event_from_sse_reuses_preexisting_full_ref() -> None:
    from agent_window.agent.turn_event import event_from_sse

    spills: list[str] = []

    def spill(text: str) -> str:
        spills.append(text)
        return "file:should-not-be-called.txt"

    mapped = event_from_sse(
        {
            "type": "tool_result",
            "name": "read_file",
            "content": "Z" * 9000,
            "full_ref": "file:turns/a/e1.txt",
            "truncated": True,
            "summary": "read_file big (truncated)",
        },
        spill=spill,
    )
    assert mapped is not None
    assert mapped["full_ref"] == "file:turns/a/e1.txt"
    assert mapped["truncated"] is True
    assert spills == []
    assert "落盘" in mapped["summary"] or "read_file" in mapped["summary"]
