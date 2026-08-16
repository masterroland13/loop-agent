"""Minimal agent loop: LLM ↔ tools (Hermes-inspired, slim)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_window.agent.tool_dispatch import handle_function_call
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

MAX_TOOL_ITERS = 8

_WRITE_CLAIM_RE = re.compile(
    r"("
    # Claim that THIS turn wrote to disk (avoid matching「刚才已创建」「已经存在」)
    r"已(经)?(成功)?(写入|保存到|写到)(磁盘|文件)?|"
    r"(?<!才)已创建(文件|目录)|"
    r"(?<!才)已保存(文件|目录)|"
    r"已成功(创建|修改|更新)|"
    r"(修改|编辑|提案)已应用|已应用到磁盘|写入磁盘成功|"
    r"当前状态：\s*已应用|"
    r"successfully\s+(wrote|saved|applied)\b|"
    r"(file|files)\s+(has|have|was|were)\s+(been\s+)?(written|saved|applied)\b|"
    r"I\s+(have\s+)?(written|saved|applied)\s+"
    r")",
    re.IGNORECASE,
)

_TOOLS_DISABLED_NOTE = (
    "⚠️ 本轮工具调用不可用（模型/网关拒绝 tools schema），已降级为纯文本。"
    "上述任何「已修改/已写入文件」类结论均不可信；请换支持工具的模型后重试。"
)

_UNVERIFIED_WRITE_NOTE = (
    "⚠️ 本轮未通过 propose_edit 审批写入磁盘；上述写盘结论可能不实。"
    "如需改文件，请明确要求并等待 Diff 面板 Apply。"
)

# After an approval gate, these statuses must NOT trigger another free-form LLM turn.
_GATE_STOP_STATUSES = frozenset({"cancelled"})
_GATE_TEMPLATE_STATUSES = frozenset({"rejected", "timeout", "failed", "partial"})
_GATE_SUCCESS_STATUSES = frozenset({"applied", "done"})
_GATE_TOOL_NAMES = frozenset({"propose_edit", "propose_shell", "propose_memory"})


def _gate_user_message(kind: str, parsed: Dict[str, Any]) -> str:
    """Fixed Chinese closing line — avoids model essays after Reject/timeout/fail."""
    status = str(parsed.get("status") or "")
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
                "是否继续执行？直接回复「继续改」或说明新的改法即可。"
            )
        if status == "timeout":
            return f"审批超时，`{path}` 未写入。需要的话请再说一次修改请求。"
        return f"修改 `{path}` 失败：{parsed.get('error') or '未知错误'}。可以重试或换一种改法。"
    if kind == "shell":
        cmd = parsed.get("command") or "该命令"
        if status == "rejected":
            return (
                f"已拒绝执行 `{cmd}`。"
                "是否继续执行？直接回复「继续执行」或给出新命令即可。"
            )
        if status == "timeout":
            return f"命令审批/执行超时：`{cmd}`。需要的话请重试。"
        return f"命令失败：`{cmd}` — {parsed.get('error') or '未知错误'}。"
    # memory
    if status == "rejected":
        return "已拒绝写入记忆。是否仍要保存？请再说一次要记住的内容。"
    if status == "timeout":
        return "记忆审批超时，未写入。需要的话请重试。"
    return f"记忆写入失败：{parsed.get('error') or '未知错误'}。"


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
            "message": "User rejected the edit. If the user asks to retry or revise, call propose_edit again; do not reply with text only.",
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
) -> AsyncIterator[Dict[str, Any]]:
    """
    Yields SSE-oriented events:
      - tool_start / tool_result
      - diff / shell / await_approval
      - tools_disabled / token / error / done
    """
    import agent_window.tools  # noqa: F401

    tools = registry.get_openai_tools()
    working = list(messages)
    write_gate_seen = False

    for _ in range(MAX_TOOL_ITERS):
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
                            {"status": "failed", "error": "propose_edit missing patch payload"},
                            ensure_ascii=False,
                        )
                    else:
                        async for event, maybe_result in _handle_patch_gate(parsed, cancel_event):
                            if event.get("type") == "_result":
                                result = maybe_result or result
                            else:
                                yield event
                elif parsed and parsed.get(AWAIT_SHELL_KEY):
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

                yield {
                    "type": "tool_result",
                    "name": name,
                    "content": result,
                    "tool_call_id": tc["id"],
                }

                # Stop: never let the model write a free-form closing essay.
                if (
                    (cancel_event is not None and cancel_event.is_set())
                    or status in _GATE_STOP_STATUSES
                ):
                    yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
                    return

                # Reject / timeout / fail after an approval gate: fixed template only.
                if gate_handled and status in _GATE_TEMPLATE_STATUSES:
                    msg = _gate_user_message(gate_kind or "patch", parsed_result or {})
                    yield {"type": "token", "content": msg}
                    yield {"type": "done"}
                    return

                # Safety net: approval tools that did not succeed must not continue the LLM.
                if (
                    name in _GATE_TOOL_NAMES
                    and status
                    and status not in _GATE_SUCCESS_STATUSES
                    and status not in _GATE_STOP_STATUSES
                ):
                    msg = _gate_user_message(gate_kind or _gate_kind_from_tool_name(name), parsed_result or {"status": status})
                    yield {"type": "token", "content": msg}
                    yield {"type": "done"}
                    return

                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )
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
        elif content and _looks_like_write_claim(content) and not write_gate_seen:
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

    yield {
        "type": "error",
        "code": "TOOL_LOOP_LIMIT",
        "message": f"工具调用超过 {MAX_TOOL_ITERS} 轮，已中止",
    }
