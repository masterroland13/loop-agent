"""AGENTS.md layered loading and Skills progressive disclosure."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_window.config import settings
from agent_window.services.skills import (
    agents_md_paths,
    read_agents_md,
    skill_context_blocks,
)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))
    from agent_window.services.workspace import set_workspace_root

    set_workspace_root(str(tmp_path))
    return tmp_path


# ── AGENTS.md layered loading ────────────────────────────────────────


def test_no_agents_md(ws: Path) -> None:
    assert agents_md_paths() == []
    assert read_agents_md() == ""


def test_workspace_root_only(ws: Path) -> None:
    (ws / "AGENTS.md").write_text("Project rule: always test.", encoding="utf-8")
    paths = agents_md_paths()
    assert len(paths) == 1
    assert paths[0] == ws / "AGENTS.md"
    assert "always test" in read_agents_md()


def test_parent_dir_layer(ws: Path, monkeypatch) -> None:
    # Create a parent AGENTS.md
    parent = ws.parent
    (parent / "AGENTS.md").write_text("Global rule: be concise.", encoding="utf-8")
    (ws / "AGENTS.md").write_text("Project rule: always test.", encoding="utf-8")
    try:
        paths = agents_md_paths()
        assert len(paths) == 2
        # Parent comes before workspace root
        assert paths[0] == parent / "AGENTS.md"
        assert paths[1] == ws / "AGENTS.md"
        merged = read_agents_md()
        assert "be concise" in merged
        assert "always test" in merged
        # Parent layer should be labeled
        assert "[from" in merged
    finally:
        (parent / "AGENTS.md").unlink()


def test_global_layer(ws: Path, monkeypatch, tmp_path: Path) -> None:
    import agent_window.services.skills as skills_mod

    new_file = tmp_path / "loop-agent" / "AGENTS.md"
    legacy_file = tmp_path / "hal-agent" / "AGENTS.md"
    new_file.parent.mkdir()
    legacy_file.parent.mkdir()
    new_file.write_text("Global: answer in Chinese.", encoding="utf-8")
    legacy_file.write_text("Legacy: should not win.", encoding="utf-8")
    monkeypatch.setattr(
        skills_mod,
        "global_agents_md_candidates",
        lambda: [new_file, legacy_file],
    )
    (ws / "AGENTS.md").write_text("Project: use pytest.", encoding="utf-8")
    paths = agents_md_paths()
    assert len(paths) == 2
    assert paths[0] == new_file
    assert paths[1] == ws / "AGENTS.md"
    assert legacy_file not in paths
    merged = read_agents_md()
    assert "answer in Chinese" in merged
    assert "use pytest" in merged
    assert "should not win" not in merged


def test_global_layer_falls_back_to_previous_config_dir(ws: Path, monkeypatch, tmp_path: Path) -> None:
    import agent_window.services.skills as skills_mod

    new_file = tmp_path / "loop-agent" / "AGENTS.md"
    legacy_file = tmp_path / "hal-agent" / "AGENTS.md"
    legacy_file.parent.mkdir()
    legacy_file.write_text("Legacy: answer in Chinese.", encoding="utf-8")
    monkeypatch.setattr(
        skills_mod,
        "global_agents_md_candidates",
        lambda: [new_file, legacy_file],
    )
    (ws / "AGENTS.md").write_text("Project: use pytest.", encoding="utf-8")
    paths = agents_md_paths()
    assert paths[0] == legacy_file
    assert new_file not in paths
    merged = read_agents_md()
    assert "answer in Chinese" in merged
    assert "use pytest" in merged


def test_empty_agents_md_skipped(ws: Path) -> None:
    (ws / "AGENTS.md").write_text("", encoding="utf-8")
    assert read_agents_md() == ""


# ── Skills progressive disclosure ────────────────────────────────────


def test_skills_inject_name_desc_only(ws: Path, monkeypatch) -> None:
    # Create a skill with frontmatter
    skill_dir = ws / "skills" / "code-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Code Review\ndescription: Review code for quality\n---\n\n"
        "# Full instructions\n\nDo a thorough review of all files.\n" * 50,
        encoding="utf-8",
    )
    # Activate the skill
    from agent_window.services.agent_settings import save_agent_settings

    save_agent_settings({"active_skills": ["code-review"]})

    blocks = skill_context_blocks()
    skills_block = [b for b in blocks if "Available Skills" in b]
    assert len(skills_block) == 1
    text = skills_block[0]
    # Should have name and description
    assert "Code Review" in text
    assert "Review code for quality" in text
    assert "code-review" in text
    # Should NOT have the full body
    assert "Do a thorough review" not in text
    # Should mention how to load
    assert "load via tools" in text or "read_file" in text
    assert "SKILL.md" in text or "tools" in text


def test_skills_not_active_not_injected(ws: Path) -> None:
    skill_dir = ws / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# My Skill\nDo stuff.", encoding="utf-8")
    # Not activated
    blocks = skill_context_blocks()
    assert not any("Available Skills" in b for b in blocks)


def test_agents_md_still_full_text(ws: Path) -> None:
    (ws / "AGENTS.md").write_text("Full project rules here.", encoding="utf-8")
    blocks = skill_context_blocks()
    agents_block = [b for b in blocks if "AGENTS.md" in b]
    assert len(agents_block) == 1
    assert "Full project rules here." in agents_block[0]
