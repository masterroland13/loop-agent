"""Reasoning / Thought extraction (S1)."""

from __future__ import annotations

from types import SimpleNamespace

from agent_window.services.reasoning import (
    completion_extra_body_for_reasoning,
    extract_reasoning_text,
    visible_text_content,
)


def test_extract_reasoning_content_attr():
    msg = SimpleNamespace(
        content="final answer",
        reasoning_content="step by step plan",
        tool_calls=None,
    )
    text, source = extract_reasoning_text(msg)
    assert text == "step by step plan"
    assert source == "reasoning_content"
    assert visible_text_content(msg) == "final answer"
    assert text != "final answer"


def test_extract_from_dict_and_content_parts():
    text, source = extract_reasoning_text(
        {
            "content": [
                {"type": "thinking", "thinking": "I will read the file"},
                {"type": "text", "text": "Done."},
            ]
        }
    )
    assert "read the file" in text
    assert source == "content_parts"
    assert (
        visible_text_content(
            {
                "content": [
                    {"type": "thinking", "thinking": "secret"},
                    {"type": "text", "text": "Done."},
                ]
            }
        )
        == "Done."
    )
    assert "secret" not in visible_text_content(
        {
            "content": [
                {"type": "thinking", "thinking": "secret"},
                {"type": "text", "text": "Done."},
            ]
        }
    )


def test_no_fake_reasoning_when_absent():
    text, source = extract_reasoning_text({"content": "hello", "role": "assistant"})
    assert text == ""
    assert source == "none"


def test_extra_body_only_when_opted_in():
    assert completion_extra_body_for_reasoning(
        supports_reasoning=False, reasoning_mode="openai_compatible"
    ) is None
    body = completion_extra_body_for_reasoning(
        supports_reasoning=True, reasoning_mode="openai_compatible"
    )
    assert body is not None
    assert body.get("include_reasoning") is True
    assert completion_extra_body_for_reasoning(
        supports_reasoning=True, reasoning_mode="none"
    ) is None
