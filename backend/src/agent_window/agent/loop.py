"""Minimal agent loop: LLM ↔ tools (Hermes-inspired, slim)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_window.agent.tool_dispatch import handle_function_call
from agent_window.agent.observation import slim_tool_result
from agent_window.services.agent_settings import load_agent_settings
from agent_window.services.memory import MemoryStatus, decide_memory, wait_for_memory_decision
from agent_window.services.patches import PatchStatus, wait_for_decision
from agent_window.services.provider import provider
from agent_window.services.session_turns import TurnCancelled, race_with_cancel
from agent_window.services.shell import ShellStatus, shell_to_public, wait_for_shell_decision
from agent_window.tools.edit_tools import AWAIT_PATCH_KEY
from agent_window.tools.memory_tools import AWAIT_MEMORY_KEY
from agent_window.tools.registry import registry
from agent_window.tools.shell_tools import AWAIT_SHELL_KEY

logger = logging.getLogger(__name__)

# Fallback if settings missing; real cap comes from agent_settings.max_tool_iters.
DEFAULT_MAX_TOOL_ITERS = 24

_WRITE_CLAIM_RE = re.compile(
    r"("
    # Claim that THIS turn wrote to disk (avoid matching「刚才已创建」「已经存在」)
    r"已(经)?(成功)?(写入|保存到|写到)(磁盘|文件)?|"
    r"(?<!才)已创建(文件|目录)?|"
    r"(?<!才)已保存(文件|目录)?|"
    r"(?<!才)新建(了)?(文件|目录|测试)?|"
    r"(?<!才)创建(了)?(文件|目录|测试)(?!前)|"
    r"已成功(创建|修改|更新|运行|执行)|"
    r"(修改|编辑|提案)已应用|已应用到磁盘|写入磁盘成功|"
    r"当前状态：\s*已应用|"
    r"测试(全部)?通过|验证通过|"
    r"\d+\s*passed\b|"
    r"successfully\s+(wrote|saved|applied|created|ran)\b|"
    r"(file|files)\s+(has|have|was|were)\s+(been\s+)?(written|saved|applied|created)\b|"
    r"I\s+(have\s+)?(written|saved|applied|created|ran)\s+"
    r")",
    re.IGNORECASE,
)

_TOOLS_DISABLED_NOTE = (
    "⚠️ 本轮工具调用不可用（模型/网关拒绝 tools schema），已降级为纯文本。"
    "上述任何「已修改/已写入文件」类结论均不可信；请换支持工具的模型后重试。"
)

_UNVERIFIED_WRITE_NOTE = (
    "⚠️ 本轮未通过 propose_edit / propose_shell 审批执行；上述写盘/运行结论可能不实。"
    "如需改文件或跑命令，请明确要求并等待审批卡片。"
)

# Gate policy (Foundation F3, revised):
# - cancelled → stop turn
# - rejected / partial → user decision; end with template (do not auto-continue)
# - timeout / failed → continue_hint once; second time → template + end
_GATE_STOP_STATUSES = frozenset({"cancelled"})
_GATE_END_STATUSES = frozenset({"rejected", "partial"})
_GATE_RETRY_STATUSES = frozenset({"timeout", "failed"})
_GATE_SUCCESS_STATUSES = frozenset({"applied", "done"})
_GATE_TOOL_NAMES = frozenset({"propose_edit", "propose_delete", "propose_shell", "propose_memory"})

# Back-compat: statuses that used to force a template close (reject + retry-exhausted)
_GATE_TEMPLATE_STATUSES = _GATE_END_STATUSES | _GATE_RETRY_STATUSES
_GATE_CONTINUE_STATUSES = _GATE_RETRY_STATUSES  # only timeout/failed may soft-continue


def _gate_user_message(kind: str, parsed: Dict[str, Any], *, after_retry: bool = False) -> str:
    """Human-readable gate outcome (closing line or continue_hint body)."""
    status = str(parsed.get("status") or "")
    retry_prefix = "已自动换手段重试仍未成功。" if after_retry else ""
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


def _enrich_gate_result_for_continue(
    result: str,
    kind: str,
    parsed: Dict[str, Any],
    goal: Optional[str] = None,
) -> str:
    """One-shot continue hint for timeout/failed (not for user Reject)."""
    data = dict(parsed) if parsed else {}
    human = _gate_user_message(kind, data)
    goal_bit = f"本轮目标仍是：{goal}。" if (goal or "").strip() else ""
    data["continue_hint"] = (
        f"{human} {goal_bit}"
        "这是唯一一次自动续环：请立刻换手段重试一次，或向用户说明阻塞；"
        "若再次失败/超时，本轮将结束并告知用户。"
        "禁止仅用文字声称已完成写盘/执行。"
    )
    data["loop_continue"] = True
    return json.dumps(data, ensure_ascii=False)


def _gate_kind_from_result(parsed: Dict[str, Any]) -> Optional[str]:
    if parsed.get("shell_id") is not None:
        return "shell"
    if parsed.get("memory_id") is not None:
        return "memory"
    if parsed.get("patch_id") is not None:
        return "patch"
    return None


def _gate_kind_from_tool_name(name: str) -> str:
    if name == "propose_shell":
        return "shell"
    if name == "propose_memory":
        return "memory"
    return "patch"


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _looks_like_write_claim(text: str) -> bool:
    return bool(_WRITE_CLAIM_RE.search(text or ""))


def _append_note(content: str, note: str) -> str:
    body = (content or "").rstrip()
    if note in body:
        return body
    if not body:
        return note
    return f"{body}\n\n{note}"


async def _handle_patch_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    """Yields (sse_event, final_tool_result_or_None). Last yield has the result string."""
    patch = parsed["patch"]
    patch_id = patch["id"]
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
            "message": "User rejected the edit. If the user asks to retry or revise, call propose_edit or propose_delete again; do not reply with text only.",
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


async def _handle_shell_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    shell = parsed["shell"]
    shell_id = shell["id"]
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
            "message": "User rejected the command. If the user asks to retry or revise, call propose_shell again; do not reply with text only.",
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


async def _handle_memory_gate(
    parsed: Dict[str, Any],
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[tuple[Dict[str, Any], Optional[str]]]:
    memory = parsed["memory"]
    memory_id = memory["id"]
    yield (
        {
            "type": "memory",
            "memory_id": memory_id,
            "mode": memory.get("mode"),
            "preview": memory.get("preview"),
            "content": memory.get("content"),
            "status": "pending",
        },
        None,
    )

    agent_cfg = load_agent_settings()
    if not agent_cfg.get("confirm_memory", True):
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
            "preview": decided.preview,
            "content": decided.content,
            "status": decided.status.value,
            "error": decided.error,
        },
        None,
    )

    if decided.status == MemoryStatus.APPLIED:
        result = {"status": "applied", "memory_id": memory_id, "mode": decided.mode}
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


async def run_agent_loop(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
    goal: Optional[str] = None,
    previous_goal: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Yields SSE-oriented events:
      - turn_goal (when a Goal is active)
      - progress_checkpoint (interval or after gate return; reply when model narrates)
      - tool_start / tool_result
      - diff / shell / await_approval
      - tools_disabled / token / error / done
    """
    import agent_window.tools  # noqa: F401

    from agent_window.agent.goal import inject_goal_into_messages
    from agent_window.agent.checkpoint import (
        clip_checkpoint_reply,
        format_checkpoint_user_message,
        should_checkpoint,
    )
    from agent_window.agent.checkpoint import checkpoint_interval_from_settings

    agent_cfg = load_agent_settings()
    disabled_tools = set(agent_cfg.get("disabled_tools") or [])
    try:
        max_tool_iters = int(agent_cfg.get("max_tool_iters") or DEFAULT_MAX_TOOL_ITERS)
    except (TypeError, ValueError):
        max_tool_iters = DEFAULT_MAX_TOOL_ITERS
    max_tool_iters = max(8, min(64, max_tool_iters))
    checkpoint_every_n = checkpoint_interval_from_settings(
        agent_cfg.get("checkpoint_every_n_tools"),
    )
    tools = [
        t for t in registry.get_openai_tools()
        if t.get("function", {}).get("name") not in disabled_tools
    ]
    turn_goal = (goal or "").strip() or None
    prev_goal = (previous_goal or "").strip() or None
    working = list(messages)
    if turn_goal:
        working = inject_goal_into_messages(working, turn_goal)
        event: Dict[str, Any] = {"type": "turn_goal", "goal": turn_goal}
        if prev_goal and prev_goal != turn_goal:
            event["previous_goal"] = prev_goal
        yield event
    write_gate_seen = False
    shell_gate_seen = False
    # timeout/failed may soft-continue at most once per turn
    gate_retry_used = False
    tools_since_checkpoint = 0
    # After injecting a checkpoint user msg, capture the next model narration for UI.
    pending_checkpoint: Optional[Dict[str, Any]] = None

    for _ in range(max_tool_iters):
        if cancel_event is not None and cancel_event.is_set():
            yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
            return

        try:
            turn = await race_with_cancel(
                provider.chat_complete(working, tools=tools or None, model=model),
                cancel_event,
            )
        except TurnCancelled:
            yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
            return
        except Exception as e:
            logger.exception("chat_complete failed")
            yield {"type": "error", "code": "LLM_PROVIDER_ERROR", "message": str(e)}
            return

        tool_calls = turn.get("tool_calls") or []
        content = (turn.get("content") or "").strip()
        tools_fallback = bool(turn.get("tools_fallback"))

        # Mid-loop checkpoint reply: model wrote progress then continues with tools.
        # Final-only / tools-without-narration: settle so UI leaves "等待说明".
        if pending_checkpoint is not None:
            reply = clip_checkpoint_reply(content) if content and tool_calls else ""
            event: Dict[str, Any] = {
                "type": "progress_checkpoint",
                "goal": pending_checkpoint.get("goal"),
                "tools_since_last": pending_checkpoint.get("tools_since_last"),
                "reason": pending_checkpoint.get("reason"),
            }
            if reply:
                event["reply"] = reply
            else:
                # Model skipped narration (tools-only or final answer) — do not keep UI waiting.
                event["settled"] = True
            yield event
            pending_checkpoint = None

        if tools_fallback:
            reason = turn.get("tools_fallback_reason") or "provider rejected tools schema"
            yield {
                "type": "tools_disabled",
                "message": "当前模型不支持工具调用，已降级为纯文本；无法 propose_edit / shell / memory。",
                "reason": reason,
            }

        if tool_calls:
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                            if isinstance(tc["arguments"], str)
                            else json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            }
            working.append(assistant_msg)

            gate_returned_this_batch = False
            batch_tool_count = 0

            for tc in tool_calls:
                if cancel_event is not None and cancel_event.is_set():
                    yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
                    return

                name = tc["name"]
                raw_args = tc["arguments"]
                yield {
                    "type": "tool_start",
                    "name": name,
                    "arguments": raw_args,
                    "tool_call_id": tc["id"],
                }
                result = await handle_function_call(name, raw_args)

                parsed = _try_parse_json(result)
                if parsed and parsed.get(AWAIT_PATCH_KEY):
                    write_gate_seen = True
                    if not parsed.get("patch"):
                        result = json.dumps(
                            {"status": "failed", "error": "propose_edit/propose_delete missing patch payload"},
                            ensure_ascii=False,
                        )
                    else:
                        async for event, maybe_result in _handle_patch_gate(parsed, cancel_event):
                            if event.get("type") == "_result":
                                result = maybe_result or result
                            else:
                                yield event
                elif parsed and parsed.get(AWAIT_SHELL_KEY):
                    shell_gate_seen = True
                    if not parsed.get("shell"):
                        result = json.dumps(
                            {"status": "failed", "error": "propose_shell missing shell payload"},
                            ensure_ascii=False,
                        )
                    else:
                        async for event, maybe_result in _handle_shell_gate(parsed, cancel_event):
                            if event.get("type") == "_result":
                                result = maybe_result or result
                            else:
                                yield event
                elif parsed and parsed.get(AWAIT_MEMORY_KEY):
                    if not parsed.get("memory"):
                        result = json.dumps(
                            {"status": "failed", "error": "propose_memory missing memory payload"},
                            ensure_ascii=False,
                        )
                    else:
                        async for event, maybe_result in _handle_memory_gate(parsed, cancel_event):
                            if event.get("type") == "_result":
                                result = maybe_result or result
                            else:
                                yield event

                # Never feed raw "await approval" markers back to the model.
                parsed_result = _try_parse_json(result or "")
                if parsed_result and (
                    parsed_result.get(AWAIT_PATCH_KEY)
                    or parsed_result.get(AWAIT_SHELL_KEY)
                    or parsed_result.get(AWAIT_MEMORY_KEY)
                ):
                    result = json.dumps(
                        {
                            "status": "failed",
                            "error": "approval gate did not complete; edit/command was not applied",
                        },
                        ensure_ascii=False,
                    )
                    parsed_result = _try_parse_json(result)

                status = (parsed_result or {}).get("status") if parsed_result else None
                gate_kind = _gate_kind_from_result(parsed_result or {}) or (
                    _gate_kind_from_tool_name(name) if name in _GATE_TOOL_NAMES else None
                )
                gate_handled = bool(
                    parsed
                    and (
                        parsed.get(AWAIT_PATCH_KEY)
                        or parsed.get(AWAIT_SHELL_KEY)
                        or parsed.get(AWAIT_MEMORY_KEY)
                    )
                ) or name in _GATE_TOOL_NAMES

                # Stop when the turn was cancelled.
                if (
                    (cancel_event is not None and cancel_event.is_set())
                    or status in _GATE_STOP_STATUSES
                ):
                    yield {
                        "type": "tool_result",
                        "name": name,
                        "content": result,
                        "tool_call_id": tc["id"],
                    }
                    yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
                    return

                kind = gate_kind or (
                    _gate_kind_from_tool_name(name) if name in _GATE_TOOL_NAMES else "patch"
                )
                is_gate_outcome = gate_handled or (
                    name in _GATE_TOOL_NAMES
                    and status
                    and status not in _GATE_SUCCESS_STATUSES
                    and status not in _GATE_STOP_STATUSES
                )

                # User Reject / partial apply: end this turn with a clear template.
                if is_gate_outcome and status in _GATE_END_STATUSES:
                    yield {
                        "type": "tool_result",
                        "name": name,
                        "content": result,
                        "tool_call_id": tc["id"],
                    }
                    msg = _gate_user_message(kind, parsed_result or {"status": status})
                    yield {"type": "token", "content": msg}
                    yield {"type": "done"}
                    return

                # timeout / failed: one soft continue, then end and tell the user.
                if is_gate_outcome and status in _GATE_RETRY_STATUSES:
                    if gate_retry_used:
                        yield {
                            "type": "tool_result",
                            "name": name,
                            "content": result,
                            "tool_call_id": tc["id"],
                        }
                        msg = _gate_user_message(
                            kind,
                            parsed_result or {"status": status},
                            after_retry=True,
                        )
                        yield {"type": "token", "content": msg}
                        yield {"type": "done"}
                        return

                    result = _enrich_gate_result_for_continue(
                        result,
                        kind,
                        parsed_result or {"status": status},
                        goal=turn_goal,
                    )
                    gate_retry_used = True
                    gate_returned_this_batch = True
                    yield {
                        "type": "tool_result",
                        "name": name,
                        "content": result,
                        "tool_call_id": tc["id"],
                        "loop_continue": True,
                    }
                    working.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": slim_tool_result(name, result),
                        }
                    )
                    batch_tool_count += 1
                    continue

                yield {
                    "type": "tool_result",
                    "name": name,
                    "content": result,
                    "tool_call_id": tc["id"],
                }

                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": slim_tool_result(name, result),
                    }
                )
                batch_tool_count += 1
                if gate_handled and status in _GATE_SUCCESS_STATUSES:
                    gate_returned_this_batch = True

            tools_since_checkpoint += batch_tool_count
            checkpoint_reason = should_checkpoint(
                tools_since_checkpoint,
                gate_returned_this_batch,
                checkpoint_every_n,
            )
            if checkpoint_reason:
                checkpoint_msg = format_checkpoint_user_message(turn_goal)
                working.append({"role": "user", "content": checkpoint_msg})
                pending_checkpoint = {
                    "goal": turn_goal,
                    "tools_since_last": tools_since_checkpoint,
                    "reason": checkpoint_reason,
                }
                yield {
                    "type": "progress_checkpoint",
                    "goal": turn_goal,
                    "tools_since_last": tools_since_checkpoint,
                    "reason": checkpoint_reason,
                }
                tools_since_checkpoint = 0
            continue

        if tools_fallback:
            if not content:
                content = _TOOLS_DISABLED_NOTE
            elif _looks_like_write_claim(content):
                content = _append_note(content, _TOOLS_DISABLED_NOTE)
            else:
                content = _append_note(
                    content,
                    "⚠️ 本轮工具调用不可用，无法改文件或执行命令；请换支持工具的模型。",
                )
        elif content and _looks_like_write_claim(content) and not write_gate_seen and not shell_gate_seen:
            content = _append_note(content, _UNVERIFIED_WRITE_NOTE)

        if not content:
            yield {
                "type": "error",
                "code": "EMPTY_RESPONSE",
                "message": "模型返回为空，请重试",
            }
            return

        yield {"type": "token", "content": content}
        yield {"type": "done"}
        return

    # Soft land: one final answer without tools so the user still gets a result.
    goal_line = f"本轮目标：{turn_goal}。" if turn_goal else ""
    working.append(
        {
            "role": "user",
            "content": (
                f"工具调用已达上限（{max_tool_iters} 轮）。{goal_line}"
                "请基于以上已有工具结果，直接对照目标给出当前结论、已完成事项与未完成事项；"
                "不要再调用任何工具。"
            ),
        }
    )
    try:
        turn = await race_with_cancel(
            provider.chat_complete(working, tools=None, model=model),
            cancel_event,
        )
    except TurnCancelled:
        yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
        return
    except Exception as e:
        logger.exception("soft-land chat_complete failed after tool loop limit")
        yield {
            "type": "error",
            "code": "TOOL_LOOP_LIMIT",
            "message": f"工具调用超过 {max_tool_iters} 轮，已中止（总结失败：{e}）",
        }
        return

    content = (turn.get("content") or "").strip()
    if content:
        note = f"\n\n⚠️ 工具调用已达上限（{max_tool_iters} 轮），以上为基于已有结果的总结。"
        if turn_goal:
            note += f"\n目标：{turn_goal}"
        yield {"type": "token", "content": content + note}
        yield {"type": "done"}
        return

    yield {
        "type": "error",
        "code": "TOOL_LOOP_LIMIT",
        "message": f"工具调用超过 {max_tool_iters} 轮，已中止",
    }


