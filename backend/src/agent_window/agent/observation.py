"""F4 observation slimming — shrink tool results before feeding the model loop."""

from __future__ import annotations

import json
from typing import Any

# Global cap on serialized tool message to the model (chars).
SLIM_TOOL_RESULT_MAX_CHARS = 6000

READ_FILE_CONTENT_MAX = 3500
GREP_MATCHES_MAX = 25
LIST_DIR_ENTRIES_MAX = 50
GATE_STDIO_PREVIEW = 500

_GATE_TOOLS = frozenset({"propose_edit", "propose_delete", "propose_shell", "propose_memory"})

_ERROR_HINTS: dict[str, str] = {
    "NOT_FOUND": "检查路径是否相对 workspace 根目录且存在。",
    "NOT_A_FILE": "目标不是文件；list_dir 确认后再 read_file。",
    "NOT_A_DIR": "目标不是目录。",
    "INVALID_PATH": "path 不能为空且必须在 workspace 内。",
    "INVALID_PATTERN": "修正 grep 正则后重试。",
    "BINARY": "二进制文件不可读；换文本文件或工具。",
    "PERMISSION": "无权限访问；换路径或请用户协助。",
    "TOOL_ERROR": "查看 error 字段后换参数重试。",
}


def _try_parse(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _dump(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= SLIM_TOOL_RESULT_MAX_CHARS:
        return text
    return text[: SLIM_TOOL_RESULT_MAX_CHARS - 1] + "…"


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: limit - 1] + "…", True


def _failure_observation(error: str, *, code: str | None = None, hint: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "failed", "error": error}
    if code:
        out["code"] = code
    out["hint"] = hint or _ERROR_HINTS.get(code or "", "修正参数后重试。")
    return out


def _slim_error(parsed: dict[str, Any]) -> dict[str, Any]:
    code = str(parsed.get("code") or "")
    error = str(parsed.get("error") or "tool failed")
    return _failure_observation(error, code=code or None)


def _preview_stdio(value: Any, *, preview_key: str, source_key: str) -> dict[str, Any]:
    text = str(value or "")
    if not text:
        return {}
    preview, truncated = _truncate_text(text, GATE_STDIO_PREVIEW)
    out: dict[str, Any] = {preview_key: preview}
    if truncated:
        out[f"{source_key}_truncated"] = True
        out[f"{source_key}_chars"] = len(text)
    return out


def _is_gate_outcome(parsed: dict[str, Any], tool_name: str) -> bool:
    if tool_name in _GATE_TOOLS:
        return True
    if parsed.get("continue_hint") or parsed.get("loop_continue"):
        return True
    if parsed.get("patch_id") or parsed.get("shell_id") or parsed.get("memory_id"):
        return True
    status = parsed.get("status")
    return status in ("applied", "partial", "rejected", "done", "timeout", "failed", "cancelled")


def _slim_read_file(parsed: dict[str, Any]) -> dict[str, Any]:
    content = str(parsed.get("content") or "")
    slim_content, content_truncated = _truncate_text(content, READ_FILE_CONTENT_MAX)
    out: dict[str, Any] = {
        "status": "ok",
        "path": parsed.get("path"),
        "offset": parsed.get("offset"),
        "limit": parsed.get("limit"),
        "total_lines": parsed.get("total_lines"),
        "truncated": bool(parsed.get("truncated")) or content_truncated,
        "content": slim_content,
    }
    if content_truncated or parsed.get("truncated"):
        next_offset = (parsed.get("offset") or 1) + (parsed.get("limit") or 200)
        out["hint"] = f"内容已截断；继续 read_file offset={next_offset}。"
    return out


def _slim_list_dir(parsed: dict[str, Any]) -> dict[str, Any]:
    entries = parsed.get("entries") or []
    slim_entries: list[dict[str, Any]] = []
    if isinstance(entries, list):
        for item in entries[:LIST_DIR_ENTRIES_MAX]:
            if not isinstance(item, dict):
                continue
            slim_entries.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                }
            )
    truncated = bool(parsed.get("truncated")) or len(entries) > LIST_DIR_ENTRIES_MAX
    out: dict[str, Any] = {
        "status": "ok",
        "path": parsed.get("path"),
        "entry_count": len(entries) if isinstance(entries, list) else 0,
        "entries": slim_entries,
        "truncated": truncated,
    }
    if truncated:
        out["hint"] = "目录项过多已截断；缩小 path 或 list_dir 子目录。"
    return out


