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
    "approval_timeout_sec": 300,
    "disabled_tools": [],
    # How many LLM↔tool rounds per turn before soft-stop / abort.
    "max_tool_iters": 24,
    # Progress checkpoint every N completed tools (0 = interval off; gate still checkpoints).
    "checkpoint_every_n_tools": 4,
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
    try:
        approval = int(data.get("approval_timeout_sec") or 300)
    except (TypeError, ValueError):
        approval = 300
    data["approval_timeout_sec"] = max(30, min(3600, approval))
    disabled = data.get("disabled_tools")
    if not isinstance(disabled, list):
        disabled = []
    data["disabled_tools"] = [str(t).strip() for t in disabled if str(t).strip()]
    try:
        iters = int(data.get("max_tool_iters") or 24)
    except (TypeError, ValueError):
        iters = 24
    data["max_tool_iters"] = max(8, min(64, iters))
    from agent_window.agent.checkpoint import checkpoint_interval_from_settings

    data["checkpoint_every_n_tools"] = checkpoint_interval_from_settings(
        data.get("checkpoint_every_n_tools"),
    )
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
    if "approval_timeout_sec" in updates and updates["approval_timeout_sec"] is not None:
        current["approval_timeout_sec"] = max(30, min(3600, int(updates["approval_timeout_sec"])))
    if "disabled_tools" in updates and updates["disabled_tools"] is not None:
        current["disabled_tools"] = [str(t).strip() for t in updates["disabled_tools"] if str(t).strip()]
    if "max_tool_iters" in updates and updates["max_tool_iters"] is not None:
        current["max_tool_iters"] = max(8, min(64, int(updates["max_tool_iters"])))
    if "checkpoint_every_n_tools" in updates and updates["checkpoint_every_n_tools"] is not None:
        from agent_window.agent.checkpoint import checkpoint_interval_from_settings

        current["checkpoint_every_n_tools"] = checkpoint_interval_from_settings(
            updates["checkpoint_every_n_tools"],
        )
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
