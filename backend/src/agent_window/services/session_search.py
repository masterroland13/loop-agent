"""Search this session's transcript.jsonl and spill blobs (C4).

Does not read SQLite message bodies, other sessions, the workspace, or .env.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_window.config import settings
from agent_window.services.session_transcript import (
    TRANSCRIPT_NAME,
    iter_transcript_lines,
    redact_value,
    transcript_path,
)
from agent_window.services.storage import get_session_path, resolve_session_blob_path

MAX_HITS = 12
MAX_EXCERPT = 220
MAX_TOTAL_CHARS = 6000
MAX_BLOB_READ = 120_000

_SKIP_NAMES = frozenset({".env", ".env.local", ".env.production", "credentials.json"})


class SessionSearchError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _terms(query: str) -> list[str]:
    return [part for part in (query or "").split() if part.strip()]


def _hay(text: str) -> str:
    return text.lower()


def _matches(text: str, terms: list[str]) -> bool:
    if not terms or not text:
        return False
    blob = _hay(text)
    return all(term.lower() in blob for term in terms)


def _excerpt(text: str, terms: list[str], *, limit: int = MAX_EXCERPT) -> str:
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    loc = -1
    lower = raw.lower()
    for term in terms:
        loc = lower.find(term.lower())
        if loc >= 0:
            break
    if loc < 0:
        clipped = raw[:limit]
        return clipped + ("…" if len(raw) > limit else "")
    start = max(0, loc - limit // 3)
    end = min(len(raw), start + limit)
    piece = raw[start:end]
    if start > 0:
        piece = "…" + piece
    if end < len(raw):
        piece = piece + "…"
    return piece


def _session_root(session: Any) -> Path:
    root = get_session_path(session).resolve()
    base = Path(settings.app_data_dir).resolve()
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise SessionSearchError(
            "session data path escapes user data dir",
            "PATH_FORBIDDEN",
        ) from exc
    return root


def _is_forbidden_name(path: Path) -> bool:
    name = path.name.lower()
    if name in _SKIP_NAMES:
        return True
    if name.startswith(".env") or name.endswith(".env"):
        return True
    return False


def resolve_searchable_path(session: Any, rel_or_ref: str) -> Path:
    """Resolve a user-supplied path inside this session's data_path only."""
    raw = (rel_or_ref or "").strip().replace("\\", "/")
    if raw.startswith("file:"):
        raw = raw[5:].lstrip("/")
    if not raw:
        raise SessionSearchError("path is required", "INVALID_PATH")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise SessionSearchError("absolute paths are not allowed", "PATH_FORBIDDEN")
    parts = [p for p in raw.split("/") if p and p != "."]
    if ".." in parts:
        raise SessionSearchError("path escapes session data", "PATH_FORBIDDEN")
    if any(
        p.lower() in _SKIP_NAMES
        or p.lower().startswith(".env")
        or p.lower().endswith(".env")
        for p in parts
    ):
        raise SessionSearchError("refusing to search .env or credential files", "PATH_FORBIDDEN")
    try:
        target = resolve_session_blob_path(session, "/".join(parts))
    except ValueError as exc:
        raise SessionSearchError(str(exc), "PATH_FORBIDDEN") from exc
    root = _session_root(session)
    try:
        target.resolve().relative_to(root)
    except ValueError as exc:
        raise SessionSearchError("path escapes session data", "PATH_FORBIDDEN") from exc
    rel = target.resolve().relative_to(root).as_posix()
    if rel != TRANSCRIPT_NAME and not rel.startswith("turns/"):
        raise SessionSearchError(
            "only transcript.jsonl and turns/ spill blobs are searchable",
            "PATH_FORBIDDEN",
        )
    return target


def _iter_blob_files(session: Any) -> list[Path]:
    root = _session_root(session)
    turns = root / "turns"
    if not turns.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(turns.rglob("*")):
        if not path.is_file():
            continue
        if _is_forbidden_name(path):
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        rel = path.resolve().relative_to(root).as_posix()
        if not rel.startswith("turns/"):
            continue
        out.append(path)
    return out


def _add_hit(
    hits: list[dict[str, Any]],
    *,
    source: str,
    line: int,
    excerpt: str,
    event_id: Any = None,
    event_type: str | None = None,
    path: str | None = None,
    budget: list[int],
) -> bool:
    excerpt = str(redact_value(excerpt) if isinstance(excerpt, str) else excerpt)
    if budget[0] + len(excerpt) > MAX_TOTAL_CHARS:
        room = MAX_TOTAL_CHARS - budget[0]
        if room < 40:
            return False
        excerpt = excerpt[:room] + "…"
    hit = {
        "source": source,
        "line": line,
        "excerpt": excerpt,
    }
    if event_id:
        hit["id"] = event_id
    if event_type:
        hit["type"] = event_type
    if path:
        hit["path"] = path
    hits.append(hit)
    budget[0] += len(excerpt)
    return budget[0] < MAX_TOTAL_CHARS and len(hits) < MAX_HITS


def search_session_records(
    session: Any,
    query: str,
    *,
    max_hits: int = 8,
    path: str | None = None,
) -> dict[str, Any]:
    terms = _terms(query)
    if not terms:
        raise SessionSearchError("query is required", "INVALID_ARGS")
    cap = max(1, min(int(max_hits or 8), MAX_HITS))
    hits: list[dict[str, Any]] = []
    budget = [0]
    scoped = resolve_searchable_path(session, path) if path else None

    def still() -> bool:
        return len(hits) < cap and budget[0] < MAX_TOTAL_CHARS

    jsonl = transcript_path(session)
    scan_jsonl = scoped is None or (scoped.is_file() and scoped.name == TRANSCRIPT_NAME)
    if scan_jsonl and jsonl.is_file():
        for index, line in enumerate(iter_transcript_lines(session), start=1):
            if not still():
                break
            if not _matches(line, terms):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                record = {}
            content = ""
            if isinstance(record, dict):
                content = " ".join(
                    str(record.get(key) or "")
                    for key in ("content", "preview", "name", "path", "command")
                    if record.get(key)
                )
            excerpt = _excerpt(content or line, terms)
            if not _add_hit(
                hits,
                source="transcript",
                line=index,
                excerpt=excerpt,
                event_id=record.get("id") if isinstance(record, dict) else None,
                event_type=record.get("type") if isinstance(record, dict) else None,
                path=TRANSCRIPT_NAME,
                budget=budget,
            ):
                break

    blob_targets: list[Path]
    if scoped is not None and scoped.is_file() and scoped.name != TRANSCRIPT_NAME:
        blob_targets = [scoped]
    elif scoped is None:
        blob_targets = _iter_blob_files(session)
    else:
        blob_targets = []

    root = _session_root(session)
    for blob in blob_targets:
        if not still():
            break
        try:
            text = blob.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > MAX_BLOB_READ:
            text = text[:MAX_BLOB_READ]
        rel = blob.resolve().relative_to(root).as_posix()
        for index, row in enumerate(text.splitlines() or [text], start=1):
            if not still():
                break
            if not _matches(row, terms):
                continue
            if not _add_hit(
                hits,
                source="blob",
                line=index,
                excerpt=_excerpt(row, terms),
                path=rel,
                budget=budget,
            ):
                break

    return {
        "query": query,
        "hits": hits[:cap],
        "hit_count": min(len(hits), cap),
        "truncated": (not still()) or budget[0] >= MAX_TOTAL_CHARS,
    }
