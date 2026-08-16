"""LLM base URL / API key / default model, persisted to backend/.env.

Saving from the UI writes .env AND updates in-process settings, so the
next request uses the new values without a restart and restarts keep them.
The raw key is never returned to the frontend.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_window.config import settings

logger = logging.getLogger(__name__)

_ENV_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def _env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


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
    return {
        "api_key_configured": bool(str(settings.llm_api_key or "").strip()),
        "base_url": (settings.llm_base_url or "").rstrip("/"),
        "default_model": settings.llm_model or "",
    }


def save_llm_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    env_updates: Dict[str, str] = {}
    if "base_url" in updates and updates["base_url"] is not None:
        env_updates["LLM_BASE_URL"] = _normalize_base_url(str(updates["base_url"]))
    if "api_key" in updates and updates["api_key"] is not None:
        key = str(updates["api_key"]).strip()
        if key:
            env_updates["LLM_API_KEY"] = key
    if "default_model" in updates and updates["default_model"] is not None:
        env_updates["LLM_MODEL"] = _normalize_model(str(updates["default_model"]))
    if not env_updates:
        return public_llm_config()

    _write_env(_env_path(), env_updates)

    # Apply in-process so the next request uses the new values immediately.
    if "LLM_BASE_URL" in env_updates:
        settings.llm_base_url = env_updates["LLM_BASE_URL"]
    if "LLM_API_KEY" in env_updates:
        settings.llm_api_key = env_updates["LLM_API_KEY"]
    if "LLM_MODEL" in env_updates:
        settings.llm_model = env_updates["LLM_MODEL"]
    return public_llm_config()

