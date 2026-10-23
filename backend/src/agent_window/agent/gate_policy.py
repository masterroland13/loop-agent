"""Gate policy (Foundation F3) — Reject ends; timeout/failed soft-continue once.

Extracted from ``loop.py`` so Preset/gate outcomes live in one module and
``_run_one_turn`` delegates instead of inlining policy branches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

# Gate policy (Foundation F3, revised):
# - cancelled → stop turn
# - rejected / partial → user decision; end with template (do not auto-continue)
# - timeout / failed → continue_hint once; second time → template + end
GATE_STOP_STATUSES = frozenset({"cancelled"})
GATE_END_STATUSES = frozenset({"rejected", "partial", "blocked"})
GATE_RETRY_STATUSES = frozenset({"timeout", "failed"})
GATE_SUCCESS_STATUSES = frozenset({"applied", "done"})
GATE_TOOL_NAMES = frozenset({"propose_edit", "propose_delete", "propose_shell", "propose_memory"})
GATE_CONTINUE_STATUSES = GATE_RETRY_STATUSES

# Back-compat aliases for tests / callers that imported private names from loop.
_GATE_STOP_STATUSES = GATE_STOP_STATUSES
_GATE_END_STATUSES = GATE_END_STATUSES
_GATE_RETRY_STATUSES = GATE_RETRY_STATUSES
_GATE_SUCCESS_STATUSES = GATE_SUCCESS_STATUSES
_GATE_CONTINUE_STATUSES = GATE_RETRY_STATUSES
_GATE_TEMPLATE_STATUSES = GATE_END_STATUSES | GATE_RETRY_STATUSES
_GATE_TOOL_NAMES = GATE_TOOL_NAMES


class GateAction(str, Enum):
    """What the loop should do after a gate tool resolves."""

    STOP_CANCELLED = "stop_cancelled"
    END_TURN = "end_turn"
    CONTINUE_LOOP = "continue_loop"
    APPEND = "append"


@dataclass(frozen=True)
class GateResolution:
    action: GateAction
    result: str
    user_message: Optional[str] = None
    loop_continue: bool = False
    mark_gate_retry_used: bool = False
    mark_gate_returned: bool = False


def gate_user_message(kind: str, parsed: Dict[str, Any], *, after_retry: bool = False) -> str:
    """Human-readable gate outcome (closing line or continue_hint body)."""
    status = str(parsed.get("status") or "")
    retry_prefix = "已自动换手段重试仍未成功。" if after_retry else ""
    if status == "blocked":
        return str(parsed.get("error") or "操作被策略拦截，未执行。")
    if kind == "patch":
        path = parsed.get("path") or "该文件"
        if status == "partial":
            applied = parsed.get("applied_hunks") or []
            return (
                f"已部分应用 `{path}`：写入 {len(applied)} 个选中块，其余改动未写入。"
                "需要剩余改动请直接说「把剩下的也改了」。"
            )
        if status == "rejected":
            return (
                f"已拒绝修改 `{path}`，未写入磁盘。"
                "若要换方案，请再说一次要怎么改。"
            )
        if status == "timeout":
            return (
                f"{retry_prefix}审批超时，`{path}` 未写入。"
                "需要的话请再说一次修改请求。"
            )
        return (
            f"{retry_prefix}修改 `{path}` 失败：{parsed.get('error') or '未知错误'}。"
            "可以说明新的改法后重试。"
        )
    if kind == "shell":
        cmd = parsed.get("command") or "该命令"
        if status == "rejected":
            return (
                f"已拒绝执行 `{cmd}`。"
                "若要换命令，请直接给出新命令。"
            )
        if status == "timeout":
            return f"{retry_prefix}命令审批/执行超时：`{cmd}`。需要的话请重试。"
        return (
            f"{retry_prefix}命令失败：`{cmd}` — {parsed.get('error') or '未知错误'}。"
        )
    # memory
    if status == "rejected":
        return "已拒绝写入记忆。若仍要保存，请再说一次要记住的内容。"
    if status == "timeout":
        return f"{retry_prefix}记忆审批超时，未写入。需要的话请重试。"
    return f"{retry_prefix}记忆写入失败：{parsed.get('error') or '未知错误'}。"


# Back-compat alias
_gate_user_message = gate_user_message


def enrich_gate_result_for_continue(
    result: str,
    kind: str,
    parsed: Dict[str, Any],
    goal: Optional[str] = None,
) -> str:
    """One-shot continue hint for timeout/failed (not for user Reject)."""
    data = dict(parsed) if parsed else {}
    human = gate_user_message(kind, data)
    goal_bit = f"本轮目标仍是：{goal}。" if (goal or "").strip() else ""
    data["continue_hint"] = (
        f"{human} {goal_bit}"
        "这是唯一一次自动续环：请立刻换手段重试一次，或向用户说明阻塞；"
        "若再次失败/超时，本轮将结束并告知用户。"
        "禁止仅用文字声称已完成写盘/执行。"
    )
    data["loop_continue"] = True
    return json.dumps(data, ensure_ascii=False)


# Back-compat alias
_enrich_gate_result_for_continue = enrich_gate_result_for_continue


def gate_kind_from_result(parsed: Dict[str, Any]) -> Optional[str]:
    if parsed.get("shell_id") is not None:
        return "shell"
    if parsed.get("memory_id") is not None:
        return "memory"
    if parsed.get("patch_id") is not None:
        return "patch"
    return None


def gate_kind_from_tool_name(name: str) -> str:
    if name == "propose_shell":
        return "shell"
    if name == "propose_memory":
        return "memory"
    return "patch"


def resolve_gate_outcome(
    *,
    tool_name: str,
    result: str,
    parsed_result: Optional[Dict[str, Any]],
    status: Optional[str],
    gate_handled: bool,
    gate_retry_used: bool,
    turn_goal: Optional[str],
    cancel_event_set: bool,
) -> GateResolution:
    """Map a post-gate tool result to loop action (F3)."""
    gate_kind = gate_kind_from_result(parsed_result or {}) or (
        gate_kind_from_tool_name(tool_name) if tool_name in GATE_TOOL_NAMES else None
    )
    is_gate_outcome = gate_handled or (
        tool_name in GATE_TOOL_NAMES
        and status
        and status not in GATE_SUCCESS_STATUSES
        and status not in GATE_STOP_STATUSES
    )
    kind = gate_kind or (
        gate_kind_from_tool_name(tool_name) if tool_name in GATE_TOOL_NAMES else "patch"
    )

    if cancel_event_set or status in GATE_STOP_STATUSES:
        return GateResolution(action=GateAction.STOP_CANCELLED, result=result)

    if is_gate_outcome and status in GATE_END_STATUSES:
        msg = gate_user_message(kind, parsed_result or {"status": status})
        return GateResolution(
            action=GateAction.END_TURN,
            result=result,
            user_message=msg,
        )

    if is_gate_outcome and status in GATE_RETRY_STATUSES:
        if gate_retry_used:
            msg = gate_user_message(
                kind,
                parsed_result or {"status": status},
                after_retry=True,
            )
            return GateResolution(
                action=GateAction.END_TURN,
                result=result,
                user_message=msg,
            )
        enriched = enrich_gate_result_for_continue(
            result,
            kind,
            parsed_result or {"status": status},
            goal=turn_goal,
        )
        return GateResolution(
            action=GateAction.CONTINUE_LOOP,
            result=enriched,
            loop_continue=True,
            mark_gate_retry_used=True,
            mark_gate_returned=True,
        )

    mark_returned = bool(gate_handled and status in GATE_SUCCESS_STATUSES)
    return GateResolution(
        action=GateAction.APPEND,
        result=result,
        mark_gate_returned=mark_returned,
    )
