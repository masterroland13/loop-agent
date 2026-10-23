"""Gate await handlers — Gate 深拆 Step 1–3.

``propose_*`` = **prepare** only (create pending + AWAIT_* intent).
``resolve_await_marker`` = **before_tool_call settle** (pending SSE + wait/auto-apply).
``tool_pipeline`` order: prepare → before(pre) → settle(await_gate) → execute
(non-gate only) → after. Loop never awaits.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Literal, Optional

from agent_window.services.agent_settings import load_agent_settings
from agent_window.services.memory import MemoryStatus, decide_memory, wait_for_memory_decision
from agent_window.services.patches import PatchStatus, decide_patch, wait_for_decision
from agent_window.services.shell import ShellStatus, decide_shell, shell_to_public, wait_for_shell_decision
from agent_window.services.workspace import WorkspaceError
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY
from agent_window.tools.memory_tools import AWAIT_MEMORY_KEY
from agent_window.tools.shell_tools import AWAIT_SHELL_KEY

logger = logging.getLogger(__name__)

AwaitKind = Literal["patch", "shell", "memory"]


def await_marker_kind(parsed: Optional[Dict[str, Any]]) -> Optional[AwaitKind]:
    """Return gate kind if ``parsed`` is an unresolved AWAIT_* tool payload."""
    if not parsed:
        return None
    if parsed.get(AWAIT_PATCH_KEY):
        return "patch"
    if parsed.get(AWAIT_SHELL_KEY):
        return "shell"
    if parsed.get(AWAIT_MEMORY_KEY):
        return "memory"
    return None


def still_has_await_marker(parsed: Optional[Dict[str, Any]]) -> bool:
    """True when tool JSON still contains an unresolved AWAIT_* key."""
    return await_marker_kind(parsed) is not None


async def abandon_await_proposal(parsed: Dict[str, Any]) -> None:
    """Cancel a prepared pending proposal (e.g. before_tool_call blocked).

    Uses reject so the waiter/event is cleared; caller returns ``blocked`` tool
    JSON (not user-rejected F3 template).
    """
    kind = await_marker_kind(parsed)
    try:
        if kind == "patch":
            patch = parsed.get("patch") or {}
            pid = patch.get("id")
            if pid:
                await decide_patch(str(pid), "reject")
        elif kind == "shell":
            shell = parsed.get("shell") or {}
            sid = shell.get("id")
            if sid:
                await decide_shell(str(sid), "reject")
        elif kind == "memory":
            memory = parsed.get("memory") or {}
            mid = memory.get("id")
            if mid:
                await decide_memory(str(mid), "reject")
    except WorkspaceError as e:
        logger.debug("abandon_await_proposal: %s", e)
    except Exception:
        logger.exception("abandon_await_proposal failed")


async def handle_patch_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
    *,
    auto_apply: bool = False,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    """Yields (sse_event, final_tool_result_or_None). Last yield has the result string.

    When ``auto_apply`` (YOLO): skip pending SSE / await_approval; apply immediately
    and emit the final diff status only.
    """
    patch = parsed["patch"]
    patch_id = patch["id"]
    # YOLO: skip pending SSE so DiffPanel does not flash confirmation cards.
    if not auto_apply:
        yield (
            {
                "type": "diff",
                "patch_id": patch_id,
                "path": patch["path"],
                "unified_diff": patch["unified_diff"],
                "is_new_file": patch.get("is_new_file", False),
                "is_delete": patch.get("is_delete", False),
                "status": "pending",
            },
            None,
        )

    if auto_apply:
        decided = await decide_patch(patch_id, "apply")
    else:
        yield (
            {"type": "await_approval", "kind": "patch", "patch_id": patch_id, "path": patch["path"]},
            None,
        )
        decided = await wait_for_decision(patch_id, cancel_event=cancel_event)

    status = decided.status
    yield (
        {
            "type": "diff",
            "patch_id": patch_id,
            "path": decided.path,
            "unified_diff": decided.unified_diff,
            "is_new_file": decided.is_new_file,
            "is_delete": decided.is_delete,
            "status": status.value,
            "error": decided.error,
        },
        None,
    )

    if status == PatchStatus.APPLIED:
        result = {"status": "applied", "patch_id": patch_id, "path": decided.path}
    elif status == PatchStatus.PARTIAL:
        result = {
            "status": "partial",
            "patch_id": patch_id,
            "path": decided.path,
            "applied_hunks": decided.applied_hunks or [],
            "message": (
                "User applied only the selected hunks; the rest of this edit was skipped. "
                "Do not claim the full edit was written. If the user asks for the remaining "
                "changes, call propose_edit again with just those changes."
            ),
        }
    elif status == PatchStatus.REJECTED:
        result = {
            "status": "rejected",
            "patch_id": patch_id,
            "path": decided.path,
            "message": (
                "User rejected the edit. If the user asks to retry or revise, "
                "call propose_edit or propose_delete again; do not reply with text only."
            ),
        }
    elif status == PatchStatus.FAILED:
        result = {
            "status": "failed",
            "patch_id": patch_id,
            "path": decided.path,
            "error": decided.error,
        }
    elif status == PatchStatus.CANCELLED:
        result = {
            "status": "cancelled",
            "patch_id": patch_id,
            "path": decided.path,
            "message": "Turn cancelled; edit not applied.",
        }
    else:
        result = {
            "status": "timeout",
            "patch_id": patch_id,
            "path": decided.path,
            "message": "Approval timed out; edit not applied.",
        }
    yield ({"type": "_result"}, json.dumps(result, ensure_ascii=False))


async def handle_shell_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
    *,
    auto_apply: bool = False,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    """Shell gate. ``auto_apply`` (YOLO): skip await_approval, decide apply immediately."""
    shell = parsed["shell"]
    shell_id = shell["id"]
    # YOLO: skip pending SSE so the UI does not flash Apply/Reject confirmation cards.
    if not auto_apply:
        yield (
            {
                "type": "shell",
                "shell_id": shell_id,
                "argv": shell.get("argv"),
                "cwd": shell.get("cwd"),
                "command": shell.get("command"),
                "status": "pending",
            },
            None,
        )

    if auto_apply:
        decided = await decide_shell(shell_id, "apply")
    else:
        yield (
            {
                "type": "await_approval",
                "kind": "shell",
                "shell_id": shell_id,
                "command": shell.get("command"),
            },
            None,
        )
        decided = await wait_for_shell_decision(shell_id, cancel_event=cancel_event)

    public = shell_to_public(decided)
    yield (
        {
            "type": "shell",
            "shell_id": shell_id,
            "argv": public["argv"],
            "cwd": public["cwd"],
            "command": public["command"],
            "status": public["status"],
            "exit_code": public["exit_code"],
            "stdout": public["stdout"],
            "stderr": public["stderr"],
            "truncated": public["truncated"],
            "error": public["error"],
        },
        None,
    )

    if decided.status == ShellStatus.DONE:
        result = {
            "status": "done",
            "shell_id": shell_id,
            "command": decided.command_display,
            "exit_code": decided.exit_code,
            "stdout": decided.stdout,
            "stderr": decided.stderr,
            "truncated": decided.truncated,
        }
    elif decided.status == ShellStatus.REJECTED:
        result = {
            "status": "rejected",
            "shell_id": shell_id,
            "command": decided.command_display,
            "message": (
                "User rejected the command. If the user asks to retry or revise, "
                "call propose_shell again; do not reply with text only."
            ),
        }
    elif decided.status == ShellStatus.TIMEOUT:
        result = {
            "status": "timeout",
            "shell_id": shell_id,
            "command": decided.command_display,
            "error": decided.error or "Approval or command timed out.",
        }
    elif decided.status == ShellStatus.CANCELLED:
        result = {
            "status": "cancelled",
            "shell_id": shell_id,
            "command": decided.command_display,
            "message": "Turn cancelled; command not run.",
        }
    else:
        result = {
            "status": "failed",
            "shell_id": shell_id,
            "command": decided.command_display,
            "error": decided.error,
            "exit_code": decided.exit_code,
            "stdout": decided.stdout,
            "stderr": decided.stderr,
        }
    yield ({"type": "_result"}, json.dumps(result, ensure_ascii=False))


async def handle_memory_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
    *,
    auto_apply: bool = False,
    force_confirm_memory: bool = False,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    """Memory gate. YOLO auto-applies; Strict always confirms; Trusted uses confirm_memory."""
    from agent_window.core.preset_hooks import GatePresetDecision, memory_will_auto_apply

    memory = parsed["memory"]
    memory_id = memory["id"]
    agent_cfg = load_agent_settings()
    decision = GatePresetDecision(
        auto_apply=auto_apply,
        force_confirm_memory=force_confirm_memory,
    )
    will_auto = memory_will_auto_apply(
        decision,
        confirm_memory=bool(agent_cfg.get("confirm_memory", True)),
    )
    # YOLO / auto-memory: skip pending SSE to avoid confirmation-card flicker.
    if not will_auto:
        yield (
            {
                "type": "memory",
                "memory_id": memory_id,
                "mode": memory.get("mode"),
                "target": memory.get("target") or "user",
                "preview": memory.get("preview"),
                "content": memory.get("content"),
                "op_summary": memory.get("op_summary") or "",
                "status": "pending",
            },
            None,
        )

    if will_auto:
        decided = await decide_memory(memory_id, "apply")
    else:
        yield (
            {
                "type": "await_approval",
                "kind": "memory",
                "memory_id": memory_id,
            },
            None,
        )
        decided = await wait_for_memory_decision(memory_id, cancel_event=cancel_event)

    yield (
        {
            "type": "memory",
            "memory_id": memory_id,
            "mode": decided.mode,
            "target": getattr(decided, "target", None) or memory.get("target") or "user",
            "preview": decided.preview,
            "content": decided.content,
            "op_summary": getattr(decided, "op_summary", None) or memory.get("op_summary") or "",
            "status": decided.status.value,
            "error": decided.error,
        },
        None,
    )

    if decided.status == MemoryStatus.APPLIED:
        result = {
            "status": "applied",
            "memory_id": memory_id,
            "mode": decided.mode,
            "target": getattr(decided, "target", None) or memory.get("target") or "user",
        }
    elif decided.status == MemoryStatus.REJECTED:
        result = {
            "status": "rejected",
            "memory_id": memory_id,
            "message": "User rejected the memory update.",
        }
    elif decided.status == MemoryStatus.FAILED:
        result = {
            "status": "failed",
            "memory_id": memory_id,
            "error": decided.error,
        }
    elif decided.status == MemoryStatus.CANCELLED:
        result = {
            "status": "cancelled",
            "memory_id": memory_id,
            "message": "Turn cancelled; memory not written.",
        }
    else:
        result = {
            "status": "timeout",
            "memory_id": memory_id,
            "message": "Approval timed out; memory not written.",
        }
    yield ({"type": "_result"}, json.dumps(result, ensure_ascii=False))


async def resolve_await_marker(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
    *,
    auto_apply: bool = False,
    force_confirm_memory: bool = False,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    """Resolve an AWAIT_* tool payload into SSE events + final tool JSON.

    Always yields a final ``({"type": "_result"}, <json>)`` when ``parsed`` is an
    await marker (including missing-payload failures). Caller must not call this
    for non-marker results.
    """
    kind = await_marker_kind(parsed)
    if kind == "patch":
        if not parsed.get("patch"):
            yield (
                {"type": "_result"},
                json.dumps(
                    {
                        "status": "failed",
                        "error": "propose_edit/propose_delete missing patch payload",
                    },
                    ensure_ascii=False,
                ),
            )
            return
        async for item in handle_patch_gate(parsed, cancel_event, auto_apply=auto_apply):
            yield item
        return
    if kind == "shell":
        if not parsed.get("shell"):
            yield (
                {"type": "_result"},
                json.dumps(
                    {"status": "failed", "error": "propose_shell missing shell payload"},
                    ensure_ascii=False,
                ),
            )
            return
        async for item in handle_shell_gate(parsed, cancel_event, auto_apply=auto_apply):
            yield item
        return
    if kind == "memory":
        if not parsed.get("memory"):
            yield (
                {"type": "_result"},
                json.dumps(
                    {"status": "failed", "error": "propose_memory missing memory payload"},
                    ensure_ascii=False,
                ),
            )
            return
        async for item in handle_memory_gate(
            parsed,
            cancel_event,
            auto_apply=auto_apply,
            force_confirm_memory=force_confirm_memory,
        ):
            yield item
        return
    yield (
        {"type": "_result"},
        json.dumps(
            {"status": "failed", "error": "resolve_await_marker called without AWAIT_* marker"},
            ensure_ascii=False,
        ),
    )
