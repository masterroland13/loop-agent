"""F4 observation slimming — shrink tool results before feeding the model loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent_window.agent.turn_event import INLINE_FULL_MAX, SpillFn, is_file_ref, store_full_ref

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


@dataclass(frozen=True)
class ObservationResult:
    """F4 contract — slim payload for the model plus trace metadata.

    ``model_payload`` goes into loop ``working[]``. SSE still emits the raw tool
    body; ``full_ref`` holds inline full text when truncated payloads are small
    enough (file spill wired in a later step).
    """

    model_payload: str
    display_summary: str
    full_ref: str | None = None
    truncated: bool = False
    total_chars: int | None = None


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
    slim, _ = truncate_head_tail(text, SLIM_TOOL_RESULT_MAX_CHARS)
    return slim


def truncate_head_tail(text: str, limit: int, *, head_ratio: float = 0.7) -> tuple[str, bool]:
    """Keep head + tail with an honest omitted-count marker (F4 Step 2).

    Returns ``(maybe_truncated_text, was_truncated)``. Total length ≤ ``limit``.
    """
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False

    # Placeholder length for omitted digits; refine after choosing head/tail sizes.
    # Worst-case marker: …[省略 {len(text)} 字]…
    rough_marker = f"…[省略 {len(text)} 字]…"
    budget = limit - len(rough_marker)
    if budget < 2:
        # Tiny limit: fall back to head-only with ellipsis.
        if limit == 1:
            return "…", True
        return text[: limit - 1] + "…", True

    head_len = max(1, int(budget * head_ratio))
    tail_len = max(1, budget - head_len)
    if head_len + tail_len >= len(text):
        return text, False

    omitted = len(text) - head_len - tail_len
    marker = f"…[省略 {omitted} 字]…"
    # Rebalance if marker shorter/longer than rough estimate shifted budget.
    used = head_len + tail_len + len(marker)
    if used > limit:
        overflow = used - limit
        # Prefer shaving head first, then tail.
        take_head = min(overflow, max(0, head_len - 1))
        head_len -= take_head
        overflow -= take_head
        if overflow > 0:
            tail_len = max(1, tail_len - overflow)
        omitted = len(text) - head_len - tail_len
        marker = f"…[省略 {omitted} 字]…"

    return text[:head_len] + marker + text[-tail_len:], True


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    """Back-compat alias — head/tail truncate (F4 Step 2)."""
    return truncate_head_tail(text, limit)


def _truncate_list(items: list[Any], max_keep: int) -> tuple[list[Any], int]:
    """Keep head + tail of a list; return (kept, omitted_count)."""
    if max_keep <= 0:
        return [], len(items)
    if len(items) <= max_keep:
        return list(items), 0
    head = max(1, (max_keep * 2) // 3)
    tail = max(1, max_keep - head)
    if head + tail >= len(items):
        return list(items), 0
    omitted = len(items) - head - tail
    return list(items[:head]) + list(items[-tail:]), omitted


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
    preview, truncated = truncate_head_tail(text, GATE_STDIO_PREVIEW)
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
    slim_content, content_truncated = truncate_head_tail(content, READ_FILE_CONTENT_MAX)
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
        omitted = max(0, len(content) - len(slim_content.replace("…", "")))
        # Prefer count from marker when present.
        if "省略" in slim_content:
            out["hint"] = (
                f"内容已截断（头尾保留）；继续 read_file offset={next_offset}。"
            )
        else:
            out["hint"] = (
                f"内容已截断（约省略 {omitted} 字）；继续 read_file offset={next_offset}。"
            )
        if content_truncated:
            out["content_chars"] = len(content)
    return out


def _slim_list_dir(parsed: dict[str, Any]) -> dict[str, Any]:
    entries = parsed.get("entries") or []
    slim_entries: list[dict[str, Any]] = []
    omitted_entries = 0
    if isinstance(entries, list):
        kept, omitted_entries = _truncate_list(entries, LIST_DIR_ENTRIES_MAX)
        for item in kept:
            if not isinstance(item, dict):
                continue
            slim_entries.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                }
            )
    truncated = bool(parsed.get("truncated")) or omitted_entries > 0
    out: dict[str, Any] = {
        "status": "ok",
        "path": parsed.get("path"),
        "entry_count": len(entries) if isinstance(entries, list) else 0,
        "entries": slim_entries,
        "truncated": truncated,
    }
    if truncated:
        if omitted_entries > 0:
            out["hint"] = (
                f"目录项过多已截断（头尾保留，省略 {omitted_entries} 项）；"
                "缩小 path 或 list_dir 子目录。"
            )
            out["entries_omitted"] = omitted_entries
        else:
            out["hint"] = "目录项过多已截断；缩小 path 或 list_dir 子目录。"
    return out


def _slim_grep(parsed: dict[str, Any]) -> dict[str, Any]:
    matches = parsed.get("matches") or []
    slim_matches: list[dict[str, Any]] = []
    omitted_matches = 0
    if isinstance(matches, list):
        kept, omitted_matches = _truncate_list(matches, GREP_MATCHES_MAX)
        for item in kept:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "")
            line_text, line_truncated = truncate_head_tail(text, 160)
            slim_matches.append(
                {
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "text": line_text,
                    **({"text_truncated": True} if line_truncated else {}),
                }
            )
    truncated = bool(parsed.get("truncated")) or omitted_matches > 0
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
        if omitted_matches > 0:
            out["hint"] = (
                f"匹配过多已截断（头尾保留，省略 {omitted_matches} 条）；"
                "缩小 path/glob 或更精确 pattern。"
            )
            out["matches_omitted"] = omitted_matches
        else:
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
        preview, truncated = truncate_head_tail(diff, 200)
        out["diff_preview"] = preview
        if truncated:
            out["diff_truncated"] = True
            out["diff_chars"] = len(diff)

    return out


def _slim_generic(parsed: dict[str, Any]) -> dict[str, Any]:
    """Fallback: keep structure, trim long strings / lists with head+tail."""
    out: dict[str, Any] = {}
    for key, value in parsed.items():
        if isinstance(value, str):
            slim, truncated = truncate_head_tail(value, 800)
            out[key] = slim
            if truncated:
                out[f"{key}_truncated"] = True
                out[f"{key}_chars"] = len(value)
        elif isinstance(value, list) and len(value) > 20:
            kept, omitted = _truncate_list(value, 20)
            out[key] = kept
            out[f"{key}_truncated"] = True
            if omitted:
                out[f"{key}_omitted"] = omitted
        else:
            out[key] = value
    return out


def _slim_payload_dict(tool_name: str, parsed: dict[str, Any] | None, raw_result: str) -> tuple[str, bool]:
    """Return (model_payload, truncated_flag)."""
    if not parsed:
        text, truncated = truncate_head_tail(raw_result or "", SLIM_TOOL_RESULT_MAX_CHARS)
        return text, truncated or len(text) < len(raw_result or "")

    if _is_gate_outcome(parsed, tool_name):
        slim = _slim_gate(parsed)
    elif parsed.get("error"):
        slim = _slim_error(parsed)
    elif tool_name == "read_file":
        slim = _slim_read_file(parsed)
    elif tool_name == "list_dir":
        slim = _slim_list_dir(parsed)
    elif tool_name == "grep":
        slim = _slim_grep(parsed)
    else:
        slim = _slim_generic(parsed)

    model_payload = _dump(slim)
    truncated = bool(slim.get("truncated"))
    truncated = truncated or slim.get("diff_truncated") is True
    truncated = truncated or any(
        str(k).endswith("_truncated") and slim.get(k) is True for k in slim.keys()
    )
    truncated = truncated or len(model_payload) < len(raw_result or "")
    return model_payload, truncated


def _display_summary(tool_name: str, parsed: dict[str, Any] | None, *, truncated: bool) -> str:
    suffix = " (truncated)" if truncated else ""
    if not parsed:
        return f"{tool_name}{suffix}"

    if parsed.get("error"):
        err = str(parsed.get("error") or "error")
        if len(err) > 72:
            err = err[:71] + "…"
        return f"{tool_name} failed: {err}{suffix}"

    if tool_name == "read_file":
        path = parsed.get("path") or "?"
        return f"read_file {path}{suffix}"

    if tool_name == "list_dir":
        path = parsed.get("path") or "?"
        count = parsed.get("entry_count")
        if count is None and isinstance(parsed.get("entries"), list):
            count = len(parsed["entries"])
        extra = f", {count} entries" if count is not None else ""
        return f"list_dir {path}{extra}{suffix}"

    if tool_name == "grep":
        count = parsed.get("match_count")
        if count is None and isinstance(parsed.get("matches"), list):
            count = len(parsed["matches"])
        pattern = parsed.get("pattern") or "?"
        extra = f", {count} matches" if count is not None else ""
        return f"grep {pattern}{extra}{suffix}"

    if _is_gate_outcome(parsed, tool_name):
        status = parsed.get("status") or "?"
        if parsed.get("command"):
            return f"shell {parsed['command']} → {status}{suffix}"
        if parsed.get("path"):
            return f"patch {parsed['path']} → {status}{suffix}"
        if parsed.get("memory_id"):
            return f"memory → {status}{suffix}"
        return f"{tool_name} → {status}{suffix}"

    status = parsed.get("status")
    if status:
        return f"{tool_name} → {status}{suffix}"
    return f"{tool_name} ok{suffix}"


def _resolve_full_ref(
    raw_result: str,
    *,
    truncated: bool,
    spill: SpillFn | None = None,
) -> str | None:
    """Inline ≤ INLINE_FULL_MAX, or spill to file: when spill is provided (F4 Step 3)."""
    if not truncated:
        return None
    raw = raw_result or ""
    if not raw:
        return None
    if spill is not None:
        ref, _spilled = store_full_ref(raw, spill=spill)
        return ref
    if len(raw) <= INLINE_FULL_MAX:
        return raw
    return None


def _attach_file_ref_to_payload(model_payload: str, full_ref: str | None) -> str:
    """Put file: full_ref into slim JSON so the model can find the blob.

    Never inject inline full bodies (would undo slim).
    """
    if not full_ref or not is_file_ref(full_ref):
        return model_payload
    parsed = _try_parse(model_payload)
    if parsed is not None:
        parsed["full_ref"] = full_ref
        hint = str(parsed.get("hint") or "").strip()
        note = f"完整输出已落盘：{full_ref}"
        if note not in hint:
            parsed["hint"] = f"{hint} {note}".strip() if hint else note
        return _dump(parsed)
    return f"{model_payload}\n\n[full_ref={full_ref}]"


def observe_tool_result(
    tool_name: str,
    raw_result: str,
    *,
    spill: SpillFn | None = None,
) -> ObservationResult:
    """F4 primary API — slim for model plus trace metadata (optional data_path spill)."""
    raw = raw_result or ""
    total_chars = len(raw)
    parsed = _try_parse(raw)
    model_payload, truncated = _slim_payload_dict(tool_name, parsed, raw)
    full_ref = _resolve_full_ref(raw, truncated=truncated, spill=spill)
    model_payload = _attach_file_ref_to_payload(model_payload, full_ref)
    return ObservationResult(
        model_payload=model_payload,
        display_summary=_display_summary(tool_name, parsed, truncated=truncated),
        full_ref=full_ref,
        truncated=truncated,
        total_chars=total_chars,
    )


def slim_tool_result(
    tool_name: str,
    raw_result: str,
    *,
    spill: SpillFn | None = None,
) -> str:
    """
    Return a compact JSON string for loop `working[]`.
    Full raw_result is still emitted on SSE / F6 trace.
    """
    return observe_tool_result(tool_name, raw_result, spill=spill).model_payload
