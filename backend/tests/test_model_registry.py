"""Model Registry — multi-profile Base URL / Key / model (A2)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent_window.config import settings
import agent_window.services.model_registry as registry
from agent_window.services.llm_config import public_llm_config, save_llm_config
import agent_window.services.llm_config as llm_config


@pytest.fixture
def registry_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    env = tmp_path / ".env"
    env.write_text(
        "APP_DATA_DIR=./data\n"
        "LLM_BASE_URL=https://old.example/v1\n"
        "LLM_API_KEY=old-key\n"
        "LLM_MODEL=old-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    monkeypatch.setattr(settings, "llm_base_url", "https://seed.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "seed-secret")
    monkeypatch.setattr(settings, "llm_model", "seed-model")
    monkeypatch.setattr(settings, "llm_temperature", 0.7)
    monkeypatch.setattr(settings, "llm_max_tokens", 2048)
    monkeypatch.setattr(llm_config, "_env_path", lambda: env)
    return data, env


def test_migrate_seeds_from_settings(registry_env) -> None:
    data, _env = registry_env
    path = data / "model_profiles.json"
    assert not path.exists()

    public = registry.list_profiles_public()
    assert path.exists()
    assert len(public["profiles"]) == 1
    assert public["profiles"][0]["label"] == "OpenAI Compatible"
    assert public["profiles"][0]["base_url"] == "https://seed.example/v1"
    assert public["profiles"][0]["model_id"] == "seed-model"
    assert public["profiles"][0]["api_key_configured"] is True
    assert "seed-secret" not in json.dumps(public)
    assert "api_key" not in public["profiles"][0]
    assert public["active_id"] == public["profiles"][0]["id"]
    assert public["temperature"] == pytest.approx(0.7)
    assert public["max_tokens"] == 2048

    # reverse: raw file still holds the key for provider use
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["profiles"][0]["api_key"] == "seed-secret"
    assert "seed-secret" not in str(public)


def test_create_second_activate_public_hides_keys(registry_env) -> None:
    registry.list_profiles_public()  # migrate
    second = registry.create_profile(
        label="LiteLLM",
        base_url="https://litellm.example/v1",
        api_key="litellm-key",
        model_id="kimi-for-coding",
        activate=True,
    )
    assert second["label"] == "LiteLLM"
    assert second["api_key_configured"] is True
    assert "litellm-key" not in str(second)
    assert "api_key" not in second

    listed = registry.list_profiles_public()
    assert listed["active_id"] == second["id"]
    assert len(listed["profiles"]) == 2
    assert all("api_key" not in p for p in listed["profiles"])
    assert "litellm-key" not in json.dumps(listed)
    assert "seed-secret" not in json.dumps(listed)

    handle = registry.resolve_active_handle()
    assert handle is not None
    assert handle.profile_id == second["id"]
    assert handle.model_id == "kimi-for-coding"
    assert handle.base_url == "https://litellm.example/v1"
    assert not hasattr(handle, "api_key") or getattr(handle, "api_key", None) is None
    # ModelHandle has no api_key field
    assert "api_key" not in handle.__dataclass_fields__

    # reverse: inactive first profile still present and not active
    first_id = next(p["id"] for p in listed["profiles"] if p["id"] != second["id"])
    assert listed["active_id"] != first_id


def test_update_key_configured_empty_does_not_wipe(registry_env) -> None:
    listed = registry.list_profiles_public()
    pid = listed["profiles"][0]["id"]
    assert listed["profiles"][0]["api_key_configured"] is True

    updated = registry.update_profile(pid, {"api_key": "new-secret-key"})
    assert updated["api_key_configured"] is True
    assert "new-secret-key" not in str(updated)
    assert registry.get_profile(pid)["api_key"] == "new-secret-key"

    registry.update_profile(pid, {"api_key": "   "})
    assert registry.get_profile(pid)["api_key"] == "new-secret-key"
    assert registry.list_profiles_public()["profiles"][0]["api_key_configured"] is True

    # reverse: blank does not clear configured flag
    wiped_attempt = registry.update_profile(pid, {"api_key": ""})
    assert wiped_attempt["api_key_configured"] is True
    assert registry.get_profile(pid)["api_key"] == "new-secret-key"


def test_delete_last_rejected(registry_env) -> None:
    listed = registry.list_profiles_public()
    only_id = listed["profiles"][0]["id"]
    with pytest.raises(ValueError, match="最后"):
        registry.delete_profile(only_id)
    assert len(registry.list_profiles_public()["profiles"]) == 1

    second = registry.create_profile(label="B", model_id="m2")
    after = registry.delete_profile(only_id)
    assert len(after["profiles"]) == 1
    assert after["profiles"][0]["id"] == second["id"]
    assert after["active_id"] == second["id"]
    # reverse: deleted id gone
    assert only_id not in {p["id"] for p in after["profiles"]}


def test_delete_active_activates_another(registry_env) -> None:
    a = registry.list_profiles_public()["profiles"][0]
    b = registry.create_profile(label="B", model_id="m2", activate=True)
    assert registry.list_profiles_public()["active_id"] == b["id"]
    after = registry.delete_profile(b["id"])
    assert after["active_id"] == a["id"]
    assert b["id"] not in {p["id"] for p in after["profiles"]}


def test_llm_config_adapter_updates_active(registry_env) -> None:
    registry.list_profiles_public()
    second = registry.create_profile(
        label="Other",
        base_url="https://other.example/v1",
        api_key="other-key",
        model_id="other-model",
        activate=True,
    )
    saved = save_llm_config(
        {
            "base_url": "https://adapter.example/v1/",
            "api_key": "adapter-key",
            "default_model": "adapter-model",
            "temperature": 0.3,
            "max_tokens": 4096,
        }
    )
    assert saved["base_url"] == "https://adapter.example/v1"
    assert saved["default_model"] == "adapter-model"
    assert saved["api_key_configured"] is True
    assert "adapter-key" not in str(saved)
    assert saved["temperature"] == pytest.approx(0.3)
    assert saved["max_tokens"] == 4096

    listed = registry.list_profiles_public()
    assert listed["active_id"] == second["id"]
    active = next(p for p in listed["profiles"] if p["id"] == second["id"])
    assert active["base_url"] == "https://adapter.example/v1"
    assert active["model_id"] == "adapter-model"
    assert registry.get_profile(second["id"])["api_key"] == "adapter-key"

    public = public_llm_config()
    assert public["base_url"] == "https://adapter.example/v1"
    assert public["default_model"] == "adapter-model"
    assert "adapter-key" not in str(public)

    # reverse: inactive profile unchanged
    other = next(p for p in listed["profiles"] if p["id"] != second["id"])
    assert other["base_url"] == "https://seed.example/v1"
    assert other["model_id"] == "seed-model"


def test_disabled_active_falls_back_to_enabled(registry_env) -> None:
    first = registry.list_profiles_public()["profiles"][0]
    second = registry.create_profile(
        label="Alt",
        base_url="https://alt.example/v1",
        api_key="alt-key",
        model_id="alt-model",
        activate=False,
    )
    registry.update_profile(first["id"], {"enabled": False})
    registry.set_active(first["id"])
    handle = registry.resolve_active_handle()
    assert handle is not None
    assert handle.profile_id == second["id"]
    assert handle.model_id == "alt-model"
    # reverse: disabled active is not chosen
    assert handle.profile_id != first["id"]


def test_presets_match_current_vendor_examples() -> None:
    from agent_window.services.provider_presets import list_provider_presets

    rows = list_provider_presets()
    by_id = {row["id"]: row for row in rows}
    required = {
        "router",
        "moonshot",
        "deepseek",
        "openrouter",
        "openai",
        "groq",
        "together",
        "siliconflow",
        "zhipu",
        "dashscope",
    }
    assert required <= set(by_id)
    assert len(by_id) == len(rows)
    assert by_id["moonshot"]["base_url"] == "https://api.moonshot.cn/v1"
    assert by_id["moonshot"]["model_id"] == "kimi-k3"
    assert by_id["moonshot"]["inherit_base_url"] is False
    assert by_id["deepseek"]["base_url"] == "https://api.deepseek.com"
    assert by_id["deepseek"]["model_id"] == "deepseek-flash"
    assert "deepseek-v4" not in by_id["deepseek"]["model_id"]
    assert by_id["groq"]["base_url"] == "https://api.groq.com/openai/v1"
    assert by_id["groq"]["model_id"] == "openai/gpt-oss-120b"
    assert by_id["groq"]["model_id"] != "llama-3.3-70b-versatile"
    assert by_id["together"]["base_url"] == "https://api.together.ai/v1"
    assert by_id["together"]["base_url"] != "https://api.together.xyz/v1"
    assert by_id["router"]["inherit_base_url"] is True
    assert by_id["router"]["model_id"] == "kimi-k3"
    assert by_id["router"]["base_url"] == ""
    for row in rows:
        if row["id"] != "router":
            assert row["inherit_base_url"] is False
            assert row["base_url"].startswith("https://")
    blob = json.dumps(rows)
    assert "api_key" not in blob
    assert "sk-" not in blob


def test_preset_add_moonshot_fills_url_router_inherits_active(registry_env) -> None:
    from agent_window.services.provider_presets import list_provider_presets

    rows = {row["id"]: row for row in list_provider_presets()}
    seeded = registry.list_profiles_public()
    active_id = seeded["active_id"]
    active = next(p for p in seeded["profiles"] if p["id"] == active_id)
    moon = rows["moonshot"]
    created = registry.create_profile(
        label=moon["label"],
        base_url=moon["base_url"],
        model_id=moon["model_id"],
        activate=False,
    )
    assert created["base_url"] == "https://api.moonshot.cn/v1"
    assert created["model_id"] == "kimi-k3"
    assert created["api_key_configured"] is False
    assert "api_key" not in created
    assert registry.list_profiles_public()["active_id"] == active_id
    assert created["id"] != active_id

    router = rows["router"]
    blank = registry.create_profile(
        label=router["label"],
        model_id=router["model_id"],
        activate=False,
    )
    assert blank["base_url"] == active["base_url"]
    assert blank["base_url"] == "https://seed.example/v1"
    assert blank["base_url"] != created["base_url"]
    assert blank["model_id"] == "kimi-k3"
    assert blank["api_key_configured"] is False
    assert registry.list_profiles_public()["active_id"] == active_id


def test_turn_binding_keeps_override_and_falls_back_when_disabled(registry_env) -> None:
    listed = registry.list_profiles_public()
    active_id = listed["active_id"]
    other = registry.create_profile(
        label="Other",
        base_url="https://other.example/v1",
        api_key="other-key",
        model_id="other-model",
        activate=False,
    )
    kept = registry.resolve_turn_binding(other["id"], "other-model", "custom-on-other")
    assert kept["fallback"] is False
    assert kept["profile_id"] == other["id"]
    assert kept["model_id"] == "custom-on-other"
    assert kept["model_id"] != "other-model"

    registry.update_profile(other["id"], {"enabled": False})
    fallen = registry.resolve_turn_binding(other["id"], "custom-on-other", "custom-on-other")
    assert fallen["fallback"] is True
    assert fallen["profile_id"] == active_id
    assert fallen["model_id"] == "seed-model"
    assert fallen["profile_id"] != other["id"]
    assert "other-key" not in json.dumps(fallen)

    legacy = registry.resolve_turn_binding(None, None, "from-picker")
    assert legacy["fallback"] is False
    assert legacy["profile_id"] == active_id
    assert legacy["model_id"] == "from-picker"


def test_profile_clients_do_not_share_gateway_or_settings(registry_env) -> None:
    from agent_window.services.provider import LLMProvider

    registry.list_profiles_public()
    first = registry.create_profile(
        label="A",
        base_url="https://a.example/v1",
        api_key="key-a",
        model_id="model-a",
        activate=False,
    )
    second = registry.create_profile(
        label="B",
        base_url="https://b.example/v1",
        api_key="key-b",
        model_id="model-b",
        activate=False,
    )
    prov = LLMProvider()
    client_a, model_a = prov._client_for_profile(first["id"])
    client_b, model_b = prov._client_for_profile(second["id"])
    assert str(client_a.base_url).rstrip("/") == "https://a.example/v1"
    assert str(client_b.base_url).rstrip("/") == "https://b.example/v1"
    assert client_a is not client_b
    assert model_a == "model-a"
    assert model_b == "model-b"
    assert model_a != model_b
    assert settings.llm_base_url == "https://seed.example/v1"
    assert settings.llm_api_key == "seed-secret"
    assert settings.llm_base_url != "https://b.example/v1"

    from agent_window.services.provider import turn_profile_id

    token = turn_profile_id.set(second["id"])
    try:
        via_context, via_model = prov._client_for_profile(None)
    finally:
        turn_profile_id.reset(token)
    assert via_context is client_b
    assert via_model == "model-b"
    assert via_context is not client_a

    ready = LLMProvider()
    empty = registry.create_profile(
        label="Empty",
        base_url="https://empty.example/v1",
        api_key="",
        model_id="empty-model",
        activate=False,
    )
    assert ready.profile_is_ready(second["id"]) is True
    assert ready.profile_is_ready(empty["id"]) is False
    assert ready.profile_is_ready(None) is True
    assert settings.llm_api_key == "seed-secret"
    assert settings.llm_base_url != "https://b.example/v1"


def test_chat_complete_uses_named_profile_not_active_settings(registry_env) -> None:
    from agent_window.services.provider import LLMProvider, turn_profile_id

    registry.list_profiles_public()
    second = registry.create_profile(
        label="B",
        base_url="https://b.example/v1",
        api_key="key-b",
        model_id="model-b",
        activate=False,
    )
    prov = LLMProvider()
    client_b, _ = prov._client_for_profile(second["id"])
    seen: dict[str, str] = {}

    async def fake_create(**kwargs):
        seen["model"] = str(kwargs.get("model") or "")
        seen["base"] = str(client_b.base_url)
        message = SimpleNamespace(content="from-b", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

    client_b.chat.completions.create = fake_create
    token = turn_profile_id.set(None)
    try:
        out = asyncio.run(
            prov.chat_complete(
                [{"role": "user", "content": "hi"}],
                profile_id=second["id"],
            )
        )
    finally:
        turn_profile_id.reset(token)
    assert seen["model"] == "model-b"
    assert "b.example" in seen["base"]
    assert "a.example" not in seen["base"]
    assert out["content"] == "from-b"
    assert "key-b" not in json.dumps(out)
    assert settings.llm_base_url == "https://seed.example/v1"
    assert settings.llm_api_key == "seed-secret"


def test_credentials_not_on_handle(registry_env) -> None:
    registry.list_profiles_public()
    handle = registry.resolve_active_handle()
    creds = registry.resolve_credentials(handle.profile_id if handle else None)
    assert creds["api_key"] == "seed-secret"
    assert handle is not None
    dumped = str(handle)
    assert "seed-secret" not in dumped
