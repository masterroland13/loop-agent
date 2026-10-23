"""Turn activity timeline: classify SSE / TurnEvent → Explored / Edited / Thought.

S0a pure functions — no UI, no provider. Frontend mirrors this for S0b.
Thought items only come from explicit ``thought`` events (never invented from tools).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence

from agent_window.agent.exploration import EXPLORATION_TOOLS

ActivityKind = Literal["thought", "explore", "edit", "run", "note"]
SegmentKind = Literal["thought", "explored", "edited", "note"]
ExploreAction = Literal["read", "grep", "list", "other"]

EXPLORE_TOOLS = EXPLORATION_TOOLS
EDIT_TOOLS = frozenset({"propose_edit", "propose_delete"})
RUN_TOOLS = frozenset({"propose_shell"})
MEMORY_TOOLS = frozenset({"propose_memory"})

_ERROR_STATUSES = frozenset(
    {"failed", "timeout", "error", "rejected", "cancelled"}
)
_APPLIED_EDIT_STATUSES = frozenset({"applied", "partial"})


@dataclass
class ActivityItem:
    id: str
    kind: ActivityKind
    summary: str
    ts: Optional[int] = None
    # explore
    action: Optional[ExploreAction] = None
    path: Optional[str] = None
    query: Optional[str] = None
    lines: Optional[str] = None
    # edit / run shared status
    status: Optional[str] = None
    patch_id: Optional[str] = None
    shell_id: Optional[str] = None
    add_lines: Optional[int] = None
    del_lines: Optional[int] = None
    command: Optional[str] = None
    exit_code: Optional[int] = None
    # thought
    text: Optional[str] = None
    duration_ms: Optional[int] = None
    source: Optional[str] = None
    # note
    note_type: Optional[str] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ActivitySegment:
    kind: SegmentKind
    summary: str
    items: List[ActivityItem] = field(default_factory=list)
    add_total: int = 0
    del_total: int = 0
    applied_file_count: int = 0
    pending_file_count: int = 0
    rejected_file_count: int = 0
    command_count: int = 0
    file_count: int = 0
    search_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "items": [i.to_dict() for i in self.items],
            "add_total": self.add_total,
            "del_total": self.del_total,
            "applied_file_count": self.applied_file_count,
            "pending_file_count": self.pending_file_count,
            "rejected_file_count": self.rejected_file_count,
            "command_count": self.command_count,
            "file_count": self.file_count,
            "search_count": self.search_count,
        }


def classify_tool(name: str) -> Optional[ActivityKind]:
    """Map tool name → activity kind. Memory is note (never Edited)."""
    n = (name or "").strip()
    if n in EXPLORE_TOOLS:
        return "explore"
    if n in EDIT_TOOLS:
        return "edit"
    if n in RUN_TOOLS:
        return "run"
    if n in MEMORY_TOOLS:
        return "note"
    return None


def count_diff_lines(unified_diff: str | None) -> tuple[int, int]:
    """Count added/removed content lines in a unified diff (exclude headers)."""
    if not unified_diff:
        return 0, 0
    add = 0
    delete = 0
    for line in unified_diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            add += 1
        elif line.startswith("-"):
            delete += 1
    return add, delete


def tool_name_of(event: Dict[str, Any]) -> str:
    return str(event.get("name") or event.get("tool") or "").strip()


def _parse_json_obj(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_tool_arguments(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse tool args from live SSE ``arguments`` or persisted ``full_ref`` JSON."""
    raw = event.get("arguments")
    if raw is None:
        ref = event.get("full_ref")
        if isinstance(ref, str) and ref.strip() and not ref.startswith("file:"):
            raw = ref
    return _parse_json_obj(raw)


