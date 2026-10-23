"""P2 image multimodal — payload shape, vision model route, image limits."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_window.config import settings
from agent_window.services.attachments import (
    AttachmentError,
    MAX_ATTACHMENT_BYTES,
    MAX_IMAGE_ATTACHMENT_BYTES,
    build_user_chat_message,
    is_image_meta,
    read_attachment_text,
    resolve_model_for_attachments,
    save_upload,
)

# Minimal 1×1 PNG
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def session_dir(tmp_path, monkeypatch):
    att = tmp_path / "attachments"
    att.mkdir()
    monkeypatch.setattr(
        "agent_window.services.attachments.attachments_dir",
        lambda _session: att,
    )
    session = SimpleNamespace(id="s1", data_path="sess")
    return SimpleNamespace(session=session, attachments=att)


def test_is_image_meta_accepts_png_rejects_svg() -> None:
    assert is_image_meta({"filename": "a.png", "content_type": "image/png"})
    assert is_image_meta({"filename": "a.JPG", "content_type": None})
    assert not is_image_meta({"filename": "a.svg", "content_type": "image/svg+xml"})
    assert not is_image_meta({"filename": "a.txt", "content_type": "text/plain"})
    assert not is_image_meta(None)


def test_build_user_chat_message_injects_image_url(session_dir) -> None:
    meta = save_upload(session_dir.session, "dot.png", PNG_1X1, "image/png")
    msg = build_user_chat_message(session_dir.session, "图里有什么", [meta])
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    types = [p.get("type") for p in msg["content"]]
    assert "text" in types
    assert "image_url" in types
    assert "tool_call" not in types
    text_part = next(p for p in msg["content"] if p["type"] == "text")
    assert "图里有什么" in text_part["text"]
    assert "视觉" in text_part["text"]
    assert "read_attachment" in text_part["text"]  # appendix says don't use it on images
    img_part = next(p for p in msg["content"] if p["type"] == "image_url")
    url = img_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert PNG_1X1.hex()[:16] not in url  # data url is base64, not raw hex dump as text file

    text_only = build_user_chat_message(session_dir.session, "hi", [])
    assert text_only["content"] == "hi"
    assert isinstance(text_only["content"], str)
    assert not isinstance(text_only["content"], list)


def test_resolve_model_routes_images_to_vision(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "kimi-k3")
    monkeypatch.setattr(settings, "llm_vision_model", "deepseek-v4-flash-vision-exp")
    img = [{"id": "1", "filename": "x.png", "content_type": "image/png"}]
    assert resolve_model_for_attachments("kimi-k3", img) == "deepseek-v4-flash-vision-exp"
    assert (
        resolve_model_for_attachments("kimi-k3", img, vision_model="my-vision-model")
        == "my-vision-model"
    )
    assert resolve_model_for_attachments("foo-vision-bar", img) == "foo-vision-bar"
    assert resolve_model_for_attachments("kimi-k3", []) == "kimi-k3"
    assert resolve_model_for_attachments(None, None) == "kimi-k3"
    assert resolve_model_for_attachments("kimi-k3", img) != "kimi-k3"


def test_resolve_model_requires_vision_when_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "kimi-k3")
    monkeypatch.setattr(settings, "llm_vision_model", "")
    img = [{"id": "1", "filename": "x.png", "content_type": "image/png"}]
    with pytest.raises(AttachmentError) as ei:
        resolve_model_for_attachments("kimi-k3", img, vision_model="")
    assert ei.value.code == "VISION_MODEL_REQUIRED"
    assert "vision" in str(ei.value).lower()
    assert resolve_model_for_attachments("kimi-k3", [], vision_model="") == "kimi-k3"
    assert ei.value.code != "TOO_LARGE"


def test_image_upload_allows_above_text_limit(session_dir) -> None:
    assert MAX_IMAGE_ATTACHMENT_BYTES > MAX_ATTACHMENT_BYTES
    blob = PNG_1X1 + (b"\x00" * (MAX_ATTACHMENT_BYTES + 1 - len(PNG_1X1)))
    assert len(blob) > MAX_ATTACHMENT_BYTES
    assert len(blob) <= MAX_IMAGE_ATTACHMENT_BYTES
    meta = save_upload(session_dir.session, "big.png", blob, "image/png")
    assert meta["filename"] == "big.png"
    assert meta["size"] == len(blob)

    with pytest.raises(AttachmentError) as ei:
        save_upload(
            session_dir.session,
            "big.txt",
            b"x" * (MAX_ATTACHMENT_BYTES + 1),
            "text/plain",
        )
    assert ei.value.code == "TOO_LARGE"
    assert ei.value.code != "EMPTY_FILE"


def test_image_upload_rejects_over_image_limit(session_dir) -> None:
    huge = PNG_1X1 + (b"\x00" * (MAX_IMAGE_ATTACHMENT_BYTES + 1 - len(PNG_1X1)))
    with pytest.raises(AttachmentError) as ei:
        save_upload(session_dir.session, "huge.png", huge, "image/png")
    assert ei.value.code == "TOO_LARGE"
    assert "large" in str(ei.value).lower() or "max" in str(ei.value).lower()


def test_read_attachment_text_rejects_image(session_dir) -> None:
    meta = save_upload(session_dir.session, "dot.png", PNG_1X1, "image/png")
    with pytest.raises(AttachmentError) as ei:
        read_attachment_text(session_dir.session, meta["id"])
    assert ei.value.code == "NOT_TEXT"
    assert "vision" in str(ei.value).lower() or "image" in str(ei.value).lower()
    assert ei.value.code != "NOT_FOUND"
