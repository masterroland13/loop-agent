"""Layer boundaries for agent_window.core (A0)."""

from __future__ import annotations

import ast
from pathlib import Path


def _core_package_dir() -> Path:
    import agent_window.core as core_pkg

    return Path(core_pkg.__file__).resolve().parent


def _imported_modules_from_source(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_core_package_does_not_import_api_or_models() -> None:
    import agent_window.core  # noqa: F401

    core_dir = _core_package_dir()
    py_files = sorted(core_dir.glob("*.py"))
    assert py_files, "expected core/*.py modules"

    forbidden_prefixes = ("agent_window.api", "agent_window.models")
    for path in py_files:
        imports = _imported_modules_from_source(path)
        for mod in imports:
            for bad in forbidden_prefixes:
                assert not (mod == bad or mod.startswith(bad + ".")), (
                    f"{path.name} must not import {mod}"
                )
        # reverse: forbidden packages must not appear under any alias form either
        assert "agent_window.api" not in imports
        assert "agent_window.models" not in imports


def test_loop_config_importable_from_core() -> None:
    from agent_window.core import LoopConfig
    from agent_window.core.loop_config import LoopConfig as LoopConfigDirect

    assert LoopConfig is LoopConfigDirect
    # reverse: package export is the same class, not a stub/None
    assert LoopConfig is not None
    assert not isinstance(LoopConfig.default(), type(None))
    assert isinstance(LoopConfig.default(), LoopConfig)
