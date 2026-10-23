"""Session file attachments — store under session.data_path/attachments/."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_window.models import Session as SessionModel
from agent_window.services.storage import get_session_path, sanitize_filename

MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024  # 2 MiB (text / generic)
MAX_IMAGE_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MiB (vision path)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
IMAGE_CONTENT_PREFIXES = ("image/",)

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".log", ".py", ".ts", ".tsx", ".js", ".jsx",
    ".html", ".css", ".xml", ".yaml", ".yml", ".sh", ".sql", ".toml", ".ini",
    ".cfg", ".conf", ".env", ".rst", ".r", ".go", ".rs", ".java", ".c", ".h",
    ".cpp", ".hpp", ".rb", ".php", ".swift", ".kt", ".scala", ".lua",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".tar",
    ".bin", ".dat", ".svg", ".ico", ".bmp", ".mp3", ".mp4", ".wav",
}


class AttachmentError(Exception):
    def __init__(self, message: str, code: str = "ATTACHMENT_ERROR") -> None:
        super().__init__(message)
        self.code = code


def attachments_dir(session: SessionModel) -> Path:
    d = get_session_path(session) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(filename: str) -> str:
    base = Path(filename or "upload").name
    safe = sanitize_filename(base)
    if "." in base and "." not in safe:
        ext = Path(base).suffix.lower()
        if ext and re.match(r"^\.\w{1,12}$", ext):
            safe = f"{safe}{ext}" if safe != "untitled" else f"upload{ext}"
    return safe[:120] or "upload"


def _ext_allowed(filename: str) -> bool:
    ext = Path(filename or "").suffix.lower()
    if not ext:
        return True
    return ext in ALLOWED_EXTENSIONS


def is_image_meta(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    ctype = str(meta.get("content_type") or "").lower().strip()
    if any(ctype.startswith(p) for p in IMAGE_CONTENT_PREFIXES):
        # SVG is XML text; keep out of vision pixel path.
        if "svg" in ctype:
            return False
        return True
    ext = Path(str(meta.get("filename") or "")).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def is_pdf_meta(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    ctype = str(meta.get("content_type") or "").lower()
    if "pdf" in ctype:
        return True
    return Path(str(meta.get("filename") or "")).suffix.lower() == ".pdf"


def _max_bytes_for(filename: str, content_type: str | None) -> int:
    probe = {"filename": filename, "content_type": content_type}
    if is_image_meta(probe):
        return MAX_IMAGE_ATTACHMENT_BYTES
    return MAX_ATTACHMENT_BYTES


def save_upload(
    session: SessionModel,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict[str, Any]:
    if not data:
        raise AttachmentError("empty file", "EMPTY_FILE")
    name = Path(filename or "upload").name or "upload"
    if not _ext_allowed(name):
        raise AttachmentError(f"file type not allowed: {Path(name).suffix}", "TYPE_NOT_ALLOWED")
    limit = _max_bytes_for(name, content_type)
    if len(data) > limit:
        raise AttachmentError(
            f"file too large (max {limit} bytes)",
            "TOO_LARGE",
        )

    attachment_id = uuid.uuid4().hex[:12]
    safe = _safe_name(name)
    stored_name = f"{attachment_id}__{safe}"
    root = attachments_dir(session)
    file_path = root / stored_name
    meta_path = root / f"{attachment_id}.meta.json"

    file_path.write_bytes(data)
    meta = {
        "id": attachment_id,
        "filename": name,
        "size": len(data),
        "content_type": content_type,
        "stored_name": stored_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def load_meta(session: SessionModel, attachment_id: str) -> dict[str, Any] | None:
    aid = (attachment_id or "").strip()
    if not aid or "/" in aid or "\\" in aid or ".." in aid:
        return None
    meta_path = attachments_dir(session) / f"{aid}.meta.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("id") != aid:
        return None
    return data


def resolve_file(session: SessionModel, attachment_id: str) -> Path:
    meta = load_meta(session, attachment_id)
    if not meta:
        raise AttachmentError("attachment not found", "NOT_FOUND")
    stored = meta.get("stored_name") or ""
    if "/" in stored or "\\" in stored or ".." in stored:
        raise AttachmentError("invalid stored name", "INVALID")
    path = attachments_dir(session) / stored
    if not path.is_file():
        raise AttachmentError("attachment file missing", "NOT_FOUND")
    root = attachments_dir(session).resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise AttachmentError("path escape", "INVALID") from exc
    return path


def list_metas_for_ids(session: SessionModel, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for aid in ids:
        meta = load_meta(session, aid)
        if meta:
            out.append(meta)
    return out


def read_attachment_text(
    session: SessionModel,
    attachment_id: str,
    offset: int = 1,
    limit: int = 200,
) -> dict[str, Any]:
    meta = load_meta(session, attachment_id)
    if not meta:
        raise AttachmentError("attachment not found", "NOT_FOUND")
    path = resolve_file(session, attachment_id)
    raw = path.read_bytes()
    filename = meta.get("filename") or path.name
    size = meta.get("size") or len(raw)

    if is_image_meta(meta):
        raise AttachmentError(
            f"image attachment is vision input this turn; do not read_attachment "
            f"(filename={filename}, size={size})",
            "NOT_TEXT",
        )

    if is_pdf_meta(meta):
        raise AttachmentError(
            f"PDF text extraction is not available yet (filename={filename}, size={size})",
            "NOT_TEXT",
        )

    if b"\x00" in raw[:4096]:
        raise AttachmentError(
            f"binary attachment; refuse text read (filename={filename}, size={size})",
            "NOT_TEXT",
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise AttachmentError(
                f"cannot decode as text (filename={filename}, size={size})",
                "NOT_TEXT",
            ) from exc

    lines = text.splitlines()
    total = len(lines)
    start = max(1, int(offset or 1))
    lim = max(1, min(int(limit or 200), 500))
    end = min(total, start + lim - 1)
    window = lines[start - 1 : end]
    numbered = "\n".join(f"{i}|{line}" for i, line in enumerate(window, start=start))
    return {
        "attachment_id": attachment_id,
        "filename": filename,
        "size": size,
        "offset": start,
        "limit": lim,
        "total_lines": total,
        "content": numbered,
        "truncated": end < total,
    }


def format_attachment_appendix(metas: list[dict[str, Any]]) -> str:
    if not metas:
        return ""
    lines = ["[附件]"]
    for m in metas:
        aid = m.get("id", "")
        name = m.get("filename", "?")
        size = m.get("size", 0)
        if is_image_meta(m):
            lines.append(
                f"- `{name}` (id={aid}, {size} bytes, image) — "
                "本轮已作为视觉输入注入；请直接描述图片，勿用 read_attachment 读图"
            )
        elif is_pdf_meta(m):
            lines.append(
                f"- `{name}` (id={aid}, {size} bytes, pdf) — "
                "PDF 暂不支持自动抽取正文；请说明需求或改用文本附件，勿自行写提取脚本"
            )
        else:
            lines.append(
                f'- `{name}` (id={aid}, {size} bytes) — '
                f'使用工具 read_attachment(attachment_id="{aid}") 读取'
            )
    return "\n".join(lines)


def build_content_for_model(user_text: str, metas: list[dict[str, Any]]) -> str:
    trimmed = (user_text or "").strip()
    appendix = format_attachment_appendix(metas)
    if appendix and trimmed:
        return f"{trimmed}\n\n{appendix}"
    if appendix:
        return f"（见附件）\n\n{appendix}"
    return trimmed


def _guess_image_mime(meta: dict[str, Any]) -> str:
    ctype = str(meta.get("content_type") or "").strip().lower()
    if ctype.startswith("image/") and "svg" not in ctype:
        return ctype.split(";")[0].strip() or "image/png"
    guessed, _ = mimetypes.guess_type(str(meta.get("filename") or ""))
    if guessed and guessed.startswith("image/") and "svg" not in guessed:
        return guessed
    return "image/png"


def image_data_url(session: SessionModel, meta: dict[str, Any]) -> str:
    path = resolve_file(session, str(meta["id"]))
    raw = path.read_bytes()
    mime = _guess_image_mime(meta)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def metas_have_images(metas: list[dict[str, Any]] | None) -> bool:
    return any(is_image_meta(m) for m in (metas or []))


def build_user_chat_message(
    session: SessionModel,
    user_text: str,
    metas: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build OpenAI-style user message; inject image_url parts for vision models."""
    metas = list(metas or [])
    text = build_content_for_model(user_text, metas)
    images = [m for m in metas if is_image_meta(m)]
    if not images:
        return {"role": "user", "content": text}
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for m in images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(session, m)},
            }
        )
    return {"role": "user", "content": parts}


def parse_attachments_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, dict) and m.get("id")]


def resolve_model_for_attachments(
    requested: str | None,
    metas: list[dict[str, Any]] | None,
    *,
    vision_model: str | None = None,
    default_text_model: str | None = None,
    default_vision_model: str | None = None,
) -> str:
    """Pick chat model; images require an explicit vision model id."""
    from agent_window.config import settings as app_settings

    text_model = (requested or default_text_model or app_settings.llm_model or "").strip()
    if not metas_have_images(metas):
        return text_model or app_settings.llm_model
    if "vision" in text_model.lower():
        return text_model
    vision = (
        (vision_model or "").strip()
        or (default_vision_model or "").strip()
        or (app_settings.llm_vision_model or "").strip()
    )
    if vision:
        return vision
    raise AttachmentError(
        "image attachments require a vision model; set vision_model in agent settings "
        "or LLM_VISION_MODEL / pick a model id containing 'vision'",
        "VISION_MODEL_REQUIRED",
    )
