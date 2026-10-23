"""LLM config adapter — reads/writes the **active** Model Registry profile.

Keeps `/api/llm-config` and older tests working. Optionally syncs `LLM_*` to
backend/.env for process restarts that still load Settings from env.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings
from agent_window.services import model_registry as registry

logger = logging.getLogger(__name__)

_ENV_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TEMPERATURE", "LLM_MAX_TOKENS")


def _env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def _normalize_base_url(url: str) -> str:
    return registry._normalize_base_url(url)


def _normalize_model(model: str) -> str:
    return registry._normalize_model(model)


def _write_env(path: Path, updates: Dict[str, str]) -> None:
    """Upsert KEY=VALUE lines in .env, preserving everything else."""
    existing: List[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    out: List[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def public_llm_config(_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Public view of the active profile + global generation defaults."""
    # Ensure migrate-once has run.
    store = registry.load_store()
    by_id = {p["id"]: p for p in store["profiles"]}
    active = by_id.get(store["active_id"]) or store["profiles"][0]
    return {
        "api_key_configured": bool(str(active.get("api_key") or "").strip()),
        "base_url": (active.get("base_url") or "").rstrip("/"),
        "default_model": active.get("model_id") or "",
        "temperature": store["temperature"],
        "max_tokens": store["max_tokens"],
    }


def save_llm_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update active profile fields and/or global temp/tokens; sync .env."""
    store = registry.load_store()
    active_id = store["active_id"]
    profile_updates: Dict[str, Any] = {}
    env_updates: Dict[str, str] = {}

    if "base_url" in updates and updates["base_url"] is not None:
        url = _normalize_base_url(str(updates["base_url"]))
        profile_updates["base_url"] = url
        env_updates["LLM_BASE_URL"] = url
    if "api_key" in updates and updates["api_key"] is not None:
        key = str(updates["api_key"]).strip()
        if key:
            profile_updates["api_key"] = key
            env_updates["LLM_API_KEY"] = key
    if "default_model" in updates and updates["default_model"] is not None:
        model = _normalize_model(str(updates["default_model"]))
        profile_updates["model_id"] = model
        env_updates["LLM_MODEL"] = model

    globals_kwargs: Dict[str, Any] = {}
    if "temperature" in updates and updates["temperature"] is not None:
        temp = float(updates["temperature"])
        if not (0.0 <= temp <= 2.0):
            raise ValueError("Temperature 必须在 0 到 2 之间")
        globals_kwargs["temperature"] = temp
        env_updates["LLM_TEMPERATURE"] = str(temp)
    if "max_tokens" in updates and updates["max_tokens"] is not None:
        tokens = int(updates["max_tokens"])
        if not (256 <= tokens <= 200000):
            raise ValueError("Max Tokens 必须在 256 到 200000 之间")
        globals_kwargs["max_tokens"] = tokens
        env_updates["LLM_MAX_TOKENS"] = str(tokens)

    if not profile_updates and not globals_kwargs:
        return public_llm_config()

    if profile_updates:
        registry.update_profile(active_id, profile_updates)
    if globals_kwargs:
        registry.update_globals(**globals_kwargs)

    if env_updates and os.environ.get("LOOP_SHELL") != "1":
        _write_env(_env_path(), env_updates)

    return public_llm_config()
