"""agent_settings persistence + clamping."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "agent_window.services.agent_settings.settings.app_data_dir",
        tmp_path,
    )
    return tmp_path


def test_max_tool_iters_default_and_clamp(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings

    loaded = load_agent_settings()
    assert loaded["max_tool_iters"] == 24
    assert "max_tool_iters" in loaded
    # Should not expose raw junk keys as behavior
    assert loaded["max_tool_iters"] >= 8
    assert loaded["max_tool_iters"] <= 64

    saved = save_agent_settings({"max_tool_iters": 3})
    assert saved["max_tool_iters"] == 8
    assert load_agent_settings()["max_tool_iters"] == 8

    saved = save_agent_settings({"max_tool_iters": 999})
    assert saved["max_tool_iters"] == 64
    assert load_agent_settings()["max_tool_iters"] != 999
    assert load_agent_settings()["max_tool_iters"] == 64

    saved = save_agent_settings({"max_tool_iters": 32})
    assert saved["max_tool_iters"] == 32
    assert load_agent_settings()["max_tool_iters"] == 32


def test_max_tool_iters_invalid_falls_back(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings

    path = data_dir / "agent_settings.json"
    path.write_text('{"max_tool_iters": "nope"}', encoding="utf-8")
    loaded = load_agent_settings()
    assert loaded["max_tool_iters"] == 24
    assert loaded["max_tool_iters"] != "nope"


def test_loop_preset_default_yolo_and_save(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings

    loaded = load_agent_settings()
    assert loaded["loop_preset"] == "yolo"
    assert loaded["loop_preset"] != "trusted"

    saved = save_agent_settings({"loop_preset": "trusted"})
    assert saved["loop_preset"] == "trusted"
    assert load_agent_settings()["loop_preset"] == "trusted"
    assert load_agent_settings()["loop_preset"] != "yolo"

    saved = save_agent_settings({"loop_preset": "STRICT"})
    assert saved["loop_preset"] == "strict"


def test_loop_preset_invalid_falls_back_to_yolo(data_dir: Path) -> None:
    from agent_window.services.agent_settings import load_agent_settings, save_agent_settings

    path = data_dir / "agent_settings.json"
    path.write_text('{"loop_preset": "chaos"}', encoding="utf-8")
    loaded = load_agent_settings()
    assert loaded["loop_preset"] == "yolo"
    assert loaded["loop_preset"] != "chaos"

    saved = save_agent_settings({"loop_preset": "not-a-preset"})
    assert saved["loop_preset"] == "yolo"
    assert saved["loop_preset"] != "not-a-preset"
