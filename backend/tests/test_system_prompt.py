"""SYSTEM.md / APPEND_SYSTEM.md override and append."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_window.config import settings


@pytest.fixture
def ws(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    from agent_window.services.workspace import set_workspace_root

    set_workspace_root(str(tmp_path))
    return tmp_path


def _build_prompt() -> str:
    from agent_window.api.routes import _system_prompt

    return _system_prompt()


def test_default_prompt_without_files(ws: Path) -> None:
    prompt = _build_prompt()
    assert "helpful coding assistant" in prompt
    assert "propose_edit" in prompt
    assert "propose_delete" in prompt
    assert "do not use rm" in prompt
    assert "read_attachment" in prompt
    # Attachment-only turns: read + verbal summary; no silent workspace writes.
    assert "（见附件）" in prompt
    assert "do NOT call propose_edit" in prompt
    assert "unless the user explicitly asks to write files" in prompt
    assert "invent helper scripts" in prompt
    # Must still allow writes when user explicitly asks.
    assert "create, edit, or run something" in prompt


def test_attachment_only_rule_absent_when_system_md_overrides(ws: Path) -> None:
    (ws / "SYSTEM.md").write_text("Custom only.", encoding="utf-8")
    prompt = _build_prompt()
    assert "Custom only." in prompt
    assert "（见附件）" not in prompt
    assert "do NOT call propose_edit" not in prompt


def test_system_md_replaces_default(ws: Path) -> None:
    (ws / "SYSTEM.md").write_text("You are a custom assistant. Always answer in English.", encoding="utf-8")
    prompt = _build_prompt()
    assert "custom assistant" in prompt
    assert "helpful coding assistant" not in prompt


def test_append_system_md_appends(ws: Path) -> None:
    (ws / "APPEND_SYSTEM.md").write_text("Always run tests after editing.", encoding="utf-8")
    prompt = _build_prompt()
    assert "helpful coding assistant" in prompt
    assert "Always run tests after editing." in prompt


def test_both_files_override_wins(ws: Path) -> None:
    (ws / "SYSTEM.md").write_text("Custom base.", encoding="utf-8")
    (ws / "APPEND_SYSTEM.md").write_text("Extra rule.", encoding="utf-8")
    prompt = _build_prompt()
    assert "Custom base." in prompt
    assert "Extra rule." in prompt
    assert "helpful coding assistant" not in prompt


def test_empty_system_md_falls_back(ws: Path) -> None:
    (ws / "SYSTEM.md").write_text("", encoding="utf-8")
    prompt = _build_prompt()
    assert "helpful coding assistant" in prompt
