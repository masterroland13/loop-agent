"""Skill / project rule discovery and injection.

Skills live under `skills/<skill_id>/`:
  - Prefer `SKILL.md` (optional YAML frontmatter: name, description, …)
  - Fallback to `README.md` for older layouts

Project rules are read from `AGENTS.md` in the workspace root.
Settings persist the list of active skill ids in agent_settings.json.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
from agent_window.services.workspace import get_workspace_root, workspace_status

MAX_SKILL_CHARS = 12_000
_SKILL_FILENAMES = ("SKILL.md", "README.md")


def skill_dir() -> Path | None:
    root = get_workspace_root()
    if not root:
        return None
    return Path(root) / "skills"


def agents_md_path() -> Path | None:
    root = get_workspace_root()
    if not root:
        return None
    return Path(root) / "AGENTS.md"


def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Parse simple YAML-like frontmatter; returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    # Match opening --- ... closing ---
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    raw_meta, body = match.group(1), match.group(2)
    meta: Dict[str, str] = {}
    for line in raw_meta.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            meta[key] = value
    return meta, body.lstrip("\n")


def _resolve_skill_file(entry: Path) -> Path | None:
    for name in _SKILL_FILENAMES:
        path = entry / name
        if path.is_file():
            return path
    return None


def _load_skill_file(path: Path) -> Tuple[Dict[str, str], str] | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not raw:
        return None
    meta, body = _parse_frontmatter(raw)
    content = (body or raw).strip()
    if not content and not meta:
        return None
    # Prefer body for injection; if body empty after frontmatter-only, use raw without fences
    if not content:
        content = raw
    return meta, content


def discover_skills() -> List[Dict[str, Any]]:
    """Return discovered skill ids with metadata."""
    sd = skill_dir()
    root = get_workspace_root()
    if not sd or not sd.exists():
        return []
    skills: List[Dict[str, Any]] = []
    for entry in sorted(sd.iterdir()):
        if not entry.is_dir():
            continue
        path = _resolve_skill_file(entry)
        if not path:
            continue
        loaded = _load_skill_file(path)
        if not loaded:
            continue
        meta, content = loaded
        default_name = entry.name.replace("-", " ").replace("_", " ").title()
        name = meta.get("name") or default_name
        description = meta.get("description") or ""
        skills.append({
            "id": entry.name,
            "name": name,
            "description": description,
            "path": str(path.relative_to(Path(root) if root else entry)),
            "preview": content[:200],
        })
    return skills


def read_skill(skill_id: str) -> str:
    """Return skill body for prompt injection (frontmatter stripped)."""
    sd = skill_dir()
    if not sd:
        return ""
    path = _resolve_skill_file(sd / skill_id)
    if not path:
        return ""
    loaded = _load_skill_file(path)
    if not loaded:
        return ""
    meta, content = loaded
    # Inject name/description header when present so the model sees intent
    header_parts: List[str] = []
    if meta.get("name"):
        header_parts.append(f"Name: {meta['name']}")
    if meta.get("description"):
        header_parts.append(f"Description: {meta['description']}")
    body = content[:MAX_SKILL_CHARS]
    if header_parts:
        return "\n".join(header_parts) + "\n\n" + body
    return body


def read_agents_md() -> str:
    path = agents_md_path()
    if not path or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()[:MAX_SKILL_CHARS]
    except Exception:
        return ""


def get_active_skills() -> List[str]:
    agent = load_agent_settings()
    active = agent.get("active_skills")
    if not isinstance(active, list):
        return []
    return [str(s).strip() for s in active if str(s).strip()]


def set_active_skills(skill_ids: List[str]) -> Dict[str, Any]:
    # Persist even unknown ids so the user can manually add skills before they exist.
    cleaned = [s for s in skill_ids if s.strip()]
    return save_agent_settings({"active_skills": cleaned})


def skill_context_blocks() -> List[str]:
    """Build markdown blocks to inject into system prompt."""
    blocks: List[str] = []
    agents = read_agents_md()
    if agents:
        blocks.append("## AGENTS.md (project rules; read-only here)\n" + agents)

    active = get_active_skills()
    if active:
        blocks.append("## Active Skills\n")
        for skill_id in active:
            content = read_skill(skill_id)
            if not content:
                continue
            blocks.append(f"### skill: {skill_id}\n{content}")

    return blocks


def skill_status() -> Dict[str, Any]:
    ws = workspace_status()
    return {
        "workspace_configured": ws["configured"],
        "workspace_root": ws.get("root"),
        "skills_discovered": [s["id"] for s in discover_skills()],
        "active_skills": get_active_skills(),
        "agents_md_exists": bool(agents_md_path() and agents_md_path().exists()),
    }
