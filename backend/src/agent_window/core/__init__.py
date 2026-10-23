"""loop-agent-core logical home (A0).

Physical package remains ``agent_window``; this package hosts LoopConfig and
other core primitives as they are extracted from the monolith.
"""

from agent_window.core.event_sink import LIFECYCLE_TYPES, EventSink
from agent_window.core.goal_hooks import install_goal_hooks
from agent_window.core.loop_config import LoopConfig, LoopPreset
from agent_window.core.messages import AgentMessage, default_convert_to_llm
from agent_window.core.steering import (
    bind_steering,
    clear_steering,
    drain_steering,
    format_steering_content,
    peek_steering_count,
    push_steering,
)
from agent_window.core.turn import AgentLoopState, TurnOutcome

__all__ = [
    "AgentLoopState",
    "AgentMessage",
    "EventSink",
    "LIFECYCLE_TYPES",
    "LoopConfig",
    "LoopPreset",
    "TurnOutcome",
    "bind_steering",
    "clear_steering",
    "default_convert_to_llm",
    "drain_steering",
    "format_steering_content",
    "install_goal_hooks",
    "peek_steering_count",
    "push_steering",
]
