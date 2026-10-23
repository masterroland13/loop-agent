"""LLM config adapter — active Model Registry profile + .env sync."""

from __future__ import annotations

import pytest

import agent_window.services.llm_config as llm_config
from agent_window.config import settings
from agent_window.services.llm_config import public_llm_config, save_llm_config
import agent_window.services.model_registry as registry


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    env = tmp_path / ".env"
    env.write_text(
        "APP_DATA_DIR=./data\n"
        "LLM_BASE_URL=https://old.example/v1\n"
        "LLM_API_KEY=old-key\n"
        "LLM_MODEL=old-model\n"
        "# keep this comment\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_config, "_env_path", lambda: env)
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr(settings, "llm_base_url", "https://old.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "old-key")
    monkeypatch.setattr(settings, "llm_model", "old-model")
    monkeypatch.setattr(settings, "llm_temperature", 0.7)
    monkeypatch.setattr(settings, "llm_max_tokens", 2048)
    return env


def test_public_config_hides_api_key(fake_env) -> None:
    public = public_llm_config()
    assert set(public) == {"api_key_configured", "base_url", "default_model", "temperature", "max_tokens"}
    assert "old-key" not in str(public)
    assert public["api_key_configured"] is True
    assert public["base_url"] == "https://old.example/v1"
    assert public["default_model"] == "old-model"
    assert public["temperature"] == pytest.approx(0.7)
    assert public["max_tokens"] == 2048


def test_save_writes_env_and_updates_settings(fake_env) -> None:
    saved = save_llm_config(
        {
            "base_url": "https://api.moonshot.cn/v1/",
            "api_key": "sk-new-secret",
            "default_model": "deepseek-v4-flash",
        }
    )
    text = fake_env.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=https://api.moonshot.cn/v1" in text
    assert "LLM_API_KEY=sk-new-secret" in text
    assert "LLM_MODEL=deepseek-v4-flash" in text
    assert "APP_DATA_DIR=./data" in text
    assert "# keep this comment" in text

    assert settings.llm_base_url == "https://api.moonshot.cn/v1"
    assert settings.llm_api_key == "sk-new-secret"
    assert settings.llm_model == "deepseek-v4-flash"
    assert "sk-new-secret" not in str(saved)

    # Active registry profile mirrors adapter save
    listed = registry.list_profiles_public()
    active = next(p for p in listed["profiles"] if p["id"] == listed["active_id"])
    assert active["base_url"] == "https://api.moonshot.cn/v1"
    assert active["model_id"] == "deepseek-v4-flash"
    assert active["api_key_configured"] is True


def test_partial_update_keeps_other_lines(fake_env) -> None:
    save_llm_config({"default_model": "deepseek-v4-pro"})
    text = fake_env.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=https://old.example/v1" in text
    assert "LLM_API_KEY=old-key" in text
    assert "LLM_MODEL=deepseek-v4-pro" in text


def test_invalid_base_url_rejected(fake_env) -> None:
    with pytest.raises(ValueError):
        save_llm_config({"base_url": "not-a-url"})


def test_empty_api_key_does_not_wipe(fake_env) -> None:
    # Ensure registry migrated first
    public_llm_config()
    save_llm_config({"api_key": "   "})
    text = fake_env.read_text(encoding="utf-8")
    assert "LLM_API_KEY=old-key" in text
    assert settings.llm_api_key == "old-key"
    listed = registry.list_profiles_public()
    active = next(p for p in listed["profiles"] if p["id"] == listed["active_id"])
    assert active["api_key_configured"] is True
    assert registry.get_profile(listed["active_id"])["api_key"] == "old-key"
