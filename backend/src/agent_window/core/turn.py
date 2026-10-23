"""Turn boundary types for the agent loop (charter M03 / A0).

One Turn = one LLM completion + the tool batch it requested (if any).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TurnOutcome(str, Enum):
    """Result of ``_run_one_turn`` for the outer agent loop."""

    CONTINUE = "continue"  # tool batch ran; call LLM again
    DONE = "done"  # final reply emitted (token+done) or template close
    STOP = "stop"  # cancel / provider error / empty — outer must return


@dataclass
class AgentLoopState:
    """Mutable cross-turn state for ``run_agent_loop`` / ``_run_one_turn``."""

    working: List[Dict[str, Any]]
    turn_goal: Optional[str] = None
    write_gate_seen: bool = False
    shell_gate_seen: bool = False
    memory_gate_seen: bool = False
    gate_retry_used: bool = False
    tools_since_checkpoint: int = 0
    pending_checkpoint: Optional[Dict[str, Any]] = None
    exploration_tool: Optional[str] = None
    exploration_streak: int = 0
    exploration_converged: bool = False
    tools_ran: int = 0
    checkpoint_every_n: int = 4
    exploration_threshold: int = 6
    outcome: TurnOutcome = TurnOutcome.CONTINUE
    # One-shot: edit intent + empty stop without propose_edit → inject nudge & CONTINUE
    edit_nudge_used: bool = False
    # Scratch for exploration converge flush within a batch
    pending_exploration_converge: Optional[Dict[str, Any]] = field(default=None, repr=False)
