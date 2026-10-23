"""Model Registry — multi-profile Base URL / API Key / model_id (charter A2).

Persists under ``settings.app_data_dir / model_profiles.json``.
Raw API keys never leave this module via public list APIs.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings
from agent_window.services.reasoning import normalize_reasoning_mode

logger = logging.getLogger(__name__)

_CONFIG_NAME = "model_profiles.json"
_DEFAULT_API = "openai-completions"
_DEFAULT_LABEL = "OpenAI Compatible"


@dataclass(frozen=True)
class ModelHandle:
    """Public handle for core/loop — no API key."""

    profile_id: str
    model_id: str
    api: str
    base_url: str


def _path() -> Path:
    return Path(settings.app_data_dir) / _CONFIG_NAME


def _normalize_base_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    return value


def _normalize_model(model: str) -> str:
    value = (model or "").strip()
    if not value:
        raise ValueError("模型 id 不能为空")
    return value


def _normalize_label(label: str) -> str:
    value = (label or "").strip()
    return value or _DEFAULT_LABEL


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _seed_from_settings() -> Dict[str, Any]:
    profile_id = _new_id()
    return {
        "version": 1,
        "active_id": profile_id,
        "temperature": float(settings.llm_temperature),
        "max_tokens": int(settings.llm_max_tokens),
        "profiles": [
            {
                "id": profile_id,
                "label": _DEFAULT_LABEL,
                "enabled": True,
                "base_url": (settings.llm_base_url or "").rstrip("/"),
                "api_key": str(settings.llm_api_key or ""),
                "model_id": settings.llm_model or "kimi-k3",
                "api": _DEFAULT_API,
                "supports_reasoning": False,
                "reasoning_mode": "none",
            }
        ],
    }


def _default_empty() -> Dict[str, Any]:
    """Fallback empty store (still one profile so delete-last stays meaningful)."""
    return _seed_from_settings()


def _validate_store(data: Dict[str, Any]) -> Dict[str, Any]:
    profiles = data.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return _default_empty()
    cleaned: List[Dict[str, Any]] = []
    for raw in profiles:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "").strip() or _new_id()
        cleaned.append(
            {
                "id": pid,
                "label": _normalize_label(str(raw.get("label") or "")),
                "enabled": bool(raw.get("enabled", True)),
                "base_url": str(raw.get("base_url") or "").rstrip("/"),
                "api_key": str(raw.get("api_key") or ""),
                "model_id": str(raw.get("model_id") or "").strip() or "kimi-k3",
                "api": str(raw.get("api") or _DEFAULT_API).strip() or _DEFAULT_API,
                "supports_reasoning": bool(raw.get("supports_reasoning", False)),
                "reasoning_mode": normalize_reasoning_mode(raw.get("reasoning_mode")),
            }
        )
    if not cleaned:
        return _default_empty()
    active = str(data.get("active_id") or "").strip()
    ids = {p["id"] for p in cleaned}
    if active not in ids:
        active = cleaned[0]["id"]
    try:
        temp = float(data.get("temperature", settings.llm_temperature))
    except (TypeError, ValueError):
        temp = float(settings.llm_temperature)
    temp = max(0.0, min(2.0, temp))
    try:
        tokens = int(data.get("max_tokens", settings.llm_max_tokens))
    except (TypeError, ValueError):
        tokens = int(settings.llm_max_tokens)
    tokens = max(256, min(200000, tokens))
    return {
        "version": 1,
        "active_id": active,
        "temperature": temp,
        "max_tokens": tokens,
        "profiles": cleaned,
    }


def _load_raw() -> Dict[str, Any]:
    path = _path()
    if not path.exists():
        data = _seed_from_settings()
        _save_raw(data)
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("not a dict")
        return _validate_store(raw)
    except Exception:
        logger.exception("model_profiles.json corrupt; re-seeding from settings")
        data = _seed_from_settings()
        _save_raw(data)
        return data


def _save_raw(data: Dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_store() -> Dict[str, Any]:
    return _load_raw()


def _profile_public(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": p["id"],
        "label": p["label"],
        "enabled": bool(p["enabled"]),
        "base_url": p["base_url"],
        "model_id": p["model_id"],
        "api": p.get("api") or _DEFAULT_API,
        "api_key_configured": bool(str(p.get("api_key") or "").strip()),
        "supports_reasoning": bool(p.get("supports_reasoning", False)),
        "reasoning_mode": normalize_reasoning_mode(p.get("reasoning_mode")),
    }


def list_profiles_public() -> Dict[str, Any]:
    store = _load_raw()
    return {
        "active_id": store["active_id"],
        "temperature": store["temperature"],
        "max_tokens": store["max_tokens"],
        "profiles": [_profile_public(p) for p in store["profiles"]],
    }


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """Internal full profile (includes api_key)."""
    store = _load_raw()
    for p in store["profiles"]:
        if p["id"] == profile_id:
            return dict(p)
    return None


def get_profile_public(profile_id: str) -> Optional[Dict[str, Any]]:
    p = get_profile(profile_id)
    return _profile_public(p) if p else None


def create_profile(
    *,
    label: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model_id: Optional[str] = None,
    enabled: bool = True,
    activate: bool = False,
) -> Dict[str, Any]:
    store = _load_raw()
    profile = {
        "id": _new_id(),
        "label": _normalize_label(label or "New Profile"),
        "enabled": bool(enabled),
        "base_url": _normalize_base_url(base_url) if base_url is not None else "",
        "api_key": str(api_key).strip() if api_key else "",
        "model_id": _normalize_model(model_id) if model_id else "kimi-k3",
        "api": _DEFAULT_API,
        "supports_reasoning": False,
        "reasoning_mode": "none",
    }
    if base_url is None:
        # Inherit active URL as a convenience when adding another profile.
        active = next((p for p in store["profiles"] if p["id"] == store["active_id"]), store["profiles"][0])
        profile["base_url"] = active.get("base_url") or ""
    store["profiles"].append(profile)
    if activate:
        store["active_id"] = profile["id"]
    _save_raw(store)
    _sync_settings_from_active(store)
    return _profile_public(profile)


def update_profile(profile_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    store = _load_raw()
    target: Optional[Dict[str, Any]] = None
    for p in store["profiles"]:
        if p["id"] == profile_id:
            target = p
            break
    if target is None:
        raise KeyError(f"profile not found: {profile_id}")

    if "label" in updates and updates["label"] is not None:
        target["label"] = _normalize_label(str(updates["label"]))
    if "enabled" in updates and updates["enabled"] is not None:
        target["enabled"] = bool(updates["enabled"])
    if "base_url" in updates and updates["base_url"] is not None:
        target["base_url"] = _normalize_base_url(str(updates["base_url"]))
    if "model_id" in updates and updates["model_id"] is not None:
        target["model_id"] = _normalize_model(str(updates["model_id"]))
    if "api_key" in updates and updates["api_key"] is not None:
        key = str(updates["api_key"]).strip()
        if key:
            target["api_key"] = key
        # empty key → keep existing (do not wipe)
    if "api" in updates and updates["api"] is not None:
        target["api"] = str(updates["api"]).strip() or _DEFAULT_API
    if "supports_reasoning" in updates and updates["supports_reasoning"] is not None:
        target["supports_reasoning"] = bool(updates["supports_reasoning"])
        # Turning reasoning on defaults to openai_compatible request hints.
        if target["supports_reasoning"] and normalize_reasoning_mode(
            target.get("reasoning_mode")
        ) == "none":
            target["reasoning_mode"] = "openai_compatible"
        if not target["supports_reasoning"]:
            target["reasoning_mode"] = "none"
    if "reasoning_mode" in updates and updates["reasoning_mode"] is not None:
        target["reasoning_mode"] = normalize_reasoning_mode(updates["reasoning_mode"])

    _save_raw(store)
    _sync_settings_from_active(store)
    return _profile_public(target)


def delete_profile(profile_id: str) -> Dict[str, Any]:
    store = _load_raw()
    if len(store["profiles"]) <= 1:
        raise ValueError("不能删除最后一个模型档案")
    remaining = [p for p in store["profiles"] if p["id"] != profile_id]
    if len(remaining) == len(store["profiles"]):
        raise KeyError(f"profile not found: {profile_id}")
    store["profiles"] = remaining
    if store["active_id"] == profile_id:
        # Prefer an enabled profile; else first remaining.
        enabled = next((p for p in remaining if p.get("enabled")), remaining[0])
        store["active_id"] = enabled["id"]
    _save_raw(store)
    _sync_settings_from_active(store)
    return list_profiles_public()


def set_active(profile_id: str) -> Dict[str, Any]:
    store = _load_raw()
    if not any(p["id"] == profile_id for p in store["profiles"]):
        raise KeyError(f"profile not found: {profile_id}")
    store["active_id"] = profile_id
    _save_raw(store)
    _sync_settings_from_active(store)
    return list_profiles_public()


def update_globals(*, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Dict[str, Any]:
    store = _load_raw()
    if temperature is not None:
        temp = float(temperature)
        if not (0.0 <= temp <= 2.0):
            raise ValueError("Temperature 必须在 0 到 2 之间")
        store["temperature"] = temp
    if max_tokens is not None:
        tokens = int(max_tokens)
        if not (256 <= tokens <= 200000):
            raise ValueError("Max Tokens 必须在 256 到 200000 之间")
        store["max_tokens"] = tokens
    _save_raw(store)
    _sync_settings_from_active(store)
    return list_profiles_public()


def _handle_from_profile(profile: Dict[str, Any]) -> ModelHandle:
    return ModelHandle(
        profile_id=profile["id"],
        model_id=profile["model_id"],
        api=profile.get("api") or _DEFAULT_API,
        base_url=(profile.get("base_url") or "").rstrip("/"),
    )


def resolve_active_handle() -> Optional[ModelHandle]:
    """Active profile if enabled; else first enabled; else None."""
    store = _load_raw()
    by_id = {p["id"]: p for p in store["profiles"]}
    active = by_id.get(store["active_id"])
    chosen: Optional[Dict[str, Any]] = None
    if active and active.get("enabled"):
        chosen = active
    else:
        chosen = next((p for p in store["profiles"] if p.get("enabled")), None)
    if not chosen:
        return None
    return _handle_from_profile(chosen)


def resolve_handle(profile_id: Optional[str] = None) -> Optional[ModelHandle]:
    """Enabled profile by id. Empty id means the active handle. Missing or disabled → None."""
    pid = (profile_id or "").strip()
    if not pid:
        return resolve_active_handle()
    store = _load_raw()
    for profile in store["profiles"]:
        if profile["id"] == pid and profile.get("enabled"):
            return _handle_from_profile(profile)
    return None


def resolve_turn_binding(
    profile_id: Optional[str],
    session_model_id: Optional[str],
    request_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Credentials profile + model id for one turn.

    Empty session profile uses the global active profile (legacy rows).
    A stored profile that is missing or disabled falls back to active and
    drops the stale model id. A request/session model override is kept only
    when the profile itself is still valid.
    """
    requested = (profile_id or "").strip()
    handle = resolve_handle(requested) if requested else resolve_active_handle()
    fallback = bool(requested) and handle is None
    if fallback:
        handle = resolve_active_handle()
    default_model = handle.model_id if handle else (settings.llm_model or "")
    if fallback or handle is None:
        model = default_model
    else:
        explicit = (request_model or "").strip() or (session_model_id or "").strip()
        model = explicit or default_model
    return {
        "profile_id": handle.profile_id if handle else "",
        "model_id": model,
        "fallback": fallback,
    }


