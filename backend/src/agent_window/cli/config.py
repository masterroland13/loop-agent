"""CLI configuration file support for Hal Agent.

Priority (highest first):
1. Environment variables (AGENT_BASE_URL)
2. ~/.config/hal-agent/config.json
3. Built-in defaults
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 120.0
CONFIG_DIR = Path.home() / ".config" / "hal-agent"
CONFIG_PATH = CONFIG_DIR / "config.json"


def _load_config_file() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_cli_config() -> Dict[str, Any]:
    """Return merged CLI config with priority: env > file > default."""
    file_cfg = _load_config_file()

    base_url = os.environ.get("AGENT_BASE_URL")
    if base_url is None:
        base_url = file_cfg.get("base_url") or DEFAULT_BASE

    timeout = file_cfg.get("timeout")
    try:
        timeout = float(timeout) if timeout is not None else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    default_model = file_cfg.get("default_model")
    auto_approve = bool(file_cfg.get("auto_approve", False))

    return {
        "base_url": base_url,
        "timeout": timeout,
        "default_model": default_model,
        "auto_approve": auto_approve,
    }
