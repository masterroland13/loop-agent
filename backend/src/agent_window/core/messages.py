"""AgentMessage + default_convert_to_llm (charter M06 / A4).

Inner messages may use rich roles (e.g. compaction_summary); convert_to_llm
flattens them to OpenAI-compatible user/assistant/system dicts before the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

COMPACTION_SUMMARY_MARKER = "【对话压缩摘要】"


@dataclass
class AgentMessage:
    """In-process message before convert_to_llm."""

    role: str  # user | assistant | system | compaction_summary
    content: str
    id: str | None = None
    entry_type: str | None = None
    extra: Dict[str, Any] = field(default_factory=dict)


ConvertToLlm = Callable[[List[AgentMessage]], List[Dict[str, Any]]]


def default_convert_to_llm(msgs: List[AgentMessage]) -> List[Dict[str, Any]]:
    """Required-with-default LoopConfig hook: flatten AgentMessage → LLM dicts.

    - user / assistant / system: pass-through role + content
    - compaction_summary → user message with 【对话压缩摘要】 prefix
    """
    out: List[Dict[str, Any]] = []
    for m in msgs:
        role = (m.role or "").strip().lower()
        content = m.content if m.content is not None else ""
        if role == "compaction_summary":
            body = content if content.startswith(COMPACTION_SUMMARY_MARKER) else f"{COMPACTION_SUMMARY_MARKER}\n{content}"
            out.append({"role": "user", "content": body})
            continue
        if role in ("user", "assistant", "system"):
            out.append({"role": role, "content": content})
            continue
        # Unknown roles: treat as user so the model still sees the text
        out.append({"role": "user", "content": content})
    return out