def _tool_result_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Live SSE uses ``content``; F6 persistence keeps the body in ``full_ref``."""
    return (
        _parse_json_obj(event.get("content"))
        or _parse_json_obj(event.get("full_ref"))
        or _parse_json_obj(event.get("summary"))
        or {}
    )


def normalize_activity_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Expand persisted TurnEvent shapes into live SSE-like activity events.

    - ``tool_start`` / ``tool_result`` use ``tool=`` instead of ``name=``
    - Historical F6 mapped ``diff``/``shell``/``memory`` SSE → ``type=gate`` + ``full_ref``
    """
    if not isinstance(event, dict):
        return {}
    out = dict(event)
    etype = str(out.get("type") or "")

    if etype in ("tool_start", "tool_result") and not out.get("name") and out.get("tool"):
        out["name"] = out["tool"]

    if etype != "gate":
        return out

    tool = str(out.get("tool") or "").strip()
    payload = _parse_json_obj(out.get("full_ref"))
    payload_type = str(payload.get("type") or "").strip()

    if tool == "propose_edit" or payload_type == "diff":
        merged = {**payload, **{k: v for k, v in out.items() if k not in payload or v is not None}}
        return {
            **merged,
            "type": "diff",
            "status": out.get("status") or payload.get("status") or "pending",
            "patch_id": payload.get("patch_id") or out.get("patch_id"),
            "path": payload.get("path") or out.get("path"),
            "unified_diff": payload.get("unified_diff") or out.get("unified_diff"),
            "is_new_file": payload.get("is_new_file", out.get("is_new_file")),
            "is_delete": payload.get("is_delete", out.get("is_delete")),
            "error": payload.get("error", out.get("error")),
        }

    if tool == "propose_shell" or payload_type == "shell":
        merged = {**payload, **{k: v for k, v in out.items() if k not in payload or v is not None}}
        return {
            **merged,
            "type": "shell",
            "status": out.get("status") or payload.get("status") or "pending",
            "shell_id": payload.get("shell_id") or payload.get("id") or out.get("shell_id"),
            "command": payload.get("command") or out.get("command"),
            "argv": payload.get("argv") or out.get("argv"),
            "exit_code": payload.get("exit_code", out.get("exit_code")),
        }

    if tool == "propose_memory" or payload_type == "memory":
        merged = {**payload, **{k: v for k, v in out.items() if k not in payload or v is not None}}
        return {
            **merged,
            "type": "memory",
            "status": out.get("status") or payload.get("status") or "pending",
            "memory_id": payload.get("memory_id") or payload.get("id") or out.get("memory_id"),
            "target": payload.get("target") or out.get("target") or "memory",
        }

    # await_approval and unknown gates are ignored by ActivityBuilder.apply
    return out


def _basename(path: str | None) -> str:
    if not path:
        return ""
    p = path.replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1] if p else path


def _line_range(args: Dict[str, Any]) -> Optional[str]:
    offset = args.get("offset")
    limit = args.get("limit")
    try:
        if offset is None and limit is None:
            return None
        start = int(offset) if offset is not None else 1
        if limit is None:
            return f"L{start}+"
        end = start + int(limit) - 1
        if end < start:
            end = start
        return f"L{start}–{end}"
    except (TypeError, ValueError):
        return None


def _explore_action(tool: str) -> ExploreAction:
    if tool == "read_file" or tool == "read_attachment":
        return "read"
    if tool == "grep":
        return "grep"
    if tool == "list_dir":
        return "list"
    return "other"


def _explore_summary(action: ExploreAction, path: Optional[str], query: Optional[str], lines: Optional[str]) -> str:
    label = _basename(path) or (path or "")
    if action == "read":
        base = f"Read {label}" if label else "Read file"
        return f"{base} {lines}".strip() if lines else base
    if action == "grep":
        q = (query or "").strip()
        q_bit = f" `{q}`" if q else ""
        where = f" in {label}" if label else ""
        return f"Grepped{q_bit}{where}".strip()
    if action == "list":
        return f"Listed {label}" if label else "Listed directory"
    return label or "Explored"


def _edit_summary(path: Optional[str], status: str, add_n: int, del_n: int) -> str:
    label = _basename(path) or path or "file"
    if status in _APPLIED_EDIT_STATUSES:
        return f"Edited {label} +{add_n} −{del_n}"
    if status == "pending":
        return f"Proposed {label}"
    if status == "rejected":
        return f"Rejected {label}"
    if status == "partial":
        return f"Partially edited {label} +{add_n} −{del_n}"
    return f"Edit {label} ({status})"


