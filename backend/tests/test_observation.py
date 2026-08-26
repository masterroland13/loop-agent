"""F4 observation slimming — formatters + loop integration."""

from __future__ import annotations

import json

import pytest

from agent_window.agent.observation import (
    SLIM_TOOL_RESULT_MAX_CHARS,
    slim_tool_result,
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
    assert len(slim["matches"]) <= 25
    assert slim["match_count"] == 40
    assert slim["truncated"] is True


def test_list_dir_limits_entries() -> None:
    entries = [{"name": f"f{i}.py", "path": f"src/f{i}.py", "type": "file"} for i in range(80)]
    raw = json.dumps({"path": "src", "entries": entries, "truncated": False})
    slim = _loads(slim_tool_result("list_dir", raw))
    assert len(slim["entries"]) <= 50
    assert slim["entry_count"] == 80
    assert slim["truncated"] is True


def test_gate_shell_strips_full_stdio() -> None:
    stdout = "x" * 5000
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
    assert len(slim["stdout_preview"]) <= 501
    assert slim.get("stdout_truncated") is True
    assert slim["stdout_chars"] == 5000


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
