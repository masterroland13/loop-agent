"""Preset → before_tool_call policy (charter §0.4 / Gate 深拆 Step 2).

YOLO: action=allow (auto-apply write/shell/memory gates).
Trusted: action=wait; memory still respects ``confirm_memory`` setting.
Strict: action=wait for write/shell; **always** confirm memory
(ignores confirm_memory=False) — first Strict≠Trusted behavioral split.

``before_tool_call`` may also return ``{action: "block", reason}`` to refuse
a tool before execute (Pipe B).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Optional

from agent_window.core.loop_config import LoopConfig, LoopPreset

GateActionName = Literal["allow", "wait", "block"]


@dataclass(frozen=True)
class GatePresetDecision:
    """How gate / before_tool_call should behave for the active Preset."""

    auto_apply: bool
    """True → skip await_approval and apply immediately (YOLO / allow)."""

    force_confirm_memory: bool = False
    """True → memory always awaits even if settings.confirm_memory is False (Strict)."""

    action: GateActionName = "wait"
    """Pipe B: allow (auto), wait (UI/CLI), or block (refuse before/instead of execute)."""

    reason: Optional[str] = None
    """Human-readable block/wait reason (mainly for action=block)."""


def decide_gate_preset(preset: LoopPreset | str) -> GatePresetDecision:
    if isinstance(preset, str):
        key = preset.strip().lower()
        try:
            preset = LoopPreset(key)
        except ValueError:
            preset = LoopPreset.YOLO
    if preset is LoopPreset.YOLO:
        return GatePresetDecision(auto_apply=True, force_confirm_memory=False, action="allow")
    if preset is LoopPreset.STRICT:
        return GatePresetDecision(
            auto_apply=False,
            force_confirm_memory=True,
            action="wait",
        )
    # Trusted (default non-YOLO)
    return GatePresetDecision(auto_apply=False, force_confirm_memory=False, action="wait")


def memory_will_auto_apply(
    decision: GatePresetDecision,
    *,
    confirm_memory: bool = True,
) -> bool:
    """Resolve memory gate auto-apply after Preset + settings."""
    if decision.action == "block":
        return False
    if decision.force_confirm_memory:
        return False
    return bool(decision.auto_apply or decision.action == "allow" or not confirm_memory)


def normalize_gate_decision(result: Any, *, fallback_preset: LoopPreset | str = LoopPreset.YOLO) -> GatePresetDecision:
    """Coerce before_tool_call return value into GatePresetDecision."""
    if isinstance(result, GatePresetDecision):
        # Back-fill action if older callers constructed without it
        if result.action not in ("allow", "wait", "block"):
            action: GateActionName = "allow" if result.auto_apply else "wait"
            return GatePresetDecision(
                auto_apply=result.auto_apply,
                force_confirm_memory=result.force_confirm_memory,
                action=action,
                reason=result.reason,
            )
        if result.auto_apply and result.action == "wait":
            # Prefer explicit auto_apply for YOLO-shaped returns
            return GatePresetDecision(
                auto_apply=True,
                force_confirm_memory=result.force_confirm_memory,
                action="allow",
                reason=result.reason,
            )
        return result
    if isinstance(result, dict):
        action_raw = result.get("action")
        reason = result.get("reason")
        if isinstance(reason, str) or reason is None:
            pass
        else:
            reason = str(reason)
        if action_raw == "block":
            return GatePresetDecision(
                auto_apply=False,
                force_confirm_memory=bool(result.get("force_confirm_memory", False)),
                action="block",
                reason=reason if isinstance(reason, str) else (reason or "blocked by before_tool_call"),
            )
        if action_raw == "allow" or result.get("auto_apply") is True:
            return GatePresetDecision(
                auto_apply=True,
                force_confirm_memory=bool(result.get("force_confirm_memory", False)),
                action="allow",
                reason=reason if isinstance(reason, str) else None,
            )
        if action_raw == "wait" or "auto_apply" in result:
            return GatePresetDecision(
                auto_apply=False,
                force_confirm_memory=bool(result.get("force_confirm_memory", False)),
                action="wait",
                reason=reason if isinstance(reason, str) else None,
            )
    return decide_gate_preset(fallback_preset)


async def before_tool_call_preset(**kwargs: Any) -> GatePresetDecision:
    """LoopConfig.before_tool_call default — returns GatePresetDecision.

    ``phase`` (optional): ``pre`` (default) before execute; ``await_gate`` when
    an AWAIT_* marker needs Pipe B resolution. Preset policy is the same either way;
    the pipeline runs ``wait_for_*`` when action is wait/allow.
    """
    config: Optional[LoopConfig] = kwargs.get("config")
    preset = config.preset if config is not None else LoopPreset.YOLO
    return decide_gate_preset(preset)


def install_preset_hooks(config: LoopConfig) -> LoopConfig:
    """Attach Preset before_tool_call (does not clear Goal hooks)."""
    return replace(config, before_tool_call=before_tool_call_preset)


async def resolve_gate_decision(
    config: LoopConfig,
    *,
    name: str = "",
    arguments: Any = None,
    phase: str = "pre",
    await_payload: Any = None,
    cancel_event: Any = None,
) -> GatePresetDecision:
    """Prefer before_tool_call hook result; fall back to decide_gate_preset."""
    if config.before_tool_call is not None:
        result = await config.before_tool_call(
            name=name,
            arguments=arguments,
            config=config,
            phase=phase,
            await_payload=await_payload,
            cancel_event=cancel_event,
        )
        return normalize_gate_decision(result, fallback_preset=config.preset)
    return decide_gate_preset(config.preset)
