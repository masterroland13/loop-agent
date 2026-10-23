"""Progress checkpoint: force the model to contrast Turn Goal periodically."""

from __future__ import annotations

from typing import Literal, Optional

from agent_window.agent.goal import clip_goal

CHECKPOINT_MARKER = "【进度检查点】"

CheckpointReason = Literal["interval", "gate", "exploration"]


def checkpoint_interval_from_settings(raw: object, *, default: int = 4) -> int:
    """0 disables interval checkpoints; gate checkpoints still apply."""
    try:
        n = int(raw if raw is not None else default)
    except (TypeError, ValueError):
        n = default
    if n <= 0:
        return 0
    return max(2, min(16, n))


def should_checkpoint(
    tools_since_last: int,
    gate_returned: bool,
    every_n_tools: int,
) -> Optional[CheckpointReason]:
    if gate_returned:
        return "gate"
    if every_n_tools > 0 and tools_since_last >= every_n_tools:
        return "interval"
    return None


def format_checkpoint_user_message(goal: Optional[str]) -> str:
    g = clip_goal(goal or "")
    return (
        f"{CHECKPOINT_MARKER}\n"
        f"对照本轮目标「{g}」，请先用 1–3 句话说明：当前进度、主要阻塞（如有）、"
        "以及下一步打算（继续 / 换手段 / 向人求助 / 对照目标收工）。"
        "说完后再继续调用工具或直接给出结论。"
    )


def clip_checkpoint_reply(text: str, *, max_len: int = 800) -> str:
    """Trim model checkpoint narration for SSE / UI (not the final answer)."""
    raw = (text or "").strip()
    if not raw:
        return ""
    # Drop accidental re-echo of the checkpoint prompt itself.
    if raw.startswith(CHECKPOINT_MARKER):
        raw = raw[len(CHECKPOINT_MARKER) :].lstrip("\n :：")
    raw = " ".join(raw.split())
    if len(raw) > max_len:
        return raw[: max_len - 1].rstrip() + "…"
    return raw