def _slim_grep(parsed: dict[str, Any]) -> dict[str, Any]:
    matches = parsed.get("matches") or []
    slim_matches: list[dict[str, Any]] = []
    if isinstance(matches, list):
        for item in matches[:GREP_MATCHES_MAX]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "")
            line_text, line_truncated = _truncate_text(text, 160)
            slim_matches.append(
                {
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "text": line_text,
                    **({"text_truncated": True} if line_truncated else {}),
                }
            )
    truncated = bool(parsed.get("truncated")) or (
        isinstance(matches, list) and len(matches) > GREP_MATCHES_MAX
    )
    out: dict[str, Any] = {
        "status": "ok",
        "pattern": parsed.get("pattern"),
        "path": parsed.get("path"),
        "glob": parsed.get("glob"),
        "files_scanned": parsed.get("files_scanned"),
        "match_count": parsed.get("match_count", len(matches) if isinstance(matches, list) else 0),
        "matches": slim_matches,
        "truncated": truncated,
    }
    if truncated:
        out["hint"] = "匹配过多已截断；缩小 path/glob 或更精确 pattern。"
    return out


def _slim_gate(parsed: dict[str, Any]) -> dict[str, Any]:
    status = str(parsed.get("status") or "unknown")
    out: dict[str, Any] = {"status": status}

    for key in (
        "path",
        "patch_id",
        "shell_id",
        "memory_id",
        "command",
        "exit_code",
        "error",
        "message",
        "continue_hint",
        "loop_continue",
        "applied_hunks",
        "truncated",
        "mode",
    ):
        if key in parsed and parsed[key] is not None:
            out[key] = parsed[key]

    out.update(_preview_stdio(parsed.get("stdout"), preview_key="stdout_preview", source_key="stdout"))
    out.update(_preview_stdio(parsed.get("stderr"), preview_key="stderr_preview", source_key="stderr"))

    if status in ("failed", "timeout", "rejected", "cancelled") and "hint" not in out:
        if parsed.get("continue_hint"):
            out["hint"] = parsed["continue_hint"]
        elif parsed.get("message"):
            out["hint"] = parsed["message"]
        elif parsed.get("error"):
            out["hint"] = parsed["error"]

    # Never pass huge diff bodies back into the loop.
    if "unified_diff" in parsed:
        diff = str(parsed["unified_diff"])
        preview, truncated = _truncate_text(diff, 200)
        out["diff_preview"] = preview
        if truncated:
            out["diff_truncated"] = True

    return out


def _slim_generic(parsed: dict[str, Any]) -> dict[str, Any]:
    """Fallback: keep structure, trim long strings."""
    out: dict[str, Any] = {}
    for key, value in parsed.items():
        if isinstance(value, str):
            out[key], _ = _truncate_text(value, 800)
        elif isinstance(value, list) and len(value) > 20:
            out[key] = value[:20]
            out[f"{key}_truncated"] = True
        else:
            out[key] = value
    return out


def slim_tool_result(tool_name: str, raw_result: str) -> str:
    """
    Return a compact JSON string for loop `working[]`.
    Full raw_result is still emitted on SSE / F6 trace.
    """
    parsed = _try_parse(raw_result or "")
    if not parsed:
        text, _ = _truncate_text(raw_result or "", SLIM_TOOL_RESULT_MAX_CHARS)
        return text

    if _is_gate_outcome(parsed, tool_name):
        return _dump(_slim_gate(parsed))

    if parsed.get("error"):
        return _dump(_slim_error(parsed))

    if tool_name == "read_file":
        return _dump(_slim_read_file(parsed))
    if tool_name == "list_dir":
        return _dump(_slim_list_dir(parsed))
    if tool_name == "grep":
        return _dump(_slim_grep(parsed))

    return _dump(_slim_generic(parsed))