def _run_summary(command: Optional[str], status: str, exit_code: Optional[int]) -> str:
    cmd = (command or "").strip() or "command"
    if len(cmd) > 80:
        cmd = cmd[:77] + "…"
    if status == "pending" or status == "running":
        return f"Ran {cmd}"
    if status == "done" or status == "applied":
        if exit_code is not None and exit_code != 0:
            return f"Ran {cmd} (exit {exit_code})"
        return f"Ran {cmd}"
    return f"Ran {cmd} ({status})"


def _thought_summary(duration_ms: Optional[int], text: Optional[str]) -> str:
    if duration_ms is not None and duration_ms < 1000:
        return "Thought briefly"
    if duration_ms is not None:
        secs = max(1, int(round(duration_ms / 1000)))
        return f"Thought {secs}s"
    if text and text.strip():
        return "Thought"
    return "Thought"


# Short thoughts nest into adjacent Explored/Edited segments (Cursor-style).
# Long thoughts stay top-level and break merge. Never drop thought text.
_NESTABLE_THOUGHT_MS = 5000


def _is_nestable_thought(it: ActivityItem) -> bool:
    if it.kind != "thought":
        return False
    if it.duration_ms is None:
        return True
    return it.duration_ms < _NESTABLE_THOUGHT_MS


def group_activity_items(
    items: Sequence[ActivityItem],
    *,
    merge: bool = True,
) -> List[ActivitySegment]:
    """Group consecutive explore / edit+run items.

    Short thoughts nest into the open tool segment in chronological order
    (or attach to the next tool segment if none is open yet). Long thoughts
    and notes remain top-level and break merge. No items are dropped.
    """
    if not merge:
        return [_singleton_segment(it) for it in items]

    segments: List[ActivitySegment] = []
    buf: List[ActivityItem] = []
    buf_kind: Optional[SegmentKind] = None
    leading_thoughts: List[ActivityItem] = []

    def flush_buf() -> None:
        nonlocal buf, buf_kind
        if not buf or buf_kind is None:
            buf = []
            buf_kind = None
            return
        segments.append(_build_segment(buf_kind, buf))
        buf = []
        buf_kind = None

    def flush_leading_as_top() -> None:
        nonlocal leading_thoughts
        for thought in leading_thoughts:
            segments.append(_build_segment("thought", [thought]))
        leading_thoughts = []

    for it in items:
        sk = _item_segment_kind(it)
        if sk == "note":
            flush_buf()
            flush_leading_as_top()
            segments.append(_build_segment("note", [it]))
            continue
        if sk == "thought":
            if _is_nestable_thought(it):
                if buf_kind is not None:
                    buf.append(it)
                else:
                    leading_thoughts.append(it)
            else:
                flush_buf()
                flush_leading_as_top()
                segments.append(_build_segment("thought", [it]))
            continue
        # explored / edited tool buckets
        if buf_kind is None:
            buf_kind = sk
            buf = [*leading_thoughts, it]
            leading_thoughts = []
            continue
        if sk == buf_kind:
            buf.append(it)
            continue
        flush_buf()
        buf_kind = sk
        buf = [*leading_thoughts, it]
        leading_thoughts = []
    flush_buf()
    flush_leading_as_top()
    return segments


def _item_segment_kind(it: ActivityItem) -> SegmentKind:
    if it.kind == "thought":
        return "thought"
    if it.kind == "note":
        return "note"
    if it.kind == "explore":
        return "explored"
    # edit + run share the Edited / Ran bucket
    return "edited"


def _singleton_segment(it: ActivityItem) -> ActivitySegment:
    return _build_segment(_item_segment_kind(it), [it])


