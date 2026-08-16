"""Context compression helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def approx_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def approx_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += approx_tokens(content)
        total += 4  # role overhead
    return total


async def compress_messages_if_needed(
    messages: List[Dict[str, Any]],
    *,
    auto_compress: bool,
    context_limit: int,
    summarize=None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    If over limit and auto_compress, fold older user/assistant turns into one system summary.
    `summarize` is an optional async callable(str) -> str.
    Returns (messages, compressed_flag).
    """
    if not auto_compress:
        return messages, False

    tokens = approx_messages_tokens(messages)
    if tokens <= context_limit:
        return messages, False

    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    if len(rest) <= 4:
        # keep last 2 turns; drop older if still over
        keep = rest[-4:]
        return system + keep, True

    # Keep newest 4 messages; summarize the rest
    older = rest[:-4]
    recent = rest[-4:]
    blob_lines = []
    for m in older:
        role = m.get("role", "?")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        blob_lines.append(f"{role}: {content[:800]}")
    blob = "\n".join(blob_lines)[:12000]

    summary_text = ""
    if summarize is not None:
        try:
            summary_text = (await summarize(blob)).strip()
        except Exception:
            logger.exception("LLM summarize failed; falling back to truncation")

    if not summary_text:
        summary_text = blob[:2000]

    summary_msg = {
        "role": "system",
        "content": (
            "以下是更早对话的压缩摘要（自动压缩）：\n" + summary_text
        ),
    }
    return system + [summary_msg] + recent, True
