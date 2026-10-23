"""LoopConfig — pluggable hooks for the agent loop (charter §3.1).

A0: dataclass + factories only.
A1c / Gate Step 2: Preset (YOLO/Trusted/Strict) via ``before_tool_call``
(``core/preset_hooks``) → action allow|wait|block; await resolved in tool_pipeline.
Strict forces memory confirmation.
A4: convert_to_llm is required-with-default (default_convert_to_llm when None).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

# Hook callables stay loosely typed in A0; A1+ will narrow signatures.
Hook = Callable[..., Any]
AsyncHook = Callable[..., Awaitable[Any]]


class LoopPreset(str, Enum):
    """Approval strategy (charter §0.4). Wired in A1 via before_tool_call / gates."""

    YOLO = "yolo"
    TRUSTED = "trusted"
    STRICT = "strict"


@dataclass
class LoopConfig:
    """Runtime policy for one agent run.

    Factories:
      - ``LoopConfig.default()`` — Goal OFF + YOLO (product default)
      - ``from_settings`` — goal_mode + preset from session/settings
      - ``with_goal_mode`` / ``with_preset`` — copy-on-write overlays

    ``convert_to_llm`` is required-with-default: if None after init, resolves to
    ``default_convert_to_llm`` (AgentMessage → OpenAI dicts; compaction_summary → user).
    """

    goal_mode: bool = False
    preset: LoopPreset = LoopPreset.YOLO

    # Charter §3.1 — convert_to_llm required-with-default (A4)
    convert_to_llm: Optional[Hook] = None
    transform_context: Optional[AsyncHook] = None
    before_tool_call: Optional[AsyncHook] = None
    after_tool_call: Optional[AsyncHook] = None
    after_tool_batch: Optional[AsyncHook] = None
    on_turn_start: Optional[AsyncHook] = None
    should_stop_after_turn: Optional[AsyncHook] = None
    get_steering_messages: Optional[AsyncHook] = None
    get_follow_up_messages: Optional[AsyncHook] = None
    on_final_reply: Optional[Hook] = None

    # Reserved for A1 GoalModeHooks / event sink; unused in A0
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.convert_to_llm is None:
            from agent_window.core.messages import default_convert_to_llm

            self.convert_to_llm = default_convert_to_llm

    @classmethod
    def default(cls) -> "LoopConfig":
        """Goal OFF + YOLO — thin loop default."""
        from agent_window.core.preset_hooks import install_preset_hooks
        from agent_window.core.tool_hooks import install_base_tool_hooks

        return install_preset_hooks(
            install_base_tool_hooks(cls(goal_mode=False, preset=LoopPreset.YOLO))
        )

    @classmethod
    def from_settings(
        cls,
        goal_mode: bool = False,
        preset: LoopPreset | str = "yolo",
    ) -> "LoopConfig":
        """Build config from session goal flag + agent settings loop_preset."""
        return cls.default().with_goal_mode(bool(goal_mode)).with_preset(preset)

    def with_goal_mode(self, enabled: bool = True) -> "LoopConfig":
        from agent_window.core.goal_hooks import install_goal_hooks

        return install_goal_hooks(replace(self, goal_mode=enabled))

    def with_preset(self, preset: LoopPreset | str) -> "LoopConfig":
        from agent_window.core.preset_hooks import install_preset_hooks

        if isinstance(preset, str):
            key = preset.strip().lower()
            try:
                preset = LoopPreset(key)
            except ValueError:
                preset = LoopPreset.YOLO
        return install_preset_hooks(replace(self, preset=preset))
