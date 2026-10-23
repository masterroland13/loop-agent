"""TurnEvent schema — shared by F6 (UI trace) and F4 (observation slim / data_path spill)."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

INLINE_FULL_MAX = 8192
FILE_REF_PREFIX = "file:"

TURN_EVENT_TYPES = frozenset(
    {
        "tool_start",
        "tool_result",
        "progress_checkpoint",
        "turn_goal",
        "gate",
        "diff",
        "shell",
        "memory",
        "token",
        "error",
        # A3 lifecycle / steering (lightweight trace; ToolTimeline ignores non-tools)
        "agent_start",
        "agent_end",
        "turn_start",
        "turn_end",
        "steer_inject",
        "soft_land",
        "edit_nudge",
        "thought",
    }
)

SpillFn = Callable[[str], str]


def now_ts() -> int:
    return int(time.time() * 1000)


def is_file_ref(value: str | None) -> bool:
    return bool(value) and str(value).startswith(FILE_REF_PREFIX)


def file_ref_path(value: str) -> str:
    """Strip file: prefix; raises ValueError if not a file ref."""
    if not is_file_ref(value):
        raise ValueError("not a file ref")
    return str(value)[len(FILE_REF_PREFIX) :].lstrip("/").replace("\\", "/")


def _stringify_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def store_full_ref(value: Any, *, spill: SpillFn | None = None) -> tuple[str | None, bool]:
    """
    Return (full_ref, spilled).

    Small payloads stay inline. Oversized ones call spill(text) → file:… ref when
    provided; otherwise truncate to INLINE_FULL_MAX (middle-tier fallback).
    """
    if value is None:
        return None, False
    text = _stringify_payload(value)
    if not text:
        return None, False
    if len(text) <= INLINE_FULL_MAX:
        return text, False
    if spill is not None:
        return spill(text), True
    return text[:INLINE_FULL_MAX], False


def _inline_ref(value: Any) -> str | None:
    """Backward-compatible helper (no spill → truncate)."""
    ref, _ = store_full_ref(value, spill=None)
    return ref


def _tool_status_from_content(content: str | None) -> str:
    if not content:
        return "done"
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            status = parsed.get("status")
            if status:
                return str(status)
            if parsed.get("error"):
                return "failed"
    except (json.JSONDecodeError, TypeError):
        pass
    return "done"


def _summary_snippet(text: str | None, *, limit: int = 400) -> str:
    if not text:
        return ""
    return text[:limit]


def event_from_sse(
    sse: dict[str, Any],
    *,
    spill: SpillFn | None = None,
) -> dict[str, Any] | None:
    """Map a loop/route SSE dict to a persisted TurnEvent. None if not tracked."""
    etype = sse.get("type")
    ts = now_ts()

    if etype == "tool_start":
        name = sse.get("name") or "tool"
        args = sse.get("arguments")
        full_ref, spilled = store_full_ref(args, spill=spill)
        return {
            "type": "tool_start",
            "ts": ts,
            "tool": name,
            "status": "running",
            "summary": name if not spilled else f"{name} · args 已落盘",
            "full_ref": full_ref,
            "truncated": spilled,
            "tool_call_id": sse.get("tool_call_id"),
        }

    if etype == "tool_result":
        name = sse.get("name") or "tool"
        content = sse.get("content") or ""
        status = _tool_status_from_content(content)
        preexisting = sse.get("full_ref")
        if isinstance(preexisting, str) and preexisting.strip():
            full_ref = preexisting.strip()
            spilled = is_file_ref(full_ref)
            truncated = spilled or bool(sse.get("truncated"))
        else:
            full_ref, spilled = store_full_ref(content, spill=spill)
            truncated = spilled or bool(sse.get("truncated"))
        if spilled:
            summary = f"{name} · 大输出已落盘（{len(content)} 字符）"
        elif isinstance(sse.get("summary"), str) and sse["summary"].strip():
            summary = str(sse["summary"]).strip()
        else:
            summary = _summary_snippet(content)
        return {
            "type": "tool_result",
            "ts": ts,
            "tool": name,
            "status": status,
            "summary": summary,
            "full_ref": full_ref,
            "truncated": truncated,
            "tool_call_id": sse.get("tool_call_id"),
        }

    if etype == "progress_checkpoint":
        reply = (sse.get("reply") or "").strip()
        reason = sse.get("reason") or "interval"
        full_ref, spilled = store_full_ref(reply, spill=spill) if reply else (None, False)
        summary = _summary_snippet(reply) if reply else reason
        if spilled and reply:
            summary = _summary_snippet(reply) + " …"
        out: dict[str, Any] = {
            "type": "progress_checkpoint",
            "ts": ts,
            "summary": summary,
            "goal": sse.get("goal"),
            "tools_since_last": sse.get("tools_since_last"),
            "reason": reason,
            "reply": None if spilled else (reply or None),
            "full_ref": full_ref,
            "truncated": spilled,
        }
        if sse.get("settled") and not reply:
            out["settled"] = True
        return out

    if etype == "turn_goal":
        goal = (sse.get("goal") or "").strip()
        if not goal:
            return None
        event: dict[str, Any] = {
            "type": "turn_goal",
            "ts": ts,
            "summary": goal,
            "goal": goal,
        }
        prev = sse.get("previous_goal")
        if isinstance(prev, str):
            prev = prev.strip()
            if prev and prev != goal:
                event["previous_goal"] = prev
        return event

    if etype == "await_approval":
        kind = sse.get("kind") or "approval"
        full_ref, spilled = store_full_ref(sse, spill=spill)
        return {
            "type": "gate",
            "ts": ts,
            "tool": kind,
            "status": "pending",
            "summary": "等待审批…",
            "full_ref": full_ref,
            "truncated": spilled or bool(sse.get("truncated")),
        }

    if etype in ("diff", "shell", "memory"):
        status = sse.get("status") or "pending"
        tool = {
            "diff": "propose_edit",
            "shell": "propose_shell",
            "memory": "propose_memory",
        }.get(etype, etype)
        parts: list[str] = [tool, str(status)]
        if sse.get("path"):
            parts.append(str(sse["path"]))
        elif sse.get("command"):
            parts.append(str(sse["command"]))
        full_ref, spilled = store_full_ref(sse, spill=spill)
        # Keep original SSE type so Activity hydrate does not depend on unpacking gate.
        out: dict[str, Any] = {
            "type": etype,
            "ts": ts,
            "tool": tool,
            "status": str(status),
            "summary": " · ".join(parts),
            "full_ref": full_ref,
            "truncated": spilled or bool(sse.get("truncated")),
        }
        for key in (
            "patch_id",
            "path",
            "is_new_file",
            "is_delete",
            "error",
            "shell_id",
            "command",
            "argv",
            "cwd",
            "exit_code",
            "memory_id",
            "target",
        ):
            if sse.get(key) is not None:
                out[key] = sse.get(key)
        # Small diffs stay inline for +/- counts; large ones live in full_ref only.
        ud = sse.get("unified_diff")
        if isinstance(ud, str) and ud and not spilled:
            out["unified_diff"] = ud
        return out

    if etype == "agent_start":
        return {
            "type": "agent_start",
            "ts": ts,
            "summary": "agent_start",
            "session_id": sse.get("session_id"),
        }

    if etype == "agent_end":
        return {
            "type": "agent_end",
            "ts": ts,
            "summary": "agent_end",
            "session_id": sse.get("session_id"),
        }

    if etype == "turn_start":
        idx = sse.get("index")
        return {
            "type": "turn_start",
            "ts": ts,
            "summary": f"turn_start:{idx}" if idx is not None else "turn_start",
            "index": idx,
        }

    if etype == "turn_end":
        idx = sse.get("index")
        outcome = sse.get("outcome")
        parts = ["turn_end"]
        if idx is not None:
            parts.append(str(idx))
        if outcome:
            parts.append(str(outcome))
        return {
            "type": "turn_end",
            "ts": ts,
            "summary": ":".join(parts),
            "index": idx,
            "outcome": outcome,
        }

    if etype == "steer_inject":
        content = (sse.get("content") or "").strip()
        return {
            "type": "steer_inject",
            "ts": ts,
            "summary": _summary_snippet(content, limit=120) or "steer",
            "content": content or None,
        }

    if etype == "soft_land":
        reason = sse.get("reason") or "max_tool_iters"
        max_iters = sse.get("max_tool_iters")
        tools_ran = sse.get("tools_ran")
        parts = ["soft_land", str(reason)]
        if max_iters is not None:
            parts.append(f"cap={max_iters}")
        if tools_ran is not None:
            parts.append(f"ran={tools_ran}")
        return {
            "type": "soft_land",
            "ts": ts,
            "summary": " · ".join(parts),
            "reason": reason,
            "max_tool_iters": max_iters,
            "tools_ran": tools_ran,
            "goal": sse.get("goal"),
        }

    if etype == "edit_nudge":
        reason = sse.get("reason") or "missing_propose_edit"
        return {
            "type": "edit_nudge",
            "ts": ts,
            "summary": f"edit_nudge · {reason}",
            "reason": reason,
            "goal": sse.get("goal"),
        }

    if etype == "thought":
        text = (sse.get("text") or sse.get("content") or "").strip()
        phase = str(sse.get("phase") or "end")
        duration = sse.get("duration_ms")
        source = sse.get("source") or "reasoning"
        summary = "Thought"
        try:
            if duration is not None and int(duration) < 1000:
                summary = "Thought briefly"
            elif duration is not None:
                summary = f"Thought {max(1, int(round(int(duration) / 1000)))}s"
        except (TypeError, ValueError):
            pass
        full_ref, spilled = store_full_ref(text, spill=spill) if text else (None, False)
        return {
            "type": "thought",
            "ts": ts,
            "summary": summary,
            "phase": phase,
            "text": None if spilled else (text or None),
            "full_ref": full_ref,
            "truncated": spilled,
            "duration_ms": duration,
            "source": source,
        }

    return None


def parse_trace(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def serialize_trace(events: list[dict[str, Any]]) -> str:
    return json.dumps(events, ensure_ascii=False)


def latest_goal(events: list[dict[str, Any]]) -> str | None:
    for ev in reversed(events):
        if ev.get("type") == "turn_goal":
            goal = (ev.get("goal") or ev.get("summary") or "").strip()
            if goal:
                return goal
    return None


def latest_progress_checkpoint(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer newest reply; else newest settled; else newest pending."""
    pending: dict[str, Any] | None = None
    settled: dict[str, Any] | None = None
    for ev in reversed(events):
        if ev.get("type") != "progress_checkpoint":
            continue
        reply = (ev.get("reply") or "").strip()
        if not reply and isinstance(ev.get("full_ref"), str) and not is_file_ref(ev["full_ref"]):
            maybe = ev["full_ref"].strip()
            if maybe and maybe not in ("interval", "gate"):
                reply = maybe
        item: dict[str, Any] = {
            "toolsSinceLast": int(ev.get("tools_since_last") or 0),
            "reason": ev.get("reason") or ev.get("summary") or "interval",
        }
        if reply:
            item["reply"] = reply
            return item
        if is_file_ref(ev.get("full_ref") if isinstance(ev.get("full_ref"), str) else None):
            item["replyRef"] = ev["full_ref"]
            return item
        if ev.get("settled"):
            item["settled"] = True
            if settled is None:
                settled = item
            continue
        if pending is None:
            pending = item
    return settled or pending


