"""Hunk parsing and partial apply — no LLM."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.services.patches import (
    PatchStatus,
    _patches,
    apply_hunks_to_content,
    apply_partial_patch,
    create_patch_from_replace,
    parse_hunks,
)
from agent_window.services.workspace import set_workspace_root


@pytest.fixture
def ws(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    _patches.clear()
    set_workspace_root(str(tmp_path))
    yield tmp_path


SAMPLE_DIFF = """\
--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 def foo():
     pass
+    # added comment
     return 1
@@ -10,2 +11,3 @@
 def bar():
     pass
+    # another comment
     return 2
"""


def test_parse_hunks() -> None:
    hunks = parse_hunks(SAMPLE_DIFF)
    assert len(hunks) == 2
    assert hunks[0].header.startswith("@@ -1,3 +1,4 @@")
    assert hunks[0].old_start == 1
    assert hunks[0].old_count == 3
    assert hunks[0].new_start == 1
    assert hunks[0].new_count == 4
    assert hunks[1].header.startswith("@@ -10,2 +11,3 @@")
    assert len(hunks[0].lines) == 4  # pass, +comment, return 1, context
    assert len(hunks[1].lines) == 4  # bar, pass, +comment, return 2


def test_apply_all_hunks() -> None:
    old = "def foo():\n    pass\n    return 1\n"
    hunks = parse_hunks(SAMPLE_DIFF)
    # Only first hunk applies to this small file
    result = apply_hunks_to_content(old, [hunks[0]], {0})
    assert "added comment" in result
    assert "return 1" in result


def test_apply_no_hunks() -> None:
    old = "def foo():\n    pass\n    return 1\n"
    hunks = parse_hunks(SAMPLE_DIFF)
    result = apply_hunks_to_content(old, [hunks[0]], set())
    assert result == old


def test_apply_subset() -> None:
    old = (
        "def foo():\n    pass\n    return 1\n"
        "\n\n\n\n\n\n"
        "def bar():\n    pass\n    return 2\n"
    )
    hunks = parse_hunks(SAMPLE_DIFF)
    # Apply only the second hunk
    result = apply_hunks_to_content(old, hunks, {1})
    assert "another comment" in result
    assert "added comment" not in result


def test_partial_apply_endpoint(ws: Path) -> None:
    target = ws / "test.py"
    target.write_text("def foo():\n    pass\n    return 1\n", encoding="utf-8")

    patch = create_patch_from_replace(
        "test.py",
        "    pass\n    return 1\n",
        "    pass\n    # added comment\n    return 1\n",
    )
    assert patch.status == PatchStatus.PENDING

    # Full apply via partial with all hunks
    hunks = parse_hunks(patch.unified_diff)
    all_ids = list(range(len(hunks)))
    result = asyncio.run(apply_partial_patch(patch.id, all_ids))
    assert result.status == PatchStatus.APPLIED
    content = target.read_text(encoding="utf-8")
    assert "added comment" in content


def test_partial_apply_empty_selection(ws: Path) -> None:
    target = ws / "test2.py"
    target.write_text("x = 1\n", encoding="utf-8")
    patch = create_patch_from_replace("test2.py", "x = 1\n", "x = 2\n")
    with pytest.raises(Exception, match="no hunks selected"):
        asyncio.run(apply_partial_patch(patch.id, []))


def test_partial_apply_already_decided(ws: Path) -> None:
    target = ws / "test3.py"
    target.write_text("a = 1\n", encoding="utf-8")
    patch = create_patch_from_replace("test3.py", "a = 1\n", "a = 2\n")
    asyncio.run(apply_partial_patch(patch.id, [0]))
    with pytest.raises(Exception, match="patch already applied"):
        asyncio.run(apply_partial_patch(patch.id, [0]))


def test_gate_message_for_partial() -> None:
    from agent_window.agent.loop import _GATE_TEMPLATE_STATUSES, _gate_user_message

    assert "partial" in _GATE_TEMPLATE_STATUSES
    msg = _gate_user_message("patch", {"status": "partial", "path": "x.py", "applied_hunks": [0, 2]})
    assert "部分应用" in msg
    assert "x.py" in msg
    assert "超时" not in msg
    assert "失败" not in msg
