"""Turn Goal: extract + inject into the agent working context."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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

# Long pasted dumps (e.g. LangGraph traces) without a clear new ask at the top.
_FILLER_MIN_LEN = 160
_LONG_FIRST_PARA = 120

_TASK_START_RE = re.compile(
    r"^(请|帮我|帮忙|需要|务必|直接|改|换成|聚焦|专注|只|先|现在|麻烦|能否)",
    re.IGNORECASE,
)

_TASK_VERB_RE = re.compile(
    r"(请|帮我|修复|列出|运行|解释|实现|添加|删除|更新|检查|排查|查看|创建|修改|对照|收工|只跑|改成)",
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


def is_exploratory_filler(text: str) -> bool:
    """True for very long user text that likely pastes context without a new directive."""
    t = (text or "").strip()
    if len(t) < _FILLER_MIN_LEN:
        return False
    first_para = re.split(r"\n\s*\n", t, maxsplit=1)[0].strip()
    if _TASK_START_RE.match(first_para):
        return False
    if _TASK_VERB_RE.search(t[:96]):
        return False
    return True


def _inherit_prior_substantive_goal(prior_user_texts: Sequence[str]) -> Optional[str]:
    for prev in reversed(list(prior_user_texts)):
        p = (prev or "").strip()
        if p and not is_low_info_followup(p):
            return clip_goal(p)
    return None


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
    priors = list(prior_user_texts or [])
    if priors:
        if is_continuation_followup(text):
            inherited = _inherit_prior_substantive_goal(priors)
            if inherited:
                return inherited
        if is_exploratory_filler(text):
            inherited = _inherit_prior_substantive_goal(priors)
            if inherited:
                return inherited
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


@dataclass(frozen=True)
class GoalResolution:
    """Result of resolving a turn goal (F1 extract / F8 pin / change note)."""

    turn_goal: Optional[str]
    previous_goal: Optional[str]
    """Set only when the goal changed from the prior assistant turn."""
    changed: bool
    source: str
    """extract | regenerate | pinned — used in goal.change audit."""


def resolve_turn_goal(
    *,
    goal_mode: bool,
    user_text: str,
    history_messages: Sequence[Any],
    pinned_goal: Optional[str] = None,
    audit_source: str = "extract",
) -> GoalResolution:
    """Resolve sticky turn goal when Goal mode is on (F1 + F8 pin).

    - Goal OFF → no goal.
    - ``pinned_goal`` set → use clipped pin (manual override).
    - else → ``extract_turn_goal`` from user text + history.
    """
    if not goal_mode:
        return GoalResolution(
            turn_goal=None,
            previous_goal=None,
            changed=False,
            source=audit_source,
        )

    prev_goal = previous_turn_goal_from_messages(history_messages)
    pin = (pinned_goal or "").strip()
    if pin:
        turn_goal = clip_goal(pin)
        source = "pinned"
    else:
        turn_goal = extract_turn_goal(
            user_text,
            prior_user_texts_from_history(history_messages),
        )
        source = audit_source

    changed = bool(prev_goal) and not goals_equal(prev_goal, turn_goal)
    return GoalResolution(
        turn_goal=turn_goal,
        previous_goal=(prev_goal if changed else None),
        changed=changed,
        source=source,
    )


def goal_change_audit_payload(resolution: GoalResolution) -> Optional[Dict[str, Any]]:
    """F8: payload for ``goal.change`` audit, or None when unchanged / no goal."""
    if not resolution.changed or not resolution.turn_goal:
        return None
    return {
        "previous_goal": resolution.previous_goal,
        "goal": resolution.turn_goal,
        "source": resolution.source,
    }


def normalize_pinned_goal(text: Optional[str]) -> Optional[str]:
    """Empty / whitespace → None; else clipped goal string."""
    raw = (text or "").strip()
    if not raw:
        return None
    return clip_goal(raw)