def _trace_detail_fields(ev: dict[str, Any]) -> dict[str, Any]:
    full = ev.get("full_ref")
    summary = ev.get("summary") or ""
    if is_file_ref(full if isinstance(full, str) else None):
        return {
            "detail": summary or "大输出已落盘",
            "fullRef": full,
            "truncated": True,
        }
    detail = full if isinstance(full, str) and full else summary
    out: dict[str, Any] = {"detail": detail or ""}
    if ev.get("truncated"):
        out["truncated"] = True
    return out


def events_to_tool_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build UI toolTrace items from persisted TurnEvents."""
    trace: list[dict[str, Any]] = []
    for ev in events:
        etype = ev.get("type")
        if etype == "tool_start":
            item: dict[str, Any] = {
                "name": str(ev.get("tool") or "tool"),
                "status": "running",
                **_trace_detail_fields(ev),
            }
            trace.append(item)
        elif etype == "tool_result":
            name = str(ev.get("tool") or "tool")
            status = str(ev.get("status") or "done")
            is_error = status in ("failed", "timeout", "error", "rejected")
            fields = _trace_detail_fields(ev)
            idx = None
            for i in range(len(trace) - 1, -1, -1):
                if trace[i]["name"] == name and trace[i]["status"] == "running":
                    idx = i
                    break
            item = {
                "name": name,
                "status": "error" if is_error else "done",
                **fields,
            }
            if idx is not None:
                trace[idx] = item
            else:
                trace.append(item)
        elif etype == "gate" and ev.get("status") == "pending":
            if trace and trace[-1]["status"] == "running":
                trace[-1] = {
                    **trace[-1],
                    "detail": ev.get("summary") or "等待审批…",
                }
        elif etype in ("diff", "shell", "memory") and ev.get("status") == "pending":
            if trace and trace[-1]["status"] == "running":
                trace[-1] = {
                    **trace[-1],
                    "detail": ev.get("summary") or "等待审批…",
                }
    return trace