def resolve_credentials(profile_id: Optional[str] = None) -> Dict[str, str]:
    """Return base_url + api_key for provider. Defaults to active handle's profile."""
    store = _load_raw()
    pid = profile_id
    if not pid:
        handle = resolve_active_handle()
        if handle:
            pid = handle.profile_id
        else:
            pid = store["active_id"]
    for p in store["profiles"]:
        if p["id"] == pid:
            return {
                "profile_id": p["id"],
                "base_url": (p.get("base_url") or "").rstrip("/"),
                "api_key": str(p.get("api_key") or ""),
                "model_id": p.get("model_id") or "",
            }
    return {"profile_id": "", "base_url": "", "api_key": "", "model_id": ""}


def get_globals() -> Dict[str, Any]:
    store = _load_raw()
    return {"temperature": store["temperature"], "max_tokens": store["max_tokens"]}


def _sync_settings_from_active(store: Dict[str, Any]) -> None:
    """Keep in-process settings aligned with active profile + globals (back-compat)."""
    by_id = {p["id"]: p for p in store["profiles"]}
    active = by_id.get(store["active_id"]) or store["profiles"][0]
    settings.llm_base_url = (active.get("base_url") or "").rstrip("/")
    settings.llm_api_key = str(active.get("api_key") or "")
    settings.llm_model = active.get("model_id") or settings.llm_model
    settings.llm_temperature = float(store["temperature"])
    settings.llm_max_tokens = int(store["max_tokens"])
