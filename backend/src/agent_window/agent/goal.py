"""Turn Goal: extract + inject into the agent working context."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

GOAL_MARKER = "【本轮目标】"
_MAX_GOAL_CHARS = 240

_AFFIRMATION_RE = re.compile(
    r"^(好的|好|行|可以|继续|同意|嗯|哦|ok|okay|yes|y|sure|go|continue|继续吧|请继续|那就这样|"
    r"麻烦了|拜托了|thanks|thank you|收到)[.!！。…\s]*$",
    re.IGNORECASE,
)

# 「好的，按你刚才…继续深挖」— short ack + new instructions still inherits prior ask.
_CONTINUATION_PREFIX_RE = re.compile(
    r"^(好的|好|行|可以|继续|同意|嗯|哦|ok|okay|yes|sure|go|continue|继续吧|请继续|那就这样|收到)"
    r"[，,。.!！\s]+",
    re.IGNORECASE,
)


def is_low_info_followup(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) > 40:
        return False
    return bool(_AFFIRMATION_RE.match(t))


def is_continuation_followup(text: str) -> bool:
    """True when the user is agreeing to continue rather than stating a new task."""
    t = (text or "").strip()
    if not t:
        return True
    if is_low_info_followup(t):
        return True
    return bool(_CONTINUATION_PREFIX_RE.match(t))


def clip_goal(text: str, max_len: int = _MAX_GOAL_CHARS) -> str:
    raw = (text or "").strip()
    if not raw:
        return "完成本轮用户请求"
    parts = re.split(r"\n\s*\n", raw, maxsplit=1)
    head = parts[0].strip()
    head = re.sub(r"\s+", " ", head)
    if len(head) > max_len:
        return head[: max_len - 1].rstrip() + "…"
    return head


def extract_turn_goal(
    user_text: str,
    prior_user_texts: Optional[Sequence[str]] = None,
) -> str:
    """
    Derive a sticky turn goal from the latest user message.

    Short affirmations ("好的" / "继续") inherit the last substantive user ask
    so the loop does not drift into aimless exploration.
    """
    text = (user_text or "").strip()
    if is_continuation_followup(text) and prior_user_texts:
        for prev in reversed(list(prior_user_texts)):
            p = (prev or "").strip()
            if p and not is_low_info_followup(p):
                return clip_goal(p)
    if not text:
        return "完成本轮用户请求"
    return clip_goal(text)


def format_goal_block(goal: str) -> str:
    g = clip_goal(goal)
    return (
        f"{GOAL_MARKER}{g}\n"
        "每一拍必须对照此目标决定：继续推进 / 换手段 / 向人求助 / 对照目标收工。"
        "不要偏离目标做无关探索；探索仅服务于完成该目标。"
    )


def inject_goal_into_messages(
    messages: List[Dict[str, Any]],
    goal: str,
) -> List[Dict[str, Any]]:
    """Insert or refresh a system Goal block after the primary system prompt."""
    working = [dict(m) for m in messages]
    block = {"role": "system", "content": format_goal_block(goal)}
    if not working:
        return [block]

    for i, msg in enumerate(working):
        content = msg.get("content")
        if msg.get("role") == "system" and isinstance(content, str) and content.startswith(GOAL_MARKER):
            working[i] = block
            return working

    if working[0].get("role") == "system":
        working.insert(1, block)
    else:
        working.insert(0, block)
    return working


def prior_user_texts_from_history(messages: Sequence[Any]) -> List[str]:
    """Collect prior user message bodies (ORM Message or dict)."""
    out: List[str] = []
    for m in messages:
        role = getattr(m, "role", None)
        if role is not None:
            role_val = role.value if hasattr(role, "value") else str(role)
            content = getattr(m, "content", "") or ""
        elif isinstance(m, dict):
            role_val = str(m.get("role") or "")
            content = m.get("content") or ""
        else:
            continue
        if role_val == "user" and str(content).strip():
            out.append(str(content))
    return out


def _role_value(message: Any) -> str:
    role = getattr(message, "role", None)
    if role is not None:
        return role.value if hasattr(role, "value") else str(role)
    if isinstance(message, dict):
        return str(message.get("role") or "")
    return ""


def _message_field(message: Any, name: str) -> Any:
    if hasattr(message, name):
        return getattr(message, name)
    if isinstance(message, dict):
        return message.get(name)
    return None


def _goal_from_summary(summary: Any) -> Optional[str]:
    if not summary or not isinstance(summary, str):
        return None
    raw = summary.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    def _pick(obj: dict) -> Optional[str]:
        goal = obj.get("goal")
        if isinstance(goal, str) and goal.strip():
            return goal.strip()
        nested = obj.get("turn_meta")
        if isinstance(nested, dict):
            nested_goal = nested.get("goal")
            if isinstance(nested_goal, str) and nested_goal.strip():
                return nested_goal.strip()
        return None

    # Prefer explicit turn_meta (or typo alias) before bare goal-bearing dicts.
    typ = data.get("type")
    if typ == "turn_meta" or "goal" in data:
        picked = _pick(data)
        if picked:
            return picked
    return _pick(data)


def goal_from_assistant_message(message: Any) -> Optional[str]:
    """Read sticky goal from assistant summary (turn_meta) or F6 trace."""
    from agent_window.agent.turn_event import latest_goal, parse_trace

    summary_goal = _goal_from_summary(_message_field(message, "summary"))
    if summary_goal:
        return summary_goal
    trace_raw = _message_field(message, "trace")
    if isinstance(trace_raw, list):
        return latest_goal([e for e in trace_raw if isinstance(e, dict)])
    return latest_goal(parse_trace(trace_raw if isinstance(trace_raw, str) else None))


def previous_turn_goal_from_messages(messages: Sequence[Any]) -> Optional[str]:
    """Newest prior assistant goal, if any."""
    for message in reversed(list(messages)):
        if _role_value(message) != "assistant":
            continue
        goal = goal_from_assistant_message(message)
        if goal:
            return goal
    return None


def goals_equal(a: Optional[str], b: Optional[str]) -> bool:
    return clip_goal(a or "") == clip_goal(b or "")
