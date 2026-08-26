"""Context compression helpers."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SummarizeFn = Callable[[str], Awaitable[str]]


def approx_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def approx_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += approx_tokens(content)
        total += 4  # role overhead
    return total


def _is_goal_system_message(msg: Dict[str, Any]) -> bool:
    from agent_window.agent.goal import GOAL_MARKER

    content = msg.get("content")
    return msg.get("role") == "system" and isinstance(content, str) and content.startswith(GOAL_MARKER)


def _split_system_messages(
    messages: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (other_system, goal_system, non_system)."""
    other_system: List[Dict[str, Any]] = []
    goal_system: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for m in messages:
        if _is_goal_system_message(m):
            goal_system.append(m)
        elif m.get("role") == "system":
            other_system.append(m)
        else:
            rest.append(m)
    return other_system, goal_system, rest


def _summary_message(summary_text: str, *, preserve_goal: Optional[str]) -> Dict[str, Any]:
    from agent_window.agent.goal import clip_goal

    lines = ["以下是更早对话的压缩摘要（自动压缩）："]
    goal = (preserve_goal or "").strip()
    if goal:
        lines.append(f"本轮目标（压缩保留）：{clip_goal(goal)}")
    lines.append(summary_text)
    return {"role": "system", "content": "\n".join(lines)}


async def compress_messages_if_needed(
    messages: List[Dict[str, Any]],
    *,
    auto_compress: bool,
    context_limit: int,
    summarize: Optional[SummarizeFn] = None,
    preserve_goal: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    If over limit and auto_compress, fold older user/assistant turns into one system summary.

    When ``preserve_goal`` is set, the Goal is pinned into the summary header and
    re-injected as a dedicated system block after compression so auto_compress
    cannot wash out Turn Goal.

    Returns (messages, compressed_flag).
    """
    if not auto_compress:
        return messages, False

    tokens = approx_messages_tokens(messages)
    if tokens <= context_limit:
        return messages, False

    other_system, _existing_goal_blocks, rest = _split_system_messages(messages)
    goal_text = (preserve_goal or "").strip() or None

    if len(rest) <= 4:
        keep = rest[-4:]
        out: List[Dict[str, Any]] = other_system + keep
        if goal_text:
            from agent_window.agent.goal import inject_goal_into_messages

            out = inject_goal_into_messages(out, goal_text)
        return out, True

    older = rest[:-4]
    recent = rest[-4:]
    blob_lines: List[str] = []
    for m in older:
        role = m.get("role", "?")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        blob_lines.append(f"{role}: {content[:800]}")
    blob = "\n".join(blob_lines)[:12000]

    summary_text = ""
    if summarize is not None:
        try:
            summarize_input = blob
            if goal_text:
                from agent_window.agent.goal import clip_goal

                summarize_input = (
                    f"【必须保留的本轮目标】{clip_goal(goal_text)}\n"
                    "摘要时不得丢失或改写该目标；其余内容极简归纳。\n\n"
                    f"{blob}"
                )
            summary_text = (await summarize(summarize_input)).strip()
        except Exception:
            logger.exception("LLM summarize failed; falling back to truncation")

    if not summary_text:
        summary_text = blob[:2000]

    summary_msg = _summary_message(summary_text, preserve_goal=goal_text)
    out = other_system + [summary_msg] + recent
    if goal_text:
        from agent_window.agent.goal import inject_goal_into_messages

        out = inject_goal_into_messages(out, goal_text)
    return out, True


def messages_contain_goal(messages: List[Dict[str, Any]], goal: str) -> bool:
    """Behavior helper for tests: Goal marker + goal substance present."""
    from agent_window.agent.goal import GOAL_MARKER, clip_goal

    needle = clip_goal(goal)
    for m in messages:
        content = m.get("content")
        if m.get("role") != "system" or not isinstance(content, str):
            continue
        if GOAL_MARKER in content and needle[:24] in content:
            return True
        if "本轮目标（压缩保留）" in content and needle[:24] in content:
            return True
    return False
