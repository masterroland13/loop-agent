"""Draft helpers for chat attachments (mirrors src/utils/chatAttachment.ts)."""

from __future__ import annotations


def draft_content_for_send(user_text: str) -> str:
    return user_text.strip()


def can_send_draft(user_text: str, attachments: list[dict]) -> bool:
    ready = [a for a in attachments if a.get("status") == "ready"]
    pending = any(a.get("status") == "pending" for a in attachments)
    if pending:
        return False
    if ready:
        return True
    return bool(user_text.strip())


def test_draft_content_is_trim_only() -> None:
    assert draft_content_for_send("  hello  ") == "hello"
    assert draft_content_for_send("") == ""
    assert "---" not in draft_content_for_send("notes")
    assert "附件" not in draft_content_for_send("x")


def test_can_send_with_ready_attachment_only() -> None:
    assert can_send_draft("", [{"name": "a.txt", "status": "ready", "id": "1"}])
    assert not can_send_draft("", [])
    assert not can_send_draft("", [{"name": "a.txt", "status": "pending"}])
    assert not can_send_draft("", [{"name": "a.txt", "status": "error"}])
    assert can_send_draft("hi", [])
    assert not can_send_draft("", [{"name": "a", "status": "ready"}, {"name": "b", "status": "pending"}])
