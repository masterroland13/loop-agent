"""Default LoopConfig.transform_context — compress + Goal pin (C3).

Lives in coding/services so core does not import compress. loop.py only
calls the hook; find_cut_index / six-section logic stay in compress.py.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, Optional, Tuple

from agent_window.core.loop_config import LoopConfig
from agent_window.services.compress import CompressMeta, compress_messages_if_needed

logger = logging.getLogger(__name__)

TransformOut = Tuple[list, bool, CompressMeta]
OnCompressed = Callable[[list, CompressMeta], Any]


async def default_transform_context(
    messages: list,
    *,
    auto_compress: bool,
    context_limit: int,
    summarize: Any = None,
    preserve_goal: Optional[str] = None,
    force: bool = False,
    focus: Optional[str] = None,
) -> TransformOut:
    """Same behavior as compress_messages_if_needed (C0–C2)."""
    return await compress_messages_if_needed(
        messages,
        auto_compress=auto_compress,
        context_limit=context_limit,
        summarize=summarize,
        preserve_goal=preserve_goal,
        force=force,
        focus=focus,
    )


def install_context_transform(
    config: LoopConfig,
    *,
    auto_compress: bool | None = None,
    context_limit: int | None = None,
    summarize: Any = None,
    on_compressed: OnCompressed | None = None,
) -> LoopConfig:
    """Bind compress settings onto ``config.transform_context``."""
    if auto_compress is None or context_limit is None:
        from agent_window.services.agent_settings import load_agent_settings

        settings = load_agent_settings()
        if auto_compress is None:
            auto_compress = bool(settings.get("auto_compress"))
        if context_limit is None:
            context_limit = int(settings.get("context_limit") or 8192)

    bound_auto = bool(auto_compress)
    bound_limit = int(context_limit)

    async def _transform(messages: list, **kwargs: Any) -> TransformOut:
        out, compressed, meta = await default_transform_context(
            messages,
            auto_compress=bool(kwargs.get("auto_compress", bound_auto)),
            context_limit=int(kwargs.get("context_limit", bound_limit)),
            summarize=kwargs.get("summarize", summarize),
            preserve_goal=kwargs.get("preserve_goal") or kwargs.get("goal"),
            force=bool(kwargs.get("force", False)),
            focus=kwargs.get("focus"),
        )
        if compressed and on_compressed is not None:
            try:
                on_compressed(out, meta)
            except Exception:
                logger.exception("transform_context on_compressed failed")
        return out, compressed, meta

    extra = dict(config.extra or {})
    extra["context_transform"] = "compress"
    return replace(config, transform_context=_transform, extra=extra)


async def apply_transform_context(
    config: LoopConfig,
    messages: list,
    *,
    preserve_goal: Optional[str] = None,
) -> TransformOut:
    """Call the hook; identity when unset. Always returns (messages, compressed, meta)."""
    hook = config.transform_context
    if hook is None:
        return list(messages), False, CompressMeta()
    result = await hook(messages, preserve_goal=preserve_goal, goal=preserve_goal)
    if isinstance(result, tuple) and len(result) >= 3:
        return result[0], bool(result[1]), result[2]
    if isinstance(result, list):
        return result, False, CompressMeta()
    return list(messages), False, CompressMeta()
