"""Session Tree helpers (charter M10 / A4).

Messages form a parent→child tree; session.leaf_id points at the active tip.
build_path walks leaf→root then reverses to root→leaf for LLM context.

Duck-typed over ORM rows (role/content/id/parent_id/entry_type) so core does
not import agent_window.models (layer boundary).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from agent_window.core.messages import AgentMessage, default_convert_to_llm


def walk_to_root(messages_by_id: dict, leaf_id: str) -> list:
    """Walk parent_id chain from leaf to root; return root→leaf order."""
    path: list = []
    seen: set[str] = set()
    current_id: str | None = leaf_id
    while current_id:
        if current_id in seen:
            break
        seen.add(current_id)
        msg = messages_by_id.get(current_id)
        if msg is None:
            break
        path.append(msg)
        current_id = getattr(msg, "parent_id", None)
    path.reverse()
    return path


def _messages_by_id(session) -> Dict[str, Any]:
    return {m.id: m for m in (getattr(session, "messages", None) or [])}


def _role_value(role: Any) -> str:
    if role is None:
        return ""
    if hasattr(role, "value"):
        return str(role.value)
    return str(role)


def _fallback_leaf_id(session) -> str | None:
    msgs = list(getattr(session, "messages", None) or [])
    if not msgs:
        return None
    latest = max(msgs, key=lambda m: (getattr(m, "sequence", 0), getattr(m, "created_at", 0) or 0))
    return latest.id


def build_path_from_session(session, leaf_id: str | None = None) -> list:
    """Active path root→leaf. Uses session.leaf_id when leaf_id is None; max sequence fallback."""
    by_id = _messages_by_id(session)
    if not by_id:
        return []
    tip = leaf_id or getattr(session, "leaf_id", None) or _fallback_leaf_id(session)
    if not tip or tip not in by_id:
        tip = _fallback_leaf_id(session)
    if not tip:
        return []
    return walk_to_root(by_id, tip)


def messages_to_agent_messages(path: Sequence[Any]) -> List[AgentMessage]:
    """Map message-like rows to AgentMessage (compaction via entry_type)."""
    out: List[AgentMessage] = []
    for m in path:
        entry = getattr(m, "entry_type", None) or "message"
        if entry == "compaction_summary":
            role = "compaction_summary"
        else:
            role = _role_value(getattr(m, "role", None))
        out.append(
            AgentMessage(
                role=role,
                content=getattr(m, "content", None) or "",
                id=getattr(m, "id", None),
                entry_type=entry,
            )
        )
    return out


def build_llm_messages(
    path: Sequence[Any],
    *,
    convert_to_llm: Optional[Callable[[List[AgentMessage]], List[Dict[str, Any]]]] = None,
    system_prompt: str | None = None,
) -> List[Dict[str, Any]]:
    """Convert path to LLM dicts; optionally prepend system_prompt."""
    convert = convert_to_llm or default_convert_to_llm
    agent_msgs = messages_to_agent_messages(list(path))
    llm = convert(agent_msgs)
    filtered: List[Dict[str, Any]] = []
    for m in llm:
        content = m.get("content")
        if isinstance(content, str) and not content.strip():
            continue
        filtered.append(m)
    if system_prompt:
        return [{"role": "system", "content": system_prompt}] + filtered
    return filtered


def last_user_on_path(path: Sequence[Any]) -> Any | None:
    for m in reversed(path):
        if _role_value(getattr(m, "role", None)) == "user":
            return m
    return None


def path_ending_at(path: Sequence[Any], message_id: str) -> list:
    out: list = []
    for m in path:
        out.append(m)
        if getattr(m, "id", None) == message_id:
            break
    return out
