"""GoalModeHooks — F1/F2/F7/F8 strategy as LoopConfig hooks (charter §0.3 / §3.1).

Installed by ``LoopConfig.with_goal_mode(True)``. When OFF, those hook slots are
cleared so ``loop.py`` has no scattered ``if goal_mode`` for inject/checkpoint/
exploration. F8 goal.change audit is resolved via ``resolve_session_goal`` /
``goal_change_audit_event`` (called from routes, not mid-loop).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_window.core.loop_config import LoopConfig
from agent_window.core.turn import AgentLoopState


def resolve_session_goal(
    *,
    goal_mode: bool,
    user_text: str,
    history_messages: Sequence[Any],
    pinned_goal: Optional[str] = None,
    audit_source: str = "extract",
):
    """F1+F8: resolve turn goal (extract or pinned) + change metadata."""
    from agent_window.agent.goal import resolve_turn_goal

    return resolve_turn_goal(
        goal_mode=goal_mode,
        user_text=user_text,
        history_messages=history_messages,
        pinned_goal=pinned_goal,
        audit_source=audit_source,
    )


def goal_change_audit_event(resolution) -> Optional[Dict[str, Any]]:
    """F8: ``goal.change`` audit payload when the goal changed."""
    from agent_window.agent.goal import goal_change_audit_payload

    return goal_change_audit_payload(resolution)


def apply_goal_start(
    working: List[Dict[str, Any]],
    *,
    goal: Optional[str],
    previous_goal: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """F1: inject Turn Goal once + turn_goal SSE payloads."""
    from agent_window.agent.goal import inject_goal_into_messages

    g = (goal or "").strip()
    if not g:
        return working, []
    next_working = inject_goal_into_messages(list(working), g)
    event: Dict[str, Any] = {"type": "turn_goal", "goal": g}
    prev = (previous_goal or "").strip()
    if prev and prev != g:
        event["previous_goal"] = prev
    return next_working, [event]


def note_exploration_tool(state: AgentLoopState, tool_name: str) -> Optional[Dict[str, Any]]:
    """F7 streak update only — never inject mid-batch."""
    from agent_window.agent.exploration import (
        should_converge_exploration,
        update_exploration_streak,
    )

    state.exploration_tool, state.exploration_streak = update_exploration_streak(
        state.exploration_tool,
        state.exploration_streak,
        tool_name,
    )
    if state.exploration_converged or not should_converge_exploration(
        state.exploration_streak,
        state.exploration_threshold,
    ):
        return None
    return {
        "goal": state.turn_goal,
        "reason": "exploration",
        "tool": state.exploration_tool or tool_name,
        "streak": state.exploration_streak,
    }


def flush_goal_after_batch(
    state: AgentLoopState,
    *,
    gate_returned: bool,
    batch_tool_count: int,
    pending_exploration: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """F7 flush + F2 checkpoint after the full tool batch.

    Mutates ``state.working`` / counters. Returns (sse_events, cleared_pending).
    """
    from agent_window.agent.checkpoint import (
        format_checkpoint_user_message,
        should_checkpoint,
    )
    from agent_window.agent.exploration import format_exploration_converge_message

    events: List[Dict[str, Any]] = []
    pending = pending_exploration

    if pending and not state.exploration_converged:
        state.exploration_converged = True
        converge_msg = format_exploration_converge_message(
            state.turn_goal,
            str(pending.get("tool") or ""),
            int(pending.get("streak") or 0),
        )
        state.working.append({"role": "user", "content": converge_msg})
        events.append(
            {
                "type": "progress_checkpoint",
                "goal": pending.get("goal"),
                "reason": "exploration",
                "tool": pending.get("tool"),
                "streak": pending.get("streak"),
            }
        )
        pending = None

    state.tools_since_checkpoint += batch_tool_count
    checkpoint_reason = should_checkpoint(
        state.tools_since_checkpoint,
        gate_returned,
        state.checkpoint_every_n,
    )
    if checkpoint_reason:
        checkpoint_msg = format_checkpoint_user_message(state.turn_goal)
        state.working.append({"role": "user", "content": checkpoint_msg})
        state.pending_checkpoint = {
            "goal": state.turn_goal,
            "tools_since_last": state.tools_since_checkpoint,
            "reason": checkpoint_reason,
        }
        events.append(
            {
                "type": "progress_checkpoint",
                "goal": state.turn_goal,
                "tools_since_last": state.tools_since_checkpoint,
                "reason": checkpoint_reason,
            }
        )
        state.tools_since_checkpoint = 0

    return events, pending


async def _on_turn_start(**kwargs: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return apply_goal_start(
        kwargs.get("working") or [],
        goal=kwargs.get("goal"),
        previous_goal=kwargs.get("previous_goal"),
    )


async def _after_tool_call(**kwargs: Any) -> Optional[Dict[str, Any]]:
    state = kwargs.get("state")
    tool_name = kwargs.get("name") or kwargs.get("tool_name") or ""
    if state is None:
        return None
    return note_exploration_tool(state, str(tool_name))


async def _after_tool_batch(**kwargs: Any) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    state = kwargs["state"]
    return flush_goal_after_batch(
        state,
        gate_returned=bool(kwargs.get("gate_returned")),
        batch_tool_count=int(kwargs.get("batch_tool_count") or 0),
        pending_exploration=kwargs.get("pending_exploration"),
    )


def install_goal_hooks(config: LoopConfig) -> LoopConfig:
    """Attach or clear F1/F2/F7 hooks according to ``config.goal_mode``."""
    if not config.goal_mode:
        return replace(
            config,
            on_turn_start=None,
            after_tool_call=None,
            after_tool_batch=None,
        )
    return replace(
        config,
        on_turn_start=_on_turn_start,
        after_tool_call=_after_tool_call,
        after_tool_batch=_after_tool_batch,
    )