def _build_segment(kind: SegmentKind, items: List[ActivityItem]) -> ActivitySegment:
    if kind == "thought":
        it = items[0]
        return ActivitySegment(
            kind="thought",
            summary=_thought_summary(it.duration_ms, it.text),
            items=list(items),
        )
    if kind == "note":
        it = items[0]
        return ActivitySegment(
            kind="note",
            summary=it.summary,
            items=list(items),
        )
    if kind == "explored":
        paths: List[str] = []
        search_count = 0
        for it in items:
            if it.action == "grep":
                search_count += 1
            elif it.path:
                paths.append(it.path)
            elif it.action == "list":
                paths.append(it.path or ".")
        # unique files/dirs for "N files"
        file_count = len({p.replace("\\", "/") for p in paths if p})
        parts: List[str] = []
        if file_count:
            parts.append(f"{file_count} file" + ("s" if file_count != 1 else ""))
        if search_count:
            parts.append(f"{search_count} search" + ("es" if search_count != 1 else ""))
        if not parts:
            explore_n = sum(1 for x in items if x.kind == "explore")
            n = explore_n or len(items)
            parts.append(f"{n} step" + ("s" if n != 1 else ""))
        return ActivitySegment(
            kind="explored",
            summary="Explored " + ", ".join(parts),
            items=list(items),
            file_count=file_count,
            search_count=search_count,
        )

    # edited bucket
    applied = 0
    pending = 0
    rejected = 0
    add_total = 0
    del_total = 0
    commands = 0
    for it in items:
        if it.kind == "thought":
            continue
        if it.kind == "run":
            commands += 1
            continue
        if it.kind != "edit":
            continue
        st = (it.status or "").lower()
        if st in _APPLIED_EDIT_STATUSES:
            applied += 1
            add_total += int(it.add_lines or 0)
            del_total += int(it.del_lines or 0)
        elif st == "pending":
            pending += 1
        elif st in ("rejected", "failed", "timeout", "cancelled"):
            rejected += 1
        else:
            pending += 1

    bits: List[str] = []
    if applied:
        bits.append(f"Edited {applied} file" + ("s" if applied != 1 else ""))
    if pending:
        bits.append(f"proposed {pending}")
    if rejected and not applied and not pending:
        bits.append(f"Rejected {rejected} file" + ("s" if rejected != 1 else ""))
    elif rejected:
        bits.append(f"{rejected} rejected")
    if commands:
        bits.append(f"ran {commands} command" + ("s" if commands != 1 else ""))
    if not bits:
        bits.append("Edited")
    summary = bits[0]
    if len(bits) > 1:
        summary = bits[0] + ", " + ", ".join(bits[1:])
    # Only applied +/- in the segment title (honest: pending does not inflate)
    if applied and (add_total or del_total):
        summary = f"{summary}  +{add_total} −{del_total}"

    return ActivitySegment(
        kind="edited",
        summary=summary,
        items=list(items),
        add_total=add_total,
        del_total=del_total,
        applied_file_count=applied,
        pending_file_count=pending,
        rejected_file_count=rejected,
        command_count=commands,
    )


