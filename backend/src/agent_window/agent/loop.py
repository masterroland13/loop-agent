"""Minimal agent loop: LLM ↔ tools (Hermes-inspired, slim)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_window.agent.gate_policy import (
    GateAction,
    resolve_gate_outcome,
)
from agent_window.agent.loop_exit import (
    EMPTY_RESPONSE_MESSAGE,
    format_missing_edit_nudge,
    should_nudge_missing_edit,
    synthesize_tools_only_reply,
    working_requests_repo_edit,
)
from agent_window.agent.tool_dispatch import handle_function_call
from agent_window.agent.tool_pipeline import run_tool_steps
from agent_window.core.event_sink import EventSink
from agent_window.core.loop_config import LoopConfig
from agent_window.core.tool_hooks import exploration_note_after_tool, observe_for_working
from agent_window.core.steering import drain_steering, format_steering_content
from agent_window.core.turn import AgentLoopState, TurnOutcome
from agent_window.services.agent_settings import load_agent_settings
from agent_window.services.context_transform import apply_transform_context
from agent_window.services.provider import provider
from agent_window.services.session_turns import TurnCancelled, race_with_cancel
from agent_window.tools.registry import registry

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

# A quoted or forbidden example is not a claim that this turn wrote anything.
# 「不会声称「测试通过」」must not trip the unverified-write banner.
_CLAIM_NEGATION_RE = re.compile(
    r"(?:不要|不会|不能|不可|禁止|并未|并没有|没有|尚未|(?<![区类识])别)"
    r"(?:再)?"
    r"(?:声称|说|写成)?"
    r"[^。\n，,；;]{0,24}$"
)

_TOOLS_DISABLED_NOTE = (
    "⚠️ 本轮工具调用不可用（模型/网关拒绝 tools schema），已降级为纯文本。"
    "上述任何「已修改/已写入文件」类结论均不可信；请换支持工具的模型后重试。"
)

_UNVERIFIED_WRITE_NOTE = (
    "⚠️ 本轮未通过 propose_edit / propose_shell 审批执行；上述写盘/运行结论可能不实。"
    "如需改文件或跑命令，请明确要求并等待审批卡片。"
)

_MAX_TOKENS_TRUNCATED_NOTE = (
    "⚠️ 本轮回复因达到 max_tokens（单次回复最大长度）上限被截断，未写完。"
    "可在 Settings 提高该上限后重试，或让我分段续写。这与上下文压缩无关。"
)


def soft_land_user_prompt(*, max_tool_iters: int, turn_goal: Optional[str]) -> str:
    """Force an honest mid-task wrap-up — not a fake 'done' report."""
    goal_line = f"\n本轮目标：{turn_goal.strip()}" if turn_goal and turn_goal.strip() else ""
    return (
        f"工具调用已达上限（{max_tool_iters} 轮），任务尚未结束，这是强制软着陆。{goal_line}\n"
        "请严格按下面三个小节输出（标题原样保留），基于**已有工具结果**据实说明；"
        "不要再调用任何工具。\n\n"
        "## 已完成\n"
        "## 未完成 / 阻塞\n"
        "## 建议下一步\n\n"
        "硬性要求：\n"
        "- 不要声称「已全部完成 / 审查完毕 / 可以收工 / 任务结束」，除非已有结果充分证明；\n"
        "- 若证据不足，必须把缺口写进「未完成 / 阻塞」；\n"
        "- 语气是阶段性汇报，不是结案陈词。"
    )


def soft_land_banner(*, max_tool_iters: int, tools_ran: int, turn_goal: Optional[str]) -> str:
    """Leading notice prepended to the soft-land reply (UI + transcript)."""
    lines = [
        f"⚠️ 工具轮次已用尽（上限 {max_tool_iters}，本轮约执行 {tools_ran} 次工具），"
        "以下为**提前收口**的阶段性说明，**不代表任务已完成**。",
    ]
    if turn_goal and turn_goal.strip():
        lines.append(f"目标：{turn_goal.strip()}")
    return "\n".join(lines)


def synthesize_soft_land_reply(
    *,
    max_tool_iters: int,
    tools_ran: int,
    turn_goal: Optional[str],
    write_gate_seen: bool = False,
    edit_intent: bool = False,
) -> str:
    """Deterministic fallback when the model returns empty on soft-land."""
    banner = soft_land_banner(
        max_tool_iters=max_tool_iters,
        tools_ran=tools_ran,
        turn_goal=turn_goal,
    )
    goal_bit = f"\n对照目标：{turn_goal.strip()}" if turn_goal and turn_goal.strip() else ""
    unfinished = f"在 {max_tool_iters} 轮工具上限内未能收工。{goal_bit}"
    if edit_intent and not write_gate_seen:
        unfinished += (
            "\n本轮**从未**调用 propose_edit / propose_delete，仓库文件未改。"
        )
    return (
        f"{banner}\n\n"
        "## 已完成\n"
        "（模型未给出文字总结；请查看上方工具轨迹。）\n\n"
        "## 未完成 / 阻塞\n"
        f"{unfinished}\n\n"
        "## 建议下一步\n"
        "可在设置中提高「最大工具轮次」后重试，或缩小范围后再发一条续跑指令。"
    )


def _extract_markdown_section(text: str, heading: str) -> str:
    """Return body under `## heading` until the next `## ` or EOF."""
    if not text:
        return ""
    marker = heading if heading.startswith("## ") else f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    body_start = start + len(marker)
    # skip heading line break
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    rest = text[body_start:]
    next_h = rest.find("\n## ")
    body = rest if next_h < 0 else rest[:next_h]
    return body.strip()


def soft_land_continue_user_message(
    *,
    turn_goal: Optional[str] = None,
    soft_land_reply: str = "",
) -> str:
    """User message sent when clicking Continue after a soft-land wrap-up.

    Carries goal + unfinished/next-step excerpts so the next turn resumes
    instead of a bare 「继续」 that drops mid-task context.
    """
    unfinished = _extract_markdown_section(soft_land_reply, "## 未完成 / 阻塞")
    next_steps = _extract_markdown_section(soft_land_reply, "## 建议下一步")
    lines = [
        "请从上一轮软着陆处继续推进，不要重复已经完成的工作；直接调用工具接着干。",
    ]
    goal = (turn_goal or "").strip()
    if goal:
        lines.append(f"本轮目标：{goal}")
    lines.append("")
    lines.append("对照上轮收口：")
    lines.append("### 未完成 / 阻塞")
    lines.append(unfinished or "（上轮未写明；请根据工具轨迹与对话自行判断缺口。）")
    lines.append("")
    lines.append("### 建议下一步")
    lines.append(next_steps or "（上轮未写明；优先消除阻塞，再对照目标推进。）")
    lines.append("")
    lines.append(
        "要求：优先处理未完成项；证据不足时据实说明；"
        "仍受本会话「最大工具轮次」限制，触顶可再次软着陆。"
    )
    return "\n".join(lines)


# F3 gate policy → agent/gate_policy.py (re-export for legacy imports)
from agent_window.agent.gate_policy import (  # noqa: E402
    GATE_END_STATUSES as _GATE_END_STATUSES,
    GATE_RETRY_STATUSES as _GATE_RETRY_STATUSES,
    GATE_STOP_STATUSES as _GATE_STOP_STATUSES,
    GATE_SUCCESS_STATUSES as _GATE_SUCCESS_STATUSES,
    GATE_TOOL_NAMES as _GATE_TOOL_NAMES,
    GATE_RETRY_STATUSES as _GATE_CONTINUE_STATUSES,
    enrich_gate_result_for_continue as _enrich_gate_result_for_continue,
    gate_user_message as _gate_user_message,
)


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _observe_tool(config: LoopConfig, name: str, result: str):
    """F4: slim for working[] + optional data_path spill via config.extra."""
    return observe_for_working(name, result, config=config)


def _tool_result_sse(
    name: str,
    result: str,
    tool_call_id: str,
    obs,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "type": "tool_result",
        "name": name,
        "content": result,
        "tool_call_id": tool_call_id,
    }
    if obs.truncated:
        event["truncated"] = True
        event["summary"] = obs.display_summary
    if obs.full_ref:
        event["full_ref"] = obs.full_ref
    if extra:
        event.update(extra)
    return event


def _answered_tool_call_ids(messages: List[Dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for m in messages:
        if m.get("role") != "tool":
            continue
        tid = m.get("tool_call_id")
        if isinstance(tid, str) and tid:
            out.add(tid)
    return out


def _append_missing_tool_results(
    messages: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    *,
    answered: Optional[Dict[str, str]] = None,
    stub_content: str = '{"status":"skipped","error":"tool result omitted"}',
) -> None:
    """Ensure every tool_call_id has a following tool message (provider API requirement)."""
    answered = dict(answered or {})
    already = _answered_tool_call_ids(messages)
    for tc in tool_calls:
        tid = tc.get("id")
        if not isinstance(tid, str) or not tid or tid in already:
            continue
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tid,
                "content": answered.get(tid, stub_content),
            }
        )
        already.add(tid)


def _claim_is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 48) : start]
    return bool(_CLAIM_NEGATION_RE.search(window))


def _looks_like_write_claim(text: str) -> bool:
    """True when the reply asserts a write or a passing run, not when it only mentions the rule."""
    for match in _WRITE_CLAIM_RE.finditer(text or ""):
        if _claim_is_negated(text or "", match.start()):
            continue
        return True
    return False


def _append_note(content: str, note: str) -> str:
    body = (content or "").rstrip()
    if note in body:
        return body
    if not body:
        return note
    return f"{body}\n\n{note}"


async def _run_one_turn(
    state: AgentLoopState,
    *,
    tools: List[Dict[str, Any]],
    model: Optional[str],
    cancel_event: Optional[asyncio.Event],
    config: LoopConfig,
) -> AsyncIterator[Dict[str, Any]]:
    """One LLM completion + optional tool batch. Sets ``state.outcome`` before returning."""
    from agent_window.agent.checkpoint import clip_checkpoint_reply

    working = state.working
    turn_goal = state.turn_goal

    def _note_exploration_tool(tool_name: str) -> Optional[Dict[str, Any]]:
        return exploration_note_after_tool(config, state, tool_name)

    try:
        working, _compressed, _meta = await apply_transform_context(
            config, working, preserve_goal=turn_goal
        )
        state.working = working
        turn = await race_with_cancel(
            provider.chat_complete(working, tools=tools or None, model=model),
            cancel_event,
        )
    except TurnCancelled:
        yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
        state.outcome = TurnOutcome.STOP
        return
    except Exception as e:
        logger.exception("chat_complete failed")
        yield {"type": "error", "code": "LLM_PROVIDER_ERROR", "message": str(e)}
        state.outcome = TurnOutcome.STOP
        return

    tool_calls = turn.get("tool_calls") or []
    content = (turn.get("content") or "").strip()
    tools_fallback = bool(turn.get("tools_fallback"))
    finish_reason = (turn.get("finish_reason") or "").strip().lower()
    reasoning = (turn.get("reasoning_content") or "").strip()
    reasoning_source = turn.get("reasoning_source") or "reasoning"
    reasoning_ms = turn.get("reasoning_duration_ms")

    # Thought before tools / final tokens — never invent when empty.
    if reasoning:
        yield {
            "type": "thought",
            "phase": "end",
            "text": reasoning,
            "duration_ms": reasoning_ms,
            "source": reasoning_source,
        }

    # Mid-loop checkpoint reply: model wrote progress then continues with tools.
    # Final-only / tools-without-narration: settle so UI leaves "等待说明".
    if state.pending_checkpoint is not None:
        reply = clip_checkpoint_reply(content) if content and tool_calls else ""
        event: Dict[str, Any] = {
            "type": "progress_checkpoint",
            "goal": state.pending_checkpoint.get("goal"),
            "tools_since_last": state.pending_checkpoint.get("tools_since_last"),
            "reason": state.pending_checkpoint.get("reason"),
        }
        if reply:
            event["reply"] = reply
        else:
            # Model skipped narration (tools-only or final answer) — do not keep UI waiting.
            event["settled"] = True
        yield event
        state.pending_checkpoint = None

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
        # Echo reasoning for gateways that require it on subsequent turns.
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        working.append(assistant_msg)

        gate_returned_this_batch = False
        batch_tool_count = 0
        pending_exploration_converge: Optional[Dict[str, Any]] = None

        for tc in tool_calls:
            if cancel_event is not None and cancel_event.is_set():
                _append_missing_tool_results(
                    working,
                    tool_calls,
                    stub_content='{"status":"cancelled","error":"turn cancelled before tool completed"}',
                )
                yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
                state.outcome = TurnOutcome.STOP
                return

            name = tc["name"]
            raw_args = tc["arguments"]
            if name == "propose_memory":
                # Any memory attempt (incl. DUPLICATE before/without settle) counts.
                state.memory_gate_seen = True
            yield {
                "type": "tool_start",
                "name": name,
                "arguments": raw_args,
                "tool_call_id": tc["id"],
            }
            result = None
            gate_kind = None
            async for step_ev in run_tool_steps(
                name,
                raw_args,
                config=config,
                cancel_event=cancel_event,
            ):
                etype = step_ev.get("type")
                if etype == "_tool_result":
                    result = step_ev.get("content")
                elif etype == "_gate_meta":
                    gate_kind = step_ev.get("kind")
                    if gate_kind == "patch":
                        state.write_gate_seen = True
                    elif gate_kind == "shell":
                        state.shell_gate_seen = True
                    elif gate_kind == "memory":
                        state.memory_gate_seen = True
                else:
                    yield step_ev
            if result is None:
                result = json.dumps(
                    {"status": "failed", "error": "tool pipeline produced no result"},
                    ensure_ascii=False,
                )

            parsed_result = _try_parse_json(result or "")
            status = (parsed_result or {}).get("status") if parsed_result else None
            gate_handled = gate_kind is not None or name in _GATE_TOOL_NAMES

            resolution = resolve_gate_outcome(
                tool_name=name,
                result=result,
                parsed_result=parsed_result,
                status=status,
                gate_handled=gate_handled,
                gate_retry_used=state.gate_retry_used,
                turn_goal=turn_goal,
                cancel_event_set=cancel_event is not None and cancel_event.is_set(),
            )
            result = resolution.result

            if resolution.action is GateAction.STOP_CANCELLED:
                obs = _observe_tool(config, name, result)
                _append_missing_tool_results(
                    working,
                    tool_calls,
                    answered={tc["id"]: obs.model_payload},
                    stub_content='{"status":"cancelled","error":"turn cancelled before tool completed"}',
                )
                yield _tool_result_sse(name, result, tc["id"], obs)
                yield {"type": "error", "code": "TURN_CANCELLED", "message": "已停止"}
                state.outcome = TurnOutcome.STOP
                return

            if resolution.action is GateAction.END_TURN:
                obs = _observe_tool(config, name, result)
                _append_missing_tool_results(
                    working,
                    tool_calls,
                    answered={tc["id"]: obs.model_payload},
                    stub_content='{"status":"skipped","error":"gate ended turn before remaining tools ran"}',
                )
                yield _tool_result_sse(name, result, tc["id"], obs)
                yield {"type": "token", "content": resolution.user_message or ""}
                yield {"type": "done"}
                state.outcome = TurnOutcome.DONE
                return

            if resolution.action is GateAction.CONTINUE_LOOP:
                if resolution.mark_gate_retry_used:
                    state.gate_retry_used = True
                if resolution.mark_gate_returned:
                    gate_returned_this_batch = True
                obs = _observe_tool(config, name, result)
                yield _tool_result_sse(
                    name,
                    result,
                    tc["id"],
                    obs,
                    extra={"loop_continue": True},
                )
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": obs.model_payload,
                    }
                )
                batch_tool_count += 1
                note = _note_exploration_tool(name)
                if note:
                    pending_exploration_converge = note
                continue

            if resolution.mark_gate_returned:
                gate_returned_this_batch = True

            obs = _observe_tool(config, name, result)
            yield _tool_result_sse(name, result, tc["id"], obs)

            working.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": obs.model_payload,
                }
            )
            batch_tool_count += 1
            note = _note_exploration_tool(name)
            if note:
                pending_exploration_converge = note

        # Only after every tool_call_id has a tool message may we inject user prompts.
        if config.after_tool_batch:
            batch_events, pending_exploration_converge = await config.after_tool_batch(
                state=state,
                gate_returned=gate_returned_this_batch,
                batch_tool_count=batch_tool_count,
                pending_exploration=pending_exploration_converge,
            )
            for ev in batch_events or []:
                yield ev
        else:
            state.tools_since_checkpoint += batch_tool_count
        state.tools_ran += batch_tool_count
        state.outcome = TurnOutcome.CONTINUE
        return

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
    elif (
        content
        and _looks_like_write_claim(content)
        and not state.write_gate_seen
        and not state.shell_gate_seen
        and not state.memory_gate_seen
    ):
        content = _append_note(content, _UNVERIFIED_WRITE_NOTE)

    # Honest note when the provider stopped because output hit max_tokens.
    if finish_reason in {"length", "max_tokens"} and content:
        content = _append_note(content, _MAX_TOKENS_TRUNCATED_NOTE)

    edit_intent = working_requests_repo_edit(working, turn_goal)

    if not content:
        if should_nudge_missing_edit(
            edit_intent=edit_intent,
            write_gate_seen=state.write_gate_seen,
            edit_nudge_used=state.edit_nudge_used,
            tools_ran=state.tools_ran,
            has_content=False,
        ):
            nudge = format_missing_edit_nudge(turn_goal=turn_goal)
            working.append({"role": "user", "content": nudge})
            state.edit_nudge_used = True
            yield {
                "type": "edit_nudge",
                "reason": "missing_propose_edit",
                "goal": turn_goal,
            }
            state.outcome = TurnOutcome.CONTINUE
            return

        if state.tools_ran > 0:
            content = synthesize_tools_only_reply(
                turn_goal,
                write_gate_seen=state.write_gate_seen,
                edit_intent=edit_intent,
                edit_nudge_used=state.edit_nudge_used,
            )
        else:
            yield {
                "type": "error",
                "code": "EMPTY_RESPONSE",
                "message": EMPTY_RESPONSE_MESSAGE,
            }
            state.outcome = TurnOutcome.STOP
            return

    yield {"type": "token", "content": content}
    yield {"type": "done"}
    state.outcome = TurnOutcome.DONE
    return


async def run_agent_loop(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
    goal: Optional[str] = None,
    previous_goal: Optional[str] = None,
    config: Optional[LoopConfig] = None,
    emit: Optional[EventSink] = None,
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Yields SSE-oriented events:
      - agent_start / turn_start / turn_end / agent_end (A3 lifecycle)
      - steer_inject (when steering messages are drained)
      - turn_goal (when a Goal is active)
      - progress_checkpoint (interval, gate return, or exploration converge; reply when model narrates)
      - tool_start / tool_result
      - diff / shell / await_approval
      - soft_land / edit_nudge
      - thought (model reasoning block when provider returns it)
      - tools_disabled / token / error / done

    Pipe A: all events also go through ``emit`` (EventSink) for fire-and-forget observers.
    """
    cfg = config or LoopConfig.default()
    sink = emit or EventSink()

    def _pub(ev: Dict[str, Any]) -> Dict[str, Any]:
        sink.emit(ev)
        return ev

    import agent_window.tools  # noqa: F401

    from agent_window.agent.checkpoint import checkpoint_interval_from_settings
    from agent_window.agent.exploration import exploration_repeat_threshold_from_settings

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
    exploration_threshold = exploration_repeat_threshold_from_settings(
        agent_cfg.get("exploration_repeat_threshold"),
    )
    tools = [
        t for t in registry.get_openai_tools()
        if t.get("function", {}).get("name") not in disabled_tools
    ]
    turn_goal = (goal or "").strip() or None
    prev_goal = (previous_goal or "").strip() or None
    # Goal OFF → hooks cleared by with_goal_mode; soft-land still reads state.turn_goal
    effective_goal = turn_goal if cfg.goal_mode else None
    working = list(messages)

    try:
        yield _pub({"type": "agent_start", "session_id": session_id})

        if cfg.on_turn_start:
            working, start_events = await cfg.on_turn_start(
                working=working,
                goal=turn_goal,
                previous_goal=prev_goal,
            )
            for ev in start_events or []:
                yield _pub(ev)

        state = AgentLoopState(
            working=working,
            turn_goal=effective_goal,
            checkpoint_every_n=checkpoint_every_n,
            exploration_threshold=exploration_threshold,
        )

        for turn_index in range(max_tool_iters):
            if cancel_event is not None and cancel_event.is_set():
                yield _pub({"type": "error", "code": "TURN_CANCELLED", "message": "已停止"})
                return

            if cfg.get_steering_messages:
                pending = await cfg.get_steering_messages()
            elif session_id:
                pending = drain_steering(session_id)
            else:
                pending = []
            if not isinstance(pending, list):
                pending = []
            for msg in pending:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                # drain_steering already frames; keep a safety wrap for custom hooks.
                body = format_steering_content(content.strip())
                injected = {"role": "user", "content": body}
                state.working.append(injected)
                yield _pub({"type": "steer_inject", "content": injected["content"]})

            yield _pub({"type": "turn_start", "index": turn_index})
            async for event in _run_one_turn(
                state,
                tools=tools,
                model=model,
                cancel_event=cancel_event,
                config=cfg,
            ):
                sink.emit(event)
                yield event
            yield _pub(
                {
                    "type": "turn_end",
                    "index": turn_index,
                    "outcome": state.outcome.value,
                }
            )
            if state.outcome is TurnOutcome.STOP or state.outcome is TurnOutcome.DONE:
                return
            # CONTINUE → next iter

        # Soft land: one final answer without tools — honest mid-task wrap-up, not fake done.
        soft_index = max_tool_iters
        yield _pub({"type": "turn_start", "index": soft_index})
        soft_outcome = TurnOutcome.STOP
        try:
            yield _pub(
                {
                    "type": "soft_land",
                    "reason": "max_tool_iters",
                    "max_tool_iters": max_tool_iters,
                    "tools_ran": state.tools_ran,
                    "goal": state.turn_goal,
                }
            )
            state.working.append(
                {
                    "role": "user",
                    "content": soft_land_user_prompt(
                        max_tool_iters=max_tool_iters,
                        turn_goal=state.turn_goal,
                    ),
                }
            )
            try:
                turn = await race_with_cancel(
                    provider.chat_complete(state.working, tools=None, model=model),
                    cancel_event,
                )
            except TurnCancelled:
                yield _pub({"type": "error", "code": "TURN_CANCELLED", "message": "已停止"})
                return
            except Exception as e:
                logger.exception("soft-land chat_complete failed after tool loop limit")
                yield _pub(
                    {
                        "type": "error",
                        "code": "TOOL_LOOP_LIMIT",
                        "message": (
                            f"工具调用超过 {max_tool_iters} 轮，已提前收口"
                            f"（总结失败：{e}）。任务未完成。"
                        ),
                    }
                )
                return

            banner = soft_land_banner(
                max_tool_iters=max_tool_iters,
                tools_ran=state.tools_ran,
                turn_goal=state.turn_goal,
            )
            content = (turn.get("content") or "").strip()
            if content:
                # Banner first so users don't miss the incomplete-task signal.
                body = content
                if banner not in body:
                    body = f"{banner}\n\n{body}"
                yield _pub({"type": "token", "content": body})
                yield _pub({"type": "done"})
                soft_outcome = TurnOutcome.DONE
                state.outcome = soft_outcome
                return

            if state.tools_ran > 0:
                yield _pub(
                    {
                        "type": "token",
                        "content": synthesize_soft_land_reply(
                            max_tool_iters=max_tool_iters,
                            tools_ran=state.tools_ran,
                            turn_goal=state.turn_goal,
                            write_gate_seen=state.write_gate_seen,
                            edit_intent=working_requests_repo_edit(
                                state.working, state.turn_goal
                            ),
                        ),
                    }
                )
                yield _pub({"type": "done"})
                soft_outcome = TurnOutcome.DONE
                state.outcome = soft_outcome
                return

            yield _pub(
                {
                    "type": "error",
                    "code": "TOOL_LOOP_LIMIT",
                    "message": (
                        f"工具调用超过 {max_tool_iters} 轮，已提前收口；"
                        "无工具结果可总结。任务未完成。"
                    ),
                }
            )
            soft_outcome = TurnOutcome.STOP
            state.outcome = soft_outcome
        finally:
            yield _pub(
                {
                    "type": "turn_end",
                    "index": soft_index,
                    "outcome": soft_outcome.value,
                }
            )
    finally:
        yield _pub({"type": "agent_end", "session_id": session_id})



