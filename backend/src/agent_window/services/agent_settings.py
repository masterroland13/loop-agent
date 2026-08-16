"""Persisted agent governance settings (compress / memory / limits)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from agent_window.config import settings

_CONFIG_NAME = "agent_settings.json"

DEFAULTS: Dict[str, Any] = {
    "auto_compress": False,
    "confirm_memory": True,
    "context_limit": 8192,
    "active_skills": [],
}


def _path() -> Path:
    return Path(settings.app_data_dir) / _CONFIG_NAME


def load_agent_settings() -> Dict[str, Any]:
    path = _path()
    data = dict(DEFAULTS)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in DEFAULTS if k in raw})
        except Exception:
            pass
    data["auto_compress"] = bool(data.get("auto_compress"))
    data["confirm_memory"] = bool(data.get("confirm_memory", True))
    try:
        limit = int(data.get("context_limit") or 8192)
    except (TypeError, ValueError):
        limit = 8192
    data["context_limit"] = max(2048, min(32768, limit))
    active = data.get("active_skills")
    if not isinstance(active, list):
        active = []
    data["active_skills"] = [str(s).strip() for s in active if str(s).strip()]
    return data


def save_agent_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = load_agent_settings()
    if "auto_compress" in updates and updates["auto_compress"] is not None:
        current["auto_compress"] = bool(updates["auto_compress"])
    if "confirm_memory" in updates and updates["confirm_memory"] is not None:
        current["confirm_memory"] = bool(updates["confirm_memory"])
    if "context_limit" in updates and updates["context_limit"] is not None:
        current["context_limit"] = max(2048, min(32768, int(updates["context_limit"])))
    if "active_skills" in updates and updates["active_skills"] is not None:
        current["active_skills"] = [str(s).strip() for s in updates["active_skills"] if str(s).strip()]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
