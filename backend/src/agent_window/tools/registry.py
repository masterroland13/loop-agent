"""Central tool registry (Hermes-inspired, minimal)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

ToolHandler = Callable[[Dict[str, Any]], Awaitable[str] | str]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        return sorted(self._tools.keys())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """OpenAI / LiteLLM chat.completions `tools` payload."""
        tools: List[Dict[str, Any]] = []
        for spec in self._tools.values():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
            )
        return tools


registry = ToolRegistry()
