"""Base tool hooks — F4 observation slim + optional Goal exploration note (F7).

F4 runs for every turn (Goal OFF included). F7 exploration streak is collected
when ``config.goal_mode`` is ON; it does not inject mid-batch.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional

from agent_window.agent.observation import ObservationResult, observe_tool_result
from agent_window.agent.turn_event import SpillFn
from agent_window.core.loop_config import LoopConfig
from agent_window.core.turn import AgentLoopState


def _spill_from_config(config: LoopConfig | None) -> SpillFn | None:
    if config is None:
        return None
    spill = (config.extra or {}).get("observe_spill")
    return spill if callable(spill) else None


def observe_for_working(
    tool_name: str,
    raw_result: str,
    *,
    config: LoopConfig | None = None,
    spill: SpillFn | None = None,
) -> ObservationResult:
    """F4 contract entry — slim payload + trace metadata (spill from config.extra)."""
    return observe_tool_result(
        tool_name,
        raw_result,
        spill=spill if spill is not None else _spill_from_config(config),
    )


def slim_for_working(
    tool_name: str,
    raw_result: str,
    *,
    config: LoopConfig | None = None,
    spill: SpillFn | None = None,
) -> str:
    """Compact JSON/text for ``working[]``; SSE/trace keep full ``raw_result``."""
    return observe_for_working(tool_name, raw_result, config=config, spill=spill).model_payload


def exploration_note_after_tool(
    config: LoopConfig,
    state: AgentLoopState,
    tool_name: str,
) -> Optional[Dict[str, Any]]:
    """F7 streak update when Goal mode is on."""
    if not config.goal_mode:
        return None
    from agent_window.core.goal_hooks import note_exploration_tool

    return note_exploration_tool(state, tool_name)


def install_base_tool_hooks(config: LoopConfig) -> LoopConfig:
    """Ensure base hooks are composed with Goal hooks (F4 always; F7 when ON)."""
    extra = dict(config.extra or {})
    extra.setdefault("tool_hooks", {"observe": "observation.observe_tool_result"})
    return replace(config, extra=extra)


def with_observe_spill(config: LoopConfig, spill: SpillFn) -> LoopConfig:
    """Attach a data_path spill callback for F4 oversized full_ref (F6-aligned)."""
    extra = dict(config.extra or {})
    extra["observe_spill"] = spill
    return replace(config, extra=extra)