class ActivityBuilder:
    """Incremental reducer for live SSE or persisted TurnEvent dicts."""

    def __init__(self) -> None:
        self.items: List[ActivityItem] = []
        self._seq = 0
        self._open_explore: Dict[str, int] = {}
        self._edit_by_patch: Dict[str, int] = {}
        self._run_by_shell: Dict[str, int] = {}
        self._open_thought_idx: Optional[int] = None

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def apply(self, event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        event = normalize_activity_event(event)
        etype = str(event.get("type") or "")
        if etype == "thought":
            self._apply_thought(event)
        elif etype == "tool_start":
            self._apply_tool_start(event)
        elif etype == "tool_result":
            self._apply_tool_result(event)
        elif etype == "diff":
            self._apply_diff(event)
        elif etype == "shell":
            self._apply_shell(event)
        elif etype in ("edit_nudge", "soft_land"):
            self._apply_note(event, note_type=etype)
        elif etype == "memory":
            # memory gate SSE if present
            self._apply_memory_event(event)

    def apply_many(self, events: Iterable[Dict[str, Any]]) -> None:
        for ev in events:
            self.apply(ev)

    def segments(self, *, merge: bool = True) -> List[ActivitySegment]:
        return group_activity_items(self.items, merge=merge)

    def snapshot(self, *, merge: bool = True) -> Dict[str, Any]:
        segs = self.segments(merge=merge)
        applied = sum(s.applied_file_count for s in segs if s.kind == "edited")
        pending = sum(s.pending_file_count for s in segs if s.kind == "edited")
        add_total = sum(s.add_total for s in segs if s.kind == "edited")
        del_total = sum(s.del_total for s in segs if s.kind == "edited")
        return {
            "items": [i.to_dict() for i in self.items],
            "segments": [s.to_dict() for s in segs],
            "stats": {
                "applied_file_count": applied,
                "pending_file_count": pending,
                "add_total": add_total,
                "del_total": del_total,
                "has_thought": any(i.kind == "thought" for i in self.items),
            },
        }

    def _apply_thought(self, event: Dict[str, Any]) -> None:
        phase = str(event.get("phase") or "end").lower()
        text = event.get("text")
        text_s = str(text) if text is not None else ""
        if not text_s.strip():
            ref = event.get("full_ref")
            if isinstance(ref, str) and ref.strip() and not ref.startswith("file:"):
                text_s = ref.strip()
        duration = event.get("duration_ms")
        try:
            duration_i = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_i = None
        source = event.get("source")
        source_s = str(source) if source else "reasoning"
        ts = event.get("ts")
        ts_i = int(ts) if isinstance(ts, (int, float)) else None

        if phase == "start":
            item = ActivityItem(
                id=self._next_id("thought"),
                kind="thought",
                summary=_thought_summary(None, None),
                text="",
                source=source_s,
                ts=ts_i,
            )
            self.items.append(item)
            self._open_thought_idx = len(self.items) - 1
            return

        if phase == "delta":
            if self._open_thought_idx is None:
                item = ActivityItem(
                    id=self._next_id("thought"),
                    kind="thought",
                    summary=_thought_summary(None, text_s),
                    text=text_s,
                    source=source_s,
                    ts=ts_i,
                )
                self.items.append(item)
                self._open_thought_idx = len(self.items) - 1
            else:
                cur = self.items[self._open_thought_idx]
                cur.text = (cur.text or "") + text_s
                cur.summary = _thought_summary(cur.duration_ms, cur.text)
            return

        # end or whole-block (no open stream)
        if self._open_thought_idx is not None:
            cur = self.items[self._open_thought_idx]
            if text_s and not (cur.text or "").strip():
                cur.text = text_s
            elif text_s and phase == "end":
                # end payload is optional final chunk; append only if distinct suffix
                if not (cur.text or "").endswith(text_s):
                    cur.text = (cur.text or "") + text_s
            if duration_i is not None:
                cur.duration_ms = duration_i
            cur.summary = _thought_summary(cur.duration_ms, cur.text)
            self._open_thought_idx = None
            return

        item = ActivityItem(
            id=self._next_id("thought"),
            kind="thought",
            summary=_thought_summary(duration_i, text_s),
            text=text_s or None,
            duration_ms=duration_i,
            source=source_s,
            ts=ts_i,
        )
        self.items.append(item)

    def _apply_tool_start(self, event: Dict[str, Any]) -> None:
        name = tool_name_of(event)
        kind = classify_tool(name)
        if kind != "explore":
            # edit/run/memory appear via diff/shell/note events
            return
        args = parse_tool_arguments(event)
        action = _explore_action(name)
        path = args.get("path")
        path_s = str(path).strip() if path is not None else None
        query = args.get("query") or args.get("pattern")
        query_s = str(query).strip() if query is not None else None
        lines = _line_range(args)
        call_id = event.get("tool_call_id")
        call_s = str(call_id) if call_id else None
        item = ActivityItem(
            id=self._next_id("explore"),
            kind="explore",
            summary=_explore_summary(action, path_s, query_s, lines),
            action=action,
            path=path_s,
            query=query_s,
            lines=lines,
            status="running",
            tool_call_id=call_s,
            ts=event.get("ts") if isinstance(event.get("ts"), int) else None,
        )
        self.items.append(item)
        if call_s:
            self._open_explore[call_s] = len(self.items) - 1

    def _apply_tool_result(self, event: Dict[str, Any]) -> None:
        name = tool_name_of(event)
        kind = classify_tool(name)
        status = str(event.get("status") or "done")
        call_id = event.get("tool_call_id")
        call_s = str(call_id) if call_id else None

        if kind == "explore":
            idx: Optional[int] = None
            if call_s and call_s in self._open_explore:
                idx = self._open_explore.pop(call_s)
            else:
                for i in range(len(self.items) - 1, -1, -1):
                    it = self.items[i]
                    if it.kind == "explore" and it.status == "running" and (
                        not call_s or it.tool_call_id == call_s
                    ):
                        idx = i
                        break
            if idx is not None:
                it = self.items[idx]
                it.status = "error" if status.lower() in _ERROR_STATUSES else "done"
            return

        if kind == "edit":
            # Hydration / no live diff SSE: infer from tool_result JSON.
            parsed = _tool_result_payload(event)
            patch_id = str(parsed.get("patch_id") or "").strip()
            path = parsed.get("path")
            path_s = str(path) if path is not None else None
            st = str(parsed.get("status") or status or "done").lower()
            if patch_id and patch_id in self._edit_by_patch:
                it = self.items[self._edit_by_patch[patch_id]]
                it.status = st
                if path_s:
                    it.path = path_s
                it.summary = _edit_summary(
                    it.path, st, int(it.add_lines or 0), int(it.del_lines or 0)
                )
                return
            if patch_id or path_s:
                item = ActivityItem(
                    id=self._next_id("edit"),
                    kind="edit",
                    summary=_edit_summary(path_s, st, 0, 0),
                    path=path_s,
                    status=st,
                    patch_id=patch_id or None,
                    add_lines=0,
                    del_lines=0,
                    tool_call_id=call_s,
                )
                self.items.append(item)
                if patch_id:
                    self._edit_by_patch[patch_id] = len(self.items) - 1
            return

        if kind == "run":
            parsed = _tool_result_payload(event)
            shell_id = str(parsed.get("shell_id") or "").strip()
            command = parsed.get("command")
            command_s = str(command) if command is not None else None
            st = str(parsed.get("status") or status or "done").lower()
            exit_code = parsed.get("exit_code")
            try:
                exit_i = int(exit_code) if exit_code is not None else None
            except (TypeError, ValueError):
                exit_i = None
            if shell_id and shell_id in self._run_by_shell:
                it = self.items[self._run_by_shell[shell_id]]
                it.status = st
                if command_s:
                    it.command = command_s
                if exit_i is not None:
                    it.exit_code = exit_i
                it.summary = _run_summary(it.command, st, it.exit_code)
                return
            if shell_id or command_s:
                item = ActivityItem(
                    id=self._next_id("run"),
                    kind="run",
                    summary=_run_summary(command_s, st, exit_i),
                    status=st,
                    shell_id=shell_id or None,
                    command=command_s,
                    exit_code=exit_i,
                    tool_call_id=call_s,
                )
                self.items.append(item)
                if shell_id:
                    self._run_by_shell[shell_id] = len(self.items) - 1
            return

        if kind == "note" and name in MEMORY_TOOLS:
            # Prefer dedicated memory SSE; if only tool_result, record a note once.
            parsed = _tool_result_payload(event)
            err = str(parsed.get("error") or "").strip()
            code = str(parsed.get("code") or "").strip().upper()
            if code == "DUPLICATE" or "duplicate" in err.lower():
                preview = "Memory · already present (duplicate)"
            elif err:
                preview = f"Memory · {err[:160]}"
            else:
                preview = event.get("summary") or "Memory update"
            st = str(parsed.get("status") or status or "done")
            self.items.append(
                ActivityItem(
                    id=self._next_id("note"),
                    kind="note",
                    summary=str(preview)[:200],
                    note_type="propose_memory",
                    status=st,
                    tool_call_id=call_s,
                )
            )

    def _apply_diff(self, event: Dict[str, Any]) -> None:
        patch_id = str(event.get("patch_id") or "").strip()
        if not patch_id:
            return
        path = event.get("path")
        path_s = str(path) if path is not None else None
        status = str(event.get("status") or "pending").lower()
        diff = event.get("unified_diff")
        if diff is None:
            diff = _parse_json_obj(event.get("full_ref")).get("unified_diff")
        add_n, del_n = count_diff_lines(str(diff) if diff is not None else None)
        # Only credit +/- when applied/partial (pending keeps counts for detail but stats use applied)
        show_add = add_n if status in _APPLIED_EDIT_STATUSES or status == "pending" else add_n
        show_del = del_n if status in _APPLIED_EDIT_STATUSES or status == "pending" else del_n

        if patch_id in self._edit_by_patch:
            it = self.items[self._edit_by_patch[patch_id]]
            it.status = status
            it.path = path_s or it.path
            it.add_lines = show_add
            it.del_lines = show_del
            it.summary = _edit_summary(it.path, status, show_add, show_del)
            return

        item = ActivityItem(
            id=self._next_id("edit"),
            kind="edit",
            summary=_edit_summary(path_s, status, show_add, show_del),
            path=path_s,
            status=status,
            patch_id=patch_id,
            add_lines=show_add,
            del_lines=show_del,
            ts=event.get("ts") if isinstance(event.get("ts"), int) else None,
        )
        self.items.append(item)
        self._edit_by_patch[patch_id] = len(self.items) - 1

    def _apply_shell(self, event: Dict[str, Any]) -> None:
        shell_id = str(event.get("shell_id") or event.get("id") or "").strip()
        if not shell_id:
            return
        command = event.get("command")
        if not command and event.get("argv"):
            argv = event["argv"]
            if isinstance(argv, list):
                command = " ".join(str(a) for a in argv)
        command_s = str(command) if command is not None else None
        status = str(event.get("status") or "pending").lower()
        exit_code = event.get("exit_code")
        try:
            exit_i = int(exit_code) if exit_code is not None else None
        except (TypeError, ValueError):
            exit_i = None

        if shell_id in self._run_by_shell:
            it = self.items[self._run_by_shell[shell_id]]
            it.status = status
            it.command = command_s or it.command
            it.exit_code = exit_i if exit_i is not None else it.exit_code
            it.summary = _run_summary(it.command, status, it.exit_code)
            return

        item = ActivityItem(
            id=self._next_id("run"),
            kind="run",
            summary=_run_summary(command_s, status, exit_i),
            status=status,
            shell_id=shell_id,
            command=command_s,
            exit_code=exit_i,
            ts=event.get("ts") if isinstance(event.get("ts"), int) else None,
        )
        self.items.append(item)
        self._run_by_shell[shell_id] = len(self.items) - 1

    def _apply_note(self, event: Dict[str, Any], *, note_type: str) -> None:
        if note_type == "edit_nudge":
            summary = "催促提出文件修改（edit_nudge）"
        elif note_type == "soft_land":
            summary = "工具轮次触顶软着陆"
        else:
            summary = note_type
        reason = event.get("reason") or event.get("summary")
        if reason:
            summary = f"{summary} · {reason}"
        self.items.append(
            ActivityItem(
                id=self._next_id("note"),
                kind="note",
                summary=summary[:240],
                note_type=note_type,
                ts=event.get("ts") if isinstance(event.get("ts"), int) else None,
            )
        )

    def _apply_memory_event(self, event: Dict[str, Any]) -> None:
        status = str(event.get("status") or "pending")
        target = event.get("target") or "memory"
        summary = f"Memory ({target}) {status}"
        self.items.append(
            ActivityItem(
                id=self._next_id("note"),
                kind="note",
                summary=summary,
                note_type="propose_memory",
                status=status,
            )
        )


def build_turn_activity(
    events: Sequence[Dict[str, Any]],
    *,
    merge: bool = True,
) -> Dict[str, Any]:
    """Reduce a list of SSE / TurnEvent dicts into activity items + segments."""
    builder = ActivityBuilder()
    builder.apply_many(events)
    return builder.snapshot(merge=merge)
