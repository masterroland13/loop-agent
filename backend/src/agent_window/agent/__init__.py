"""Agent runtime package."""

from __future__ import annotations

from typing import Any

__all__ = ["run_agent_loop"]


def __getattr__(name: str) -> Any:
    # Lazy: importing agent.observation must not pull in loop (circular with tool_hooks).
    if name == "run_agent_loop":
        from agent_window.agent.loop import run_agent_loop

        return run_agent_loop
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
