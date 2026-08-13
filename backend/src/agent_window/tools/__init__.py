"""Tool package — importing modules registers tools."""

from agent_window.tools import builtin as _builtin  # noqa: F401
from agent_window.tools import edit_tools as _edit_tools  # noqa: F401
from agent_window.tools import fs_tools as _fs_tools  # noqa: F401
from agent_window.tools import memory_tools as _memory_tools  # noqa: F401
from agent_window.tools import shell_tools as _shell_tools  # noqa: F401
from agent_window.tools.registry import registry

__all__ = ["registry"]
