"""Tests for agent_window.cli.config.load_cli_config defaults."""

from __future__ import annotations

import json

import pytest

from agent_window.cli import config as cli_config
from agent_window.cli.config import (
    DEFAULT_BASE,
    DEFAULT_TIMEOUT,
    load_cli_config,
)


@pytest.fixture
def no_env_no_file(monkeypatch, tmp_path) -> None:
    """Ensure neither env var nor config file influence the result."""
    monkeypatch.delenv("AGENT_BASE_URL", raising=False)
    monkeypatch.setattr(
        cli_config, "CONFIG_PATH", tmp_path / "missing" / "config.json"
    )
    monkeypatch.setattr(
        cli_config, "LEGACY_CONFIG_PATH", tmp_path / "missing-legacy" / "config.json"
    )


def test_defaults_when_no_env_and_no_file(no_env_no_file) -> None:
    cfg = load_cli_config()

    assert set(cfg) == {"base_url", "timeout", "default_model", "auto_approve"}
    assert cfg["base_url"] == DEFAULT_BASE == "http://127.0.0.1:8000"
    assert cfg["timeout"] == DEFAULT_TIMEOUT == 120.0
    assert cfg["default_model"] is None
    assert cfg["auto_approve"] is False


def test_defaults_used_when_file_has_empty_dict(no_env_no_file, monkeypatch) -> None:
    monkeypatch.setattr(cli_config, "_load_config_file", lambda: {})

    cfg = load_cli_config()

    assert cfg["base_url"] == DEFAULT_BASE
    assert cfg["timeout"] == DEFAULT_TIMEOUT
    assert cfg["default_model"] is None
    assert cfg["auto_approve"] is False


def test_legacy_config_used_when_new_file_missing(no_env_no_file, monkeypatch, tmp_path) -> None:
    legacy = tmp_path / "hal-agent" / "config.json"
    legacy.parent.mkdir()
    legacy.write_text(
        json.dumps({"base_url": "https://legacy.example", "timeout": 30}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_config, "LEGACY_CONFIG_PATH", legacy)

    cfg = load_cli_config()

    assert cfg["base_url"] == "https://legacy.example"
    assert cfg["timeout"] == 30.0


def test_new_config_wins_over_legacy(no_env_no_file, monkeypatch, tmp_path) -> None:
    new_file = tmp_path / "loop-agent" / "config.json"
    legacy = tmp_path / "hal-agent" / "config.json"
    new_file.parent.mkdir()
    legacy.parent.mkdir()
    new_file.write_text(json.dumps({"base_url": "https://new.example"}), encoding="utf-8")
    legacy.write_text(json.dumps({"base_url": "https://legacy.example"}), encoding="utf-8")
    monkeypatch.setattr(cli_config, "CONFIG_PATH", new_file)
    monkeypatch.setattr(cli_config, "LEGACY_CONFIG_PATH", legacy)

    cfg = load_cli_config()

    assert cfg["base_url"] == "https://new.example"
    assert cfg["base_url"] != "https://legacy.example"


def test_defaults_ignored_when_env_var_set(no_env_no_file, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_BASE_URL", "https://env.example")

    cfg = load_cli_config()

    assert cfg["base_url"] == "https://env.example"
    assert cfg["timeout"] == DEFAULT_TIMEOUT
