"""Extract model reasoning / thinking blocks for Cursor-style Thought UI.

Never invent CoT from tool names — only parse fields the provider actually returns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def extract_reasoning_text(message: Any) -> Tuple[str, str]:
    """Return ``(text, source)`` from an OpenAI-style chat message object or dict.

    Sources: ``reasoning_content`` | ``thinking`` | ``content_parts`` | ``none``.
    """
    if message is None:
        return "", "none"

    # dict form (tests / normalized)
    if isinstance(message, dict):
        return _from_dict(message)

    # SDK message object
    for attr, source in (
        ("reasoning_content", "reasoning_content"),
        ("reasoning", "reasoning"),
        ("thinking", "thinking"),
    ):
        val = getattr(message, attr, None)
        text = _as_text(val)
        if text:
            return text, source

    # pydantic v2 extras
    extra = getattr(message, "model_extra", None) or {}
    if isinstance(extra, dict):
        for key, source in (
            ("reasoning_content", "reasoning_content"),
            ("reasoning", "reasoning"),
            ("thinking", "thinking"),
        ):
            text = _as_text(extra.get(key))
            if text:
                return text, source

    content = getattr(message, "content", None)
    parts_text, parts_source = _from_content_parts(content)
    if parts_text:
        return parts_text, parts_source

    return "", "none"


def _from_dict(message: Dict[str, Any]) -> Tuple[str, str]:
    for key, source in (
        ("reasoning_content", "reasoning_content"),
        ("reasoning", "reasoning"),
        ("thinking", "thinking"),
    ):
        text = _as_text(message.get(key))
        if text:
            return text, source
    parts_text, parts_source = _from_content_parts(message.get("content"))
    if parts_text:
        return parts_text, parts_source
    return "", "none"


def _from_content_parts(content: Any) -> Tuple[str, str]:
    """Anthropic-style / multimodal content arrays with thinking blocks."""
    if not isinstance(content, list):
        return "", "none"
    chunks: List[str] = []
    for part in content:
        if not isinstance(part, dict):
            # SDK objects
            ptype = getattr(part, "type", None)
            if ptype in ("thinking", "reasoning"):
                text = _as_text(
                    getattr(part, "thinking", None)
                    or getattr(part, "text", None)
                    or getattr(part, "reasoning", None)
                )
                if text:
                    chunks.append(text)
            continue
        ptype = str(part.get("type") or "")
        if ptype in ("thinking", "reasoning"):
            text = _as_text(
                part.get("thinking") or part.get("text") or part.get("reasoning")
            )
            if text:
                chunks.append(text)
    if not chunks:
        return "", "none"
    return "\n\n".join(chunks).strip(), "content_parts"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        # nested parts
        text, _ = _from_content_parts(value)
        return text
    return str(value).strip()


def visible_text_content(message: Any) -> str:
    """User-visible assistant text, excluding thinking parts when content is a list."""
    if message is None:
        return ""
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                ptype = str(part.get("type") or "text")
                if ptype in ("thinking", "reasoning"):
                    continue
                if ptype in ("text", "output_text") or "text" in part:
                    t = _as_text(part.get("text"))
                    if t:
                        texts.append(t)
            else:
                ptype = getattr(part, "type", None)
                if ptype in ("thinking", "reasoning"):
                    continue
                t = _as_text(getattr(part, "text", None))
                if t:
                    texts.append(t)
        return "\n".join(texts).strip()
    return "" if content is None else str(content)


def reasoning_modes() -> frozenset[str]:
    return frozenset({"none", "openai_compatible", "auto"})


def normalize_reasoning_mode(raw: Any) -> str:
    value = str(raw or "none").strip().lower()
    if value in reasoning_modes():
        return value
    return "none"


def completion_extra_body_for_reasoning(
    *,
    supports_reasoning: bool,
    reasoning_mode: str,
) -> Optional[Dict[str, Any]]:
    """Optional request hints some gateways need to emit reasoning_content.

    Conservative: only when profile opts in. Unknown gateways simply ignore extras.
    """
    if not supports_reasoning:
        return None
    mode = normalize_reasoning_mode(reasoning_mode)
    if mode == "none":
        return None
    # Common OpenAI-compatible / DeepSeek / Kimi gateway knobs (best-effort).
    return {
        "include_reasoning": True,
    }
