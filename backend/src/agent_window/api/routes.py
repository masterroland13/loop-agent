"""API route handlers."""

import asyncio
import json
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from agent_window.config import settings
from agent_window.models import Role, get_db, get_sessionmaker
from agent_window.schemas import (
    AgentSettingsResponse,
    AgentSettingsUpdateRequest,
    AssetsResponse,
    AttachmentResponse,
    AuditEmitRequest,
    AuditEventResponse,
    AuditSessionSummary,
    ApplyPartialRequest,
    CreateSessionRequest,
    FavoriteItemResponse,
    FavoriteToggleRequest,
    HealthResponse,
    LlmConfigResponse,
    LlmConfigUpdateRequest,
    LlmTestResponse,
    ModelGlobalsUpdateRequest,
    ModelProfileCreateRequest,
    ModelProfileResponse,
    ModelProfilesListResponse,
    ProviderPresetResponse,
    ModelProfileUpdateRequest,
    MemoryContentResponse,
    MemoryContentUpdateRequest,
    MemoryProposalResponse,
    MessageRequest,
    MessageResponse,
    ModelsResponse,
    ModelInfo,
    PatchResponse,
    RegenerateRequest,
    RuntimeResponse,
    SessionResponse,
    ShellResponse,
    SkillActivateRequest,
    SkillInfo,
    SkillsResponse,
    SteerRequest,
    ToolInfo,
    ToolsResponse,
    UpdateSessionRequest,
    WorkspaceBrowseResponse,
    WorkspaceFileCopyRequest,
    WorkspaceFileCopyResponse,
    WorkspaceFileDeleteResponse,
    WorkspaceFilePathRequest,
    WorkspaceFilePathResponse,
    WorkspaceFileReadResponse,
    WorkspaceFileRevealResponse,
    WorkspaceFilesListResponse,
    WorkspaceFileRenameRequest,
    WorkspaceFileRenameResponse,
    WorkspaceFileTreeStatsResponse,
    WorkspaceFileWriteRequest,
    WorkspaceFileWriteResponse,
    WorkspaceSetRequest,
    WorkspaceStatusResponse,
)
from agent_window.agent.loop import run_agent_loop
from agent_window.core.event_sink import EventSink
from agent_window.core.goal_hooks import goal_change_audit_event, resolve_session_goal
from agent_window.core.loop_config import LoopConfig
from agent_window.core.session_tree import (
    build_llm_messages,
    build_path_from_session,
    last_user_on_path,
    path_ending_at,
)
from agent_window.core.steering import push_steering
from agent_window.core.tool_hooks import with_observe_spill
from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
from agent_window.services.attachment_context import use_attachment_session
from agent_window.services.attachments import (
    AttachmentError,
    build_content_for_model,
    build_user_chat_message,
    list_metas_for_ids,
    load_meta,
    parse_attachments_json,
    resolve_file,
    resolve_model_for_attachments,
    save_upload,
)
from agent_window.services.llm_config import public_llm_config, save_llm_config
from agent_window.services import model_registry as model_registry
from agent_window.services.audit import (
    audit_to_public,
    emit_audit,
    list_audit_events,
    list_audit_session_summaries,
)
from agent_window.services.compress import (
    approx_messages_tokens,
    approx_tokens,
    compress_messages_if_needed,
)
from agent_window.services.memory import (
    MEMORY_GUIDANCE,
    decide_memory,
    get_frozen_memory_md,
    get_frozen_user_md,
    get_memory_md_char_limit,
    get_user_md_char_limit,
    list_pending_memories,
    memory_md_path,
    memory_status,
    memory_status_for_target,
    memory_to_public,
    normalize_memory_target,
    path_for_target,
    read_for_target,
    read_memory_md,
    read_user_md,
    write_for_target,
)
from agent_window.services.patches import apply_partial_patch, decide_patch, list_pending, patch_to_public, retry_patch
from agent_window.services.provider import provider
from agent_window.services.session_turns import (
    SessionBusyError,
    cancel_turn,
    end_turn,
    runtime_info,
    try_begin_turn,
)
from agent_window.services.shell import decide_shell, list_pending_shells, retry_shell, shell_to_public
from agent_window.services.skills import (
    discover_skills,
    set_active_skills,
    skill_context_blocks,
    skill_status,
)
from agent_window.services.storage import (
    add_message,
    create_session,
    delete_session,
    get_message,
    get_session,
    list_favorites,
    list_sessions,
    read_session_blob,
    toggle_message_favorite,
    update_session_goal_mode,
    update_session_pinned_goal,
    update_session_title,
    update_session_workspace_root,
)
from agent_window.services.turn_trace import TurnTraceWriter, trace_for_response
from agent_window.services.workspace import (
    WorkspaceError,
    browse_directory,
    clear_workspace_root,
    get_workspace_root,
    copy_entry,
    delete_entry,
    list_directory,
    mkdir_directory,
    read_editor_file,
    read_text_file,
    rename_entry,
    reveal_in_explorer,
    set_workspace_root,
    tree_stats,
    workspace_status,
    write_editor_file,
    write_text_file,
)
from agent_window.tools.registry import registry

router = APIRouter()


def _parse_message_attachments(message, session_id: str) -> list[AttachmentResponse]:
    raw = getattr(message, "attachments", None) or "[]"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list):
        return []
    out: list[AttachmentResponse] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        aid = str(item["id"])
        out.append(
            AttachmentResponse(
                id=aid,
                filename=str(item.get("filename") or "file"),
                size=int(item.get("size") or 0),
                content_type=item.get("content_type"),
                url=f"/api/sessions/{session_id}/attachments/{aid}",
            )
        )
    return out


def _message_to_response(message) -> MessageResponse:
    session_id = getattr(message, "session_id", "") or ""
    return MessageResponse(
        id=message.id,
        role=message.role.value,
        content=message.content,
        sequence=message.sequence,
        is_favorite=message.is_favorite,
        summary=message.summary or None,
        trace=trace_for_response(message),
        attachments=_parse_message_attachments(message, session_id),
        created_at=message.created_at,
        parent_id=getattr(message, "parent_id", None),
        entry_type=getattr(message, "entry_type", None) or "message",
    )


def _resolve_turn_goal_for_session(
    session,
    *,
    user_text: str,
    history_messages: list,
    audit_source: str,
    session_id: str,
) -> tuple[str | None, str | None, bool]:
    """F1+F8: resolve turn goal (extract / pin) and emit goal.change when needed."""
    resolution = resolve_session_goal(
        goal_mode=bool(getattr(session, "goal_mode", False)),
        user_text=user_text,
        history_messages=history_messages,
        pinned_goal=getattr(session, "pinned_goal", None),
        audit_source=audit_source,
    )
    payload = goal_change_audit_event(resolution)
    if payload:
        _audit("goal.change", payload, session_id=session_id)
    return resolution.turn_goal, resolution.previous_goal, resolution.changed


async def _agent_turn_event_stream(
    *,
    session_id: str,
    session_local: Session,
    session_db,
    user_message_id: str,
    assistant_message_id: str,
    chat_messages: List[dict],
    turn_goal: str | None,
    model: str | None,
    model_name: str,
    cancel_event: asyncio.Event,
    compressed: bool,
    memory_injected: bool,
    prompt_tokens: int,
    started: float,
    http_request: Request,
    agent_cfg: dict,
    previous_goal: str | None = None,
    compress_method: str | None = None,
    compress_preview: str | None = None,
    model_fallback: bool = False,
    fallback_profile_id: str | None = None,
):
    """Yield SSE lines for one agent turn; persist F6 trace on placeholder assistant."""
    if not session_db:
        yield f"event: error\ndata: {json.dumps({'code': 'SESSION_NOT_FOUND', 'message': 'Session not found'}, ensure_ascii=False)}\n\n"
        return

    assistant_row = get_message(session_local, assistant_message_id)
    if not assistant_row:
        yield f"event: error\ndata: {json.dumps({'code': 'ASSISTANT_NOT_FOUND', 'message': 'Assistant placeholder missing'}, ensure_ascii=False)}\n\n"
        return

    writer = TurnTraceWriter(session_local, session_db, assistant_row)
    # Omit goal key when Goal mode is off so clients do not show the quality-ring banner.
    meta_payload: dict = {
        "message_id": user_message_id,
        "assistant_message_id": writer.assistant_id,
    }
    if turn_goal:
        meta_payload["goal"] = turn_goal
    if model_fallback:
        meta_payload["model_fallback"] = True
        meta_payload["model"] = model_name
        if fallback_profile_id:
            meta_payload["profile_id"] = fallback_profile_id
    yield (
        "event: meta\ndata: "
        f"{json.dumps(meta_payload, ensure_ascii=False)}\n\n"
    )

    assistant_content_parts: List[str] = []
    loop_cfg = with_observe_spill(
        LoopConfig.from_settings(
            goal_mode=bool(getattr(session_db, "goal_mode", False)),
            preset=agent_cfg.get("loop_preset") or "yolo",
        ),
        writer.spill,
    )

    async def _agent_events():
        with use_attachment_session(session_id):
            async for event in run_agent_loop(
                chat_messages,
                model=model,
                cancel_event=cancel_event,
                goal=turn_goal,
                previous_goal=previous_goal,
                config=loop_cfg,
                emit=EventSink(),
                session_id=session_id,
            ):
                yield event

    async for event in _agent_events():
        etype = event.get("type")
        mapped = None
        if etype in (
            "tool_start",
            "tool_result",
            "turn_goal",
            "progress_checkpoint",
            "await_approval",
            "diff",
            "shell",
            "memory",
            "token",
            "error",
            "agent_start",
            "agent_end",
            "turn_start",
            "turn_end",
            "steer_inject",
            "soft_land",
            "edit_nudge",
            "thought",
        ):
            mapped = writer.note_sse(event)

        if etype == "token":
            assistant_content_parts.append(event["content"])
            yield f"event: token\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype == "turn_goal":
            yield f"event: turn_goal\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype == "progress_checkpoint":
            yield f"event: progress_checkpoint\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype in (
            "agent_start",
            "agent_end",
            "turn_start",
            "turn_end",
            "steer_inject",
            "soft_land",
            "edit_nudge",
            "thought",
        ):
            yield f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype == "tools_disabled":
            emit_audit(
                session_local,
                "tools.disabled",
                payload={
                    "message": event.get("message"),
                    "reason": event.get("reason"),
                    "model": model_name,
                },
                session_id=session_id,
            )
            yield f"event: tools_disabled\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype in ("tool_start", "tool_result", "diff", "shell", "memory", "await_approval"):
            if etype == "memory" and event.get("status") == "applied":
                emit_audit(
                    session_local,
                    "memory.write",
                    payload={"id": event.get("memory_id"), "auto": not agent_cfg.get("confirm_memory", True)},
                    session_id=session_id,
                )
            elif etype == "memory" and event.get("status") == "rejected":
                emit_audit(
                    session_local,
                    "memory.reject",
                    payload={"id": event.get("memory_id")},
                    session_id=session_id,
                )
            out = dict(event)
            if mapped:
                if mapped.get("full_ref"):
                    out["full_ref"] = mapped["full_ref"]
                if mapped.get("truncated"):
                    out["truncated"] = mapped["truncated"]
                if mapped.get("summary") and etype == "tool_result":
                    out["summary"] = mapped["summary"]
            yield f"event: {etype}\ndata: {json.dumps(out, ensure_ascii=False)}\n\n"
        elif etype == "error":
            writer.finalize_interrupted(
                code=str(event.get("code") or "ERROR"),
                message=str(event.get("message") or "error"),
            )
            yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            return
        elif etype == "done":
            full_content = "".join(assistant_content_parts).strip()
            if not full_content:
                writer.delete_placeholder()
                yield (
                    "event: error\ndata: "
                    f"{json.dumps({'code': 'EMPTY_RESPONSE', 'message': '模型返回为空，请重试'}, ensure_ascii=False)}\n\n"
                )
                return
            turn_meta = {
                "type": "turn_meta",
                "model": model_name,
                "elapsed_ms": int((time.time() - started) * 1000),
                "approx_prompt_tokens": prompt_tokens,
                "approx_completion_tokens": approx_tokens(full_content),
                "compressed": compressed,
                "memory_injected": memory_injected,
                "message_id": writer.assistant_id,
            }
            if turn_goal:
                turn_meta["goal"] = turn_goal
            if compressed and compress_method:
                turn_meta["compress_method"] = compress_method
            if compressed and compress_preview:
                turn_meta["compress_preview"] = compress_preview
            writer.finalize(
                summary=json.dumps(turn_meta, ensure_ascii=False),
                content=full_content,
            )
            emit_audit(
                session_local,
                "turn.complete",
                payload={
                    "model": model_name,
                    "elapsed_ms": turn_meta["elapsed_ms"],
                    "goal": turn_goal,
                    "compressed": compressed,
                    "message_id": writer.assistant_id,
                    "approx_prompt_tokens": prompt_tokens,
                    "approx_completion_tokens": turn_meta["approx_completion_tokens"],
                },
                session_id=session_id,
            )
            yield f"event: turn_meta\ndata: {json.dumps(turn_meta, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'message_id': writer.assistant_id}, ensure_ascii=False)}\n\n"


async def _sse_detach_producer(agen_factory):
    """
    Relay an async generator to SSE consumers.

    When the client disconnects (page refresh), the producer task keeps running
    until the agent turn finishes. Only explicit POST /cancel should stop a turn.
    """
    queue: asyncio.Queue[tuple[str, object | None]] = asyncio.Queue()

    async def run() -> None:
        try:
            async for item in agen_factory():
                await queue.put(("item", item))
            await queue.put(("eof", None))
        except Exception as exc:
            await queue.put(("exc", exc))

    asyncio.create_task(run())
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "eof":
                break
            if kind == "item":
                yield payload
            elif kind == "exc":
                yield (
                    "event: error\ndata: "
                    f"{json.dumps({'code': 'INTERNAL_ERROR', 'message': str(payload)}, ensure_ascii=False)}\n\n"
                )
                break
    except asyncio.CancelledError:
        # Client left; producer continues in background.
        return


def _load_prompt_file(workspace_root: str, filename: str) -> str:
    """Read a prompt file from workspace root. Returns empty string if not found."""
    from pathlib import Path

    path = Path(workspace_root) / filename
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _system_prompt(session_id: str | None = None) -> str:
    import agent_window.tools  # noqa: F401

    tool_names = ", ".join(registry.list_names()) or "(none)"
    ws_root = get_workspace_root()
    ws_root_str = str(ws_root) if ws_root else ""

    # SYSTEM.md replaces the entire system prompt; APPEND_SYSTEM.md appends.
    system_override = _load_prompt_file(ws_root_str, "SYSTEM.md") if ws_root_str else ""
    system_append = _load_prompt_file(ws_root_str, "APPEND_SYSTEM.md") if ws_root_str else ""

    if ws_root:
        workspace_hint = (
            f"Workspace root is bound to: {ws_root}. "
            "Use list_dir, read_file, and grep for local files. "
            "To change files, call propose_edit and wait for user Apply; "
            "never claim a file was written/created/modified unless a propose_edit "
            "tool result shows status=applied. "
            "To delete a file, call propose_delete(path); do not use rm or helper scripts. "
            "To run tests or commands, call propose_shell with argv as a string array "
            '(e.g. ["pytest","-q"] or ["git","status"]); it waits for user approval. '
            "To remember durable preferences use propose_memory target=user; "
            "for workspace/project lessons use propose_memory target=memory. "
            "No shell piping/redirection. Prefer old_string+new_string after read_file. "
            "Paths and cwd are relative to the workspace root. "
            "If a propose_edit/propose_delete/propose_shell/propose_memory is rejected and the user asks "
            "to retry or revise the same request, you MUST call the same tool again instead "
            "of sending a plain text reply. "
            "If tools are unavailable, say so clearly and do not invent write or shell success."
        )
    else:
        workspace_hint = (
            "No workspace is configured yet. If the user asks about local files, "
            "tell them to set a folder via This PC first. Do not invent file contents. "
            "You may still call propose_memory (target=user or target=memory) for durable notes."
        )

    def _curated_block(
        *,
        label: str,
        raw: str,
        limit: int,
        frozen: bool,
        shrink_hint: str,
    ) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        n = len(text)
        body = text
        overflow_note = ""
        if n > limit:
            body = text[:limit]
            overflow_note = f"\n\n⚠️ {label} exceeds {limit} chars; {shrink_hint}"
        state = "frozen this session" if frozen else "long-term"
        header = f"## {label} ({state}; {n}/{limit} chars)"
        return "\n\n" + header + "\n" + body + overflow_note

    user_limit = get_user_md_char_limit()
    mem_limit = get_memory_md_char_limit()
    if session_id:
        raw_user_md = get_frozen_user_md(session_id)
        raw_memory_md = get_frozen_memory_md(session_id)
        frozen = True
    else:
        raw_user_md = read_user_md()
        raw_memory_md = read_memory_md()
        frozen = False

    memory_block = (
        "\n\n"
        + MEMORY_GUIDANCE
        + _curated_block(
            label="MEMORY.md",
            raw=raw_memory_md,
            limit=mem_limit,
            frozen=frozen,
            shrink_hint="propose_memory action=replace/remove or mode=replace target=memory to shrink.",
        )
        + _curated_block(
            label="USER.md",
            raw=raw_user_md,
            limit=user_limit,
            frozen=frozen,
            shrink_hint="propose_memory action=replace/remove or mode=replace target=user to shrink.",
        )
    )

    skill_blocks = skill_context_blocks()
    skills_section = ""
    if skill_blocks:
        skills_section = "\n\n" + "\n\n".join(skill_blocks)

    if system_override:
        base = system_override
    else:
        base = (
            "You are Loop Agent, a helpful coding assistant in this workspace. "
            "When you introduce yourself or name this product, say Loop Agent only; "
            "do not call it Hal Agent. "
            "Answer concisely in Chinese unless the user asks otherwise. "
            "When providing code, use Markdown code blocks with the language identifier. "
            "中文回复必须使用规范的全角标点（，。：；！？），不要在中文句子里夹半角逗号、冒号或句号；"
            "代码、命令、路径、英文术语保持半角原样。 "
            "行内反引号只用于真正需要区分的路径、符号名或短代码片段；"
            "不要给普通英文词、布尔字面量（True/False）、或正文里每个文件名都加反引号。 "
            f"You have tools available: {tool_names}. "
            f"{workspace_hint} "
            "If the user message includes an [附件] block: for text files call "
            "read_attachment(attachment_id=...) (not workspace read_file); "
            "for image attachments the pixels are already injected as multimodal content this turn — "
            "describe them directly and do NOT call read_attachment on images; "
            "PDF is not auto-extracted yet — do not invent extraction scripts. "
            "When the user message is only attachments (or starts with 「（见附件）」) without an explicit instruction "
            "(extract/save/write/create/convert/summarize-to-file/etc.), default to read-only: "
            "for text call read_attachment then give a short verbal summary; for images give a short verbal description; "
            "do NOT call propose_edit, propose_delete, or propose_shell to extract/persist attachment contents "
            "into the workspace, and do not invent helper scripts — unless the user explicitly asks to write files. "
            "When the user explicitly asks to save/write/persist an attachment into the workspace "
            "(e.g. 「把附件保存为 workspace 文件」/ save attachment to workspace), "
            "you MUST: (1) read_attachment for text if needed, then (2) call propose_edit with the file path + full contents; "
            "do not stop after read-only tools with an empty reply. "
            "When the user asks about weather, call get_weather. "
            "Do not invent tool results — always call the tool. "
            "When the user asks you to create, edit, or run something in the workspace, "
            "you MUST call the matching tool (propose_edit, propose_shell) instead of describing the action."
        )

    if system_append:
        base = base.rstrip() + "\n\n" + system_append

    return f"{base}{memory_block}{skills_section}"


def _sse_headers():
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _audit(event_type: str, payload: dict | None = None, session_id: str | None = None) -> None:
    db = get_sessionmaker()()
    try:
        emit_audit(db, event_type, payload=payload, session_id=session_id)
    finally:
        db.close()


async def _summarize_blob(blob: str, profile_id: str | None = None) -> str:
    """LLM compressor for auto_compress — handoff-oriented 6-section summary.

    ``profile_id`` selects the gateway. The summary uses that profile's default model.
    """
    turn = await provider.chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "你是交接摘要压缩器（CONTEXT CHECKPOINT）。"
                    "严格按用户给出的六个 ## 小节输出中文交接包；"
                    "Progress 与 Critical Context 必须写清已触及的文件路径；"
                    "若输入中没有 tool 结果，Progress 写「摘要窗口内未见工具结果」，禁止写「尚未开始」；"
                    "禁止把 Goal 原文复读进 Progress / Next Steps / Critical Context；"
                    "不要编造未出现的事实；不要输出小节以外的开场白或结语。"
                ),
            },
            {"role": "user", "content": blob},
        ],
        tools=None,
        model=None,
        max_tokens=2048,
        profile_id=profile_id,
    )
    return (turn.get("content") or "").strip()


def _session_to_response(session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        workspace_root=session.workspace_root,
        goal_mode=bool(session.goal_mode),
        pinned_goal=getattr(session, "pinned_goal", None),
        leaf_id=session.leaf_id,
        profile_id=getattr(session, "profile_id", None),
        model_id=getattr(session, "model_id", None),
        title_locked=bool(getattr(session, "title_locked", False)),
        last_prompt_at=getattr(session, "last_prompt_at", None),
    )


@router.get("/api/runtime", response_model=RuntimeResponse)
def runtime_endpoint():
    return RuntimeResponse(**runtime_info())


@router.post("/api/sessions/{session_id}/cancel")
def cancel_session_endpoint(session_id: str):
    cancelled = cancel_turn(session_id)
    return {"ok": True, "cancelled": cancelled}


@router.post("/api/sessions/{session_id}/steer")
def steer_session_endpoint(
    session_id: str,
    request: SteerRequest,
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = push_steering(session_id, request.content)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_STEER", "message": "content required"},
        )
    return {"ok": True, "queued": True}


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        provider=settings.llm_provider,
        provider_available=provider.is_available(),
    )


@router.get("/api/models", response_model=ModelsResponse)
async def list_models_endpoint():
    data = await provider.list_models()
    return ModelsResponse(
        models=[ModelInfo(**m) for m in data["models"]],
        default=data["default"],
        source=data["source"],
    )


@router.get("/api/settings", response_model=AgentSettingsResponse)
def get_settings_endpoint():
    return AgentSettingsResponse(**load_agent_settings())


@router.put("/api/settings", response_model=AgentSettingsResponse)
def put_settings_endpoint(
    request: AgentSettingsUpdateRequest,
    db: Session = Depends(get_db),
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    updated = save_agent_settings(request.model_dump(exclude_unset=True))
    audit_session_id = (session_id or x_session_id or "").strip() or None
    emit_audit(db, "settings.update", payload=updated, session_id=audit_session_id)
    return AgentSettingsResponse(**updated)


@router.get("/api/llm-config", response_model=LlmConfigResponse)
def get_llm_config_endpoint():
    return LlmConfigResponse(**public_llm_config())


@router.put("/api/llm-config", response_model=LlmConfigResponse)
def put_llm_config_endpoint(request: LlmConfigUpdateRequest, db: Session = Depends(get_db)):
    payload = request.model_dump(exclude_unset=True)
    try:
        saved = save_llm_config(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_LLM_CONFIG", "message": str(e)}) from e
    emit_audit(
        db,
        "llm.config",
        payload={
            "base_url": saved["base_url"],
            "default_model": saved["default_model"],
            "api_key_updated": "api_key" in payload and bool(payload["api_key"]),
        },
    )
    provider._sync_client()
    return LlmConfigResponse(**saved)


@router.post("/api/llm-config/test", response_model=LlmTestResponse)
async def test_llm_config_endpoint():
    """Ping the gateway by listing models; report latency."""
    import time as _time

    provider._sync_client()
    if not provider.is_available():
        return LlmTestResponse(ok=False, error="未配置 API Key")
    start = _time.monotonic()
    try:
        data = await provider.list_models()
    except Exception as e:
        return LlmTestResponse(ok=False, error=str(e)[:200])
    latency = int((_time.monotonic() - start) * 1000)
    count = len(data.get("models") or [])
    source = data.get("source")
    if source == "fallback":
        return LlmTestResponse(ok=False, latency_ms=latency, error="网关未返回模型列表（用了本地备用列表）")
    return LlmTestResponse(ok=True, latency_ms=latency, model_count=count)


def _bind_turn_model(session, request_model: str | None, db: Session) -> tuple[str, bool, str]:
    """Resolve profile + model for this turn and pin the profile on the SSE task context."""
    from agent_window.services.provider import turn_profile_id

    binding = model_registry.resolve_turn_binding(
        getattr(session, "profile_id", None),
        getattr(session, "model_id", None),
        request_model,
    )
    if binding["fallback"]:
        session.profile_id = binding["profile_id"] or None
        session.model_id = binding["model_id"] or None
        db.commit()
    turn_profile_id.set(binding["profile_id"] or None)
    return binding["model_id"], bool(binding["fallback"]), binding["profile_id"]


@router.get("/api/model-profile-presets", response_model=List[ProviderPresetResponse])
def list_model_profile_presets():
    from agent_window.services.provider_presets import list_provider_presets

    return [ProviderPresetResponse(**row) for row in list_provider_presets()]


@router.get("/api/model-profiles", response_model=ModelProfilesListResponse)
def list_model_profiles_endpoint():
    data = model_registry.list_profiles_public()
    return ModelProfilesListResponse(**data)


@router.post("/api/model-profiles", response_model=ModelProfileResponse)
def create_model_profile_endpoint(request: ModelProfileCreateRequest, db: Session = Depends(get_db)):
    try:
        created = model_registry.create_profile(
            label=request.label,
            base_url=request.base_url,
            api_key=request.api_key,
            model_id=request.model_id,
            enabled=request.enabled,
            activate=request.activate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_MODEL_PROFILE", "message": str(e)}) from e
    emit_audit(db, "model_profile.create", payload={"id": created["id"], "label": created["label"]})
    provider._sync_client()
    return ModelProfileResponse(**created)


@router.patch("/api/model-profiles/{profile_id}", response_model=ModelProfilesListResponse)
def update_model_profile_endpoint(
    profile_id: str,
    request: ModelProfileUpdateRequest,
    db: Session = Depends(get_db),
):
    payload = request.model_dump(exclude_unset=True)
    globals_patch = {}
    if "temperature" in payload:
        globals_patch["temperature"] = payload.pop("temperature")
    if "max_tokens" in payload:
        globals_patch["max_tokens"] = payload.pop("max_tokens")
    try:
        if payload:
            model_registry.update_profile(profile_id, payload)
        if globals_patch:
            model_registry.update_globals(**globals_patch)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "PROFILE_NOT_FOUND", "message": "档案不存在"}) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_MODEL_PROFILE", "message": str(e)}) from e
    emit_audit(
        db,
        "model_profile.update",
        payload={
            "id": profile_id,
            "api_key_updated": "api_key" in payload and bool(payload.get("api_key")),
        },
    )
    provider._sync_client()
    return ModelProfilesListResponse(**model_registry.list_profiles_public())


@router.delete("/api/model-profiles/{profile_id}", response_model=ModelProfilesListResponse)
def delete_model_profile_endpoint(profile_id: str, db: Session = Depends(get_db)):
    try:
        data = model_registry.delete_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "PROFILE_NOT_FOUND", "message": "档案不存在"}) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "CANNOT_DELETE_PROFILE", "message": str(e)}) from e
    emit_audit(db, "model_profile.delete", payload={"id": profile_id})
    provider._sync_client()
    return ModelProfilesListResponse(**data)


@router.post("/api/model-profiles/{profile_id}/activate", response_model=ModelProfilesListResponse)
def activate_model_profile_endpoint(profile_id: str, db: Session = Depends(get_db)):
    try:
        data = model_registry.set_active(profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "PROFILE_NOT_FOUND", "message": "档案不存在"}) from None
    emit_audit(db, "model_profile.activate", payload={"id": profile_id})
    provider._sync_client()
    return ModelProfilesListResponse(**data)


@router.put("/api/model-profiles/globals", response_model=ModelProfilesListResponse)
def update_model_globals_endpoint(request: ModelGlobalsUpdateRequest, db: Session = Depends(get_db)):
    try:
        data = model_registry.update_globals(
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_MODEL_GLOBALS", "message": str(e)}) from e
    emit_audit(db, "model_profile.globals", payload=request.model_dump(exclude_unset=True))
    return ModelProfilesListResponse(**data)


@router.post("/api/model-profiles/{profile_id}/test", response_model=LlmTestResponse)
async def test_model_profile_endpoint(profile_id: str):
    import time as _time

    if model_registry.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PROFILE_NOT_FOUND", "message": "档案不存在"})
    start = _time.monotonic()
    result = await provider.test_profile(profile_id)
    latency = int((_time.monotonic() - start) * 1000)
    return LlmTestResponse(
        ok=bool(result.get("ok")),
        latency_ms=latency,
        model_count=result.get("model_count"),
        error=result.get("error"),
    )


@router.get("/api/tools", response_model=ToolsResponse)
def list_tools_endpoint():
    import agent_window.tools  # noqa: F401  (ensure registration)

    agent = load_agent_settings()
    disabled = [str(t) for t in agent.get("disabled_tools") or []]
    tools = [
        ToolInfo(name=name, description=(registry.get(name).description if registry.get(name) else ""))
        for name in registry.list_names()
    ]
    return ToolsResponse(tools=tools, disabled_tools=disabled)


@router.get("/api/memory/content", response_model=MemoryContentResponse)
def get_memory_content_endpoint(target: str = Query(default="user")):
    return _memory_content_response(target)


@router.put("/api/memory/content", response_model=MemoryContentResponse)
def put_memory_content_endpoint(request: MemoryContentUpdateRequest, db: Session = Depends(get_db)):
    return _put_memory_content(request.content, request.target, db)


@router.get("/api/memory/tracks/{target}/content", response_model=MemoryContentResponse)
def get_memory_track_content_endpoint(target: str):
    """Path-style track API (avoids query-param ambiguity with stale proxies)."""
    return _memory_content_response(target)


@router.put("/api/memory/tracks/{target}/content", response_model=MemoryContentResponse)
def put_memory_track_content_endpoint(
    target: str,
    request: MemoryContentUpdateRequest,
    db: Session = Depends(get_db),
):
    # Path target wins over body target.
    return _put_memory_content(request.content, target, db)


def _memory_content_response(target: str) -> MemoryContentResponse:
    t = normalize_memory_target(target)
    content = read_for_target(t)
    st = memory_status_for_target(t)
    path = str(path_for_target(t))
    expected_name = "MEMORY.md" if t == "memory" else "USER.md"
    if not path.replace("\\", "/").endswith(expected_name):
        raise HTTPException(
            status_code=500,
            detail={"code": "MEMORY_PATH_MISMATCH", "message": f"expected {expected_name}, got {path}"},
        )
    return MemoryContentResponse(
        content=content,
        path=path,
        target=t,
        chars=st["chars"],
        limit=st["limit"],
    )


def _put_memory_content(content: str, target: str, db: Session) -> MemoryContentResponse:
    t = normalize_memory_target(target)
    write_for_target(t, content)
    emit_audit(
        db,
        "memory.direct_edit",
        payload={"size": len(content), "target": t},
    )
    return _memory_content_response(t)


@router.get("/api/skills", response_model=SkillsResponse)
def list_skills_endpoint():
    status = skill_status()
    return SkillsResponse(
        workspace_configured=status["workspace_configured"],
        workspace_root=status.get("workspace_root"),
        skills=[SkillInfo(**s) for s in discover_skills()],
        active_skills=status["active_skills"],
        agents_md_exists=status["agents_md_exists"],
    )


@router.put("/api/skills/active", response_model=SkillsResponse)
def set_active_skills_endpoint(request: SkillActivateRequest, db: Session = Depends(get_db)):
    updated = set_active_skills(request.active_skills)
    emit_audit(db, "skill.activate", payload={"active_skills": updated["active_skills"]})
    return list_skills_endpoint()


@router.get("/api/assets", response_model=AssetsResponse)
def assets_endpoint(db: Session = Depends(get_db)):
    mem = memory_status()
    mem_md = mem.get("memory_md") or {}
    ws = workspace_status()
    agent = load_agent_settings()
    return AssetsResponse(
        status="ok",
        provider=settings.llm_provider,
        provider_available=provider.is_available(),
        session_count=len(list_sessions(db)),
        user_md_exists=mem["exists"],
        user_md_path=mem["path"],
        user_md_size=mem["size"],
        memory_md_exists=bool(mem_md.get("exists")),
        memory_md_path=str(mem_md.get("path") or memory_md_path()),
        memory_md_size=int(mem_md.get("size") or 0),
        user_md_chars=int(mem.get("chars") or 0),
        user_md_limit=int(mem.get("limit") or get_user_md_char_limit()),
        memory_md_chars=int(mem_md.get("chars") or 0),
        memory_md_limit=int(mem_md.get("limit") or get_memory_md_char_limit()),
        workspace_configured=ws["configured"],
        workspace_root=ws["root"],
        settings=AgentSettingsResponse(**agent),
    )


@router.get("/api/audit", response_model=List[AuditEventResponse])
def list_audit_endpoint(
    limit: int = 50,
    session_id: str | None = None,
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    events = list_audit_events(
        db,
        limit=limit,
        session_id=session_id,
        event_type=event_type,
    )
    return [AuditEventResponse(**audit_to_public(e)) for e in events]


@router.get("/api/audit/sessions", response_model=List[AuditSessionSummary])
def list_audit_sessions_endpoint(limit: int = 50, db: Session = Depends(get_db)):
    """Sessions that have audit activity — for replay filter UI."""
    return [AuditSessionSummary(**row) for row in list_audit_session_summaries(db, limit=limit)]


@router.get("/api/sessions/{session_id}/audit", response_model=List[AuditEventResponse])
def list_session_audit_endpoint(
    session_id: str,
    limit: int = 100,
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events = list_audit_events(
        db,
        limit=limit,
        session_id=session_id,
        event_type=event_type,
    )
    return [AuditEventResponse(**audit_to_public(e)) for e in events]


@router.post("/api/audit", response_model=AuditEventResponse)
def emit_audit_endpoint(request: AuditEmitRequest, db: Session = Depends(get_db)):
    event = emit_audit(
        db,
        request.event_type,
        payload=request.payload,
        session_id=request.session_id,
    )
    return AuditEventResponse(**audit_to_public(event))


@router.get("/api/memory")
def get_memory_endpoint(target: str = "user"):
    t = normalize_memory_target(target)
    st = memory_status_for_target(t)
    return {
        "exists": st["exists"],
        "path": st["path"],
        "size": st["size"],
        "preview": st["preview"],
        "chars": st["chars"],
        "limit": st["limit"],
        "target": t,
        "content": read_for_target(t),
    }


@router.get("/api/memory/proposals", response_model=List[MemoryProposalResponse])
def list_memory_proposals_endpoint(session_id: Optional[str] = None):
    return [MemoryProposalResponse(**m) for m in list_pending_memories(session_id)]


@router.post("/api/memory/proposals/{proposal_id}/apply", response_model=MemoryProposalResponse)
async def apply_memory_endpoint(proposal_id: str, db: Session = Depends(get_db)):
    try:
        item = await decide_memory(proposal_id, "apply")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(db, "memory.write", payload={"id": item.id, "mode": item.mode, "status": item.status.value})
    return MemoryProposalResponse(**memory_to_public(item))


@router.post("/api/memory/proposals/{proposal_id}/reject", response_model=MemoryProposalResponse)
async def reject_memory_endpoint(proposal_id: str, db: Session = Depends(get_db)):
    try:
        item = await decide_memory(proposal_id, "reject")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(db, "memory.reject", payload={"id": item.id, "mode": item.mode})
    return MemoryProposalResponse(**memory_to_public(item))


@router.get("/api/workspace", response_model=WorkspaceStatusResponse)
def get_workspace_endpoint():
    return WorkspaceStatusResponse(**workspace_status())


@router.put("/api/workspace", response_model=WorkspaceStatusResponse)
def set_workspace_endpoint(request: WorkspaceSetRequest, db: Session = Depends(get_db)):
    try:
        set_workspace_root(request.root)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)}) from e
    status = workspace_status()
    emit_audit(db, "workspace.set", payload=status)
    return WorkspaceStatusResponse(**status)


@router.delete("/api/workspace", response_model=WorkspaceStatusResponse)
def clear_workspace_endpoint():
    clear_workspace_root()
    return WorkspaceStatusResponse(**workspace_status())


@router.get("/api/workspace/browse", response_model=WorkspaceBrowseResponse)
def browse_workspace_endpoint(path: str | None = None):
    try:
        data = browse_directory(path)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)}) from e
    return WorkspaceBrowseResponse(**data)


def _workspace_files_http_status(code: str) -> int:
    if code == "NOT_FOUND":
        return 404
    if code in ("CONFLICT", "EXISTS"):
        return 409
    return 400


def _workspace_file_mtime_str(data: dict) -> dict:
    """JSON numbers lose ns precision in JS; expose mtime as a decimal string."""
    out = dict(data)
    out["mtime_ns"] = str(out["mtime_ns"])
    return out


def _parse_if_match_mtime_ns(value: int | str | None) -> int | None:
    if value is None:
        return None
    return int(value)


@router.get("/api/workspace/files/list", response_model=WorkspaceFilesListResponse)
def workspace_files_list_endpoint(path: str = Query(default=".", max_length=4096)):
    try:
        data = list_directory(path=path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    return WorkspaceFilesListResponse(**data)


@router.get("/api/workspace/files/read", response_model=WorkspaceFileReadResponse)
def workspace_files_read_endpoint(path: str = Query(..., min_length=1, max_length=4096)):
    try:
        data = read_editor_file(path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    return WorkspaceFileReadResponse(**_workspace_file_mtime_str(data))


@router.put("/api/workspace/files/write", response_model=WorkspaceFileWriteResponse)
def workspace_files_write_endpoint(request: WorkspaceFileWriteRequest, db: Session = Depends(get_db)):
    try:
        data = write_editor_file(
            path=request.path,
            content=request.content,
            if_match_mtime_ns=_parse_if_match_mtime_ns(request.if_match_mtime_ns),
            if_match_base_content=request.if_match_base_content,
            encoding=request.encoding,
        )
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(
        db,
        "files.write",
        payload={"path": data["path"], "size": data["size"]},
    )
    return WorkspaceFileWriteResponse(**_workspace_file_mtime_str(data))


@router.post("/api/workspace/files/mkdir", response_model=WorkspaceFilePathResponse)
def workspace_files_mkdir_endpoint(request: WorkspaceFilePathRequest, db: Session = Depends(get_db)):
    try:
        data = mkdir_directory(path=request.path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(db, "files.mkdir", payload={"path": data["path"]})
    return WorkspaceFilePathResponse(**data)


@router.post("/api/workspace/files/rename", response_model=WorkspaceFileRenameResponse)
def workspace_files_rename_endpoint(request: WorkspaceFileRenameRequest, db: Session = Depends(get_db)):
    try:
        data = rename_entry(from_path=request.from_path, to_path=request.to_path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(
        db,
        "files.rename",
        payload={"from": data["from"], "path": data["path"]},
    )
    return WorkspaceFileRenameResponse(**data)


@router.get("/api/workspace/files/stats", response_model=WorkspaceFileTreeStatsResponse)
def workspace_files_stats_endpoint(path: str = Query(..., min_length=1, max_length=4096)):
    try:
        data = tree_stats(path=path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    return WorkspaceFileTreeStatsResponse(**data)


@router.post("/api/workspace/files/copy", response_model=WorkspaceFileCopyResponse)
def workspace_files_copy_endpoint(request: WorkspaceFileCopyRequest, db: Session = Depends(get_db)):
    try:
        data = copy_entry(from_path=request.from_path, to_path=request.to_path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(
        db,
        "files.copy",
        payload={"from": data["from"], "path": data["path"]},
    )
    return WorkspaceFileCopyResponse(**data)


@router.post("/api/workspace/files/reveal", response_model=WorkspaceFileRevealResponse)
def workspace_files_reveal_endpoint(request: WorkspaceFilePathRequest, db: Session = Depends(get_db)):
    try:
        data = reveal_in_explorer(path=request.path)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(db, "files.reveal", payload={"path": data["path"]})
    return WorkspaceFileRevealResponse(**data)


@router.delete("/api/workspace/files/delete", response_model=WorkspaceFileDeleteResponse)
def workspace_files_delete_endpoint(
    path: str = Query(..., min_length=1, max_length=4096),
    recursive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    try:
        data = delete_entry(path=path, recursive=recursive)
    except WorkspaceError as e:
        raise HTTPException(
            status_code=_workspace_files_http_status(e.code),
            detail={"code": e.code, "message": str(e)},
        ) from e
    emit_audit(
        db,
        "files.delete",
        payload={"path": data["path"], "recursive": data["recursive"]},
    )
    return WorkspaceFileDeleteResponse(**data)


@router.get("/api/workspace/patches", response_model=List[PatchResponse])
def list_patches_endpoint(session_id: Optional[str] = None):
    return [PatchResponse(**p) for p in list_pending(session_id)]


@router.post("/api/workspace/patches/{patch_id}/apply", response_model=PatchResponse)
async def apply_patch_endpoint(patch_id: str, db: Session = Depends(get_db)):
    try:
        patch = await decide_patch(patch_id, "apply")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "patch.apply",
        payload={
            "patch_id": patch_id,
            "status": patch.status.value,
            "path": patch.path,
            "error": patch.error,
        },
    )
    return PatchResponse(**patch_to_public(patch))


@router.post("/api/workspace/patches/{patch_id}/apply-partial", response_model=PatchResponse)
async def apply_partial_patch_endpoint(patch_id: str, request: ApplyPartialRequest, db: Session = Depends(get_db)):
    try:
        patch = await apply_partial_patch(patch_id, request.hunk_ids)
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "patch.apply_partial",
        payload={
            "patch_id": patch_id,
            "status": patch.status.value,
            "path": patch.path,
            "applied_hunks": patch.applied_hunks,
            "error": patch.error,
        },
    )
    return PatchResponse(**patch_to_public(patch))


@router.post("/api/workspace/patches/{patch_id}/reject", response_model=PatchResponse)
async def reject_patch_endpoint(patch_id: str, db: Session = Depends(get_db)):
    try:
        patch = await decide_patch(patch_id, "reject")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "patch.reject",
        payload={"patch_id": patch_id, "status": patch.status.value, "path": patch.path},
    )
    return PatchResponse(**patch_to_public(patch))


@router.post("/api/workspace/patches/{patch_id}/retry", response_model=PatchResponse)
async def retry_patch_endpoint(patch_id: str, db: Session = Depends(get_db)):
    try:
        patch = await retry_patch(patch_id)
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "patch.retry",
        payload={
            "patch_id": patch_id,
            "status": patch.status.value,
            "path": patch.path,
            "error": patch.error,
        },
    )
    return PatchResponse(**patch_to_public(patch))


@router.get("/api/workspace/shells", response_model=List[ShellResponse])
def list_shells_endpoint(session_id: Optional[str] = None):
    return [ShellResponse(**s) for s in list_pending_shells(session_id)]


@router.post("/api/workspace/shells/{shell_id}/apply", response_model=ShellResponse)
async def apply_shell_endpoint(shell_id: str, db: Session = Depends(get_db)):
    try:
        item = await decide_shell(shell_id, "apply")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "shell.apply",
        payload={
            "shell_id": shell_id,
            "status": item.status.value,
            "command": item.command_display,
            "exit_code": item.exit_code,
            "error": item.error,
        },
    )
    return ShellResponse(**shell_to_public(item))


@router.post("/api/workspace/shells/{shell_id}/reject", response_model=ShellResponse)
async def reject_shell_endpoint(shell_id: str, db: Session = Depends(get_db)):
    try:
        item = await decide_shell(shell_id, "reject")
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "shell.reject",
        payload={
            "shell_id": shell_id,
            "status": item.status.value,
            "command": item.command_display,
        },
    )
    return ShellResponse(**shell_to_public(item))


@router.post("/api/workspace/shells/{shell_id}/retry", response_model=ShellResponse)
async def retry_shell_endpoint(shell_id: str, db: Session = Depends(get_db)):
    try:
        item = await retry_shell(shell_id)
    except WorkspaceError as e:
        status = 404 if e.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "shell.retry",
        payload={
            "shell_id": shell_id,
            "status": item.status.value,
            "command": item.command_display,
            "error": item.error,
        },
    )
    return ShellResponse(**shell_to_public(item))


@router.post("/api/sessions", response_model=SessionResponse)
def create_session_endpoint(request: CreateSessionRequest, db: Session = Depends(get_db)):
    session = create_session(db, title=request.title, workspace_root=request.workspace_root)
    return _session_to_response(session)


@router.get("/api/sessions/{session_id}", response_model=SessionResponse)
def get_session_endpoint(session_id: str, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)


@router.patch("/api/sessions/{session_id}", response_model=SessionResponse)
def update_session_endpoint(session_id: str, request: UpdateSessionRequest, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if request.title is not None:
        session = update_session_title(db, session, request.title.strip())
    if request.title_locked is True:
        session.title_locked = True
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
    if request.goal_mode is not None:
        session = update_session_goal_mode(db, session, request.goal_mode)
    if "workspace_root" in request.model_fields_set:
        root = (request.workspace_root or "").strip()
        if not root:
            raise HTTPException(
                status_code=400,
                detail="Unbinding is not supported; workspace_root is required",
            )
        try:
            session = update_session_workspace_root(db, session, root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "profile_id" in request.model_fields_set or "model_id" in request.model_fields_set:
        if "profile_id" in request.model_fields_set:
            pid = (request.profile_id or "").strip()
            if pid and model_registry.resolve_handle(pid) is None:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "PROFILE_NOT_FOUND", "message": "档案不存在或已停用"},
                )
            session.profile_id = pid or None
        if "model_id" in request.model_fields_set:
            session.model_id = (request.model_id or "").strip() or None
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
    if "pinned_goal" in request.model_fields_set:
        from agent_window.agent.goal import (
            goals_equal,
            normalize_pinned_goal,
            previous_turn_goal_from_messages,
        )

        new_pin = normalize_pinned_goal(request.pinned_goal)
        old_pin = getattr(session, "pinned_goal", None)
        changed = not goals_equal(old_pin, new_pin)
        if changed or (old_pin or None) != new_pin:
            session = update_session_pinned_goal(db, session, new_pin)
        if changed and new_pin:
            prev = old_pin
            if not prev:
                path = build_path_from_session(session)
                prev = previous_turn_goal_from_messages(path)
            if not goals_equal(prev, new_pin):
                emit_audit(
                    db,
                    "goal.change",
                    payload={
                        "previous_goal": prev,
                        "goal": new_pin,
                        "source": "manual",
                    },
                    session_id=session_id,
                )
    return _session_to_response(session)


@router.delete("/api/sessions/{session_id}")
def delete_session_endpoint(session_id: str, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    title = session.title
    delete_session(db, session)
    emit_audit(db, "session.delete", payload={"session_id": session_id, "title": title}, session_id=session_id)
    return {"ok": True}


@router.patch("/api/messages/{message_id}/favorite", response_model=MessageResponse)
def toggle_favorite_endpoint(message_id: str, request: FavoriteToggleRequest, db: Session = Depends(get_db)):
    message = get_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != Role.USER:
        raise HTTPException(status_code=400, detail="Only user messages can be favorited")
    message = toggle_message_favorite(db, message, request.is_favorite)
    return _message_to_response(message)


@router.get("/api/favorites", response_model=List[FavoriteItemResponse])
def list_favorites_endpoint(db: Session = Depends(get_db)):
    items = list_favorites(db)
    return [
        FavoriteItemResponse(
            id=item["id"],
            session_id=item["session_id"],
            session_title=item["session_title"],
            user_content=item["user_content"],
            assistant_content=item["assistant_content"],
            created_at=item["created_at"],
        )
        for item in items
    ]


@router.get("/api/sessions", response_model=List[SessionResponse])
def list_sessions_endpoint(db: Session = Depends(get_db)):
    sessions = list_sessions(db)
    return [_session_to_response(s) for s in sessions]


@router.get("/api/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages_endpoint(
    session_id: str,
    view: str = Query(
        "all",
        description="all = every message (incl. abandoned siblings); active = leaf→root path only",
    ),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    view_norm = (view or "all").strip().lower()
    if view_norm == "active":
        path = build_path_from_session(session)
        return [_message_to_response(m) for m in path]
    if view_norm != "all":
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_VIEW", "message": "view must be 'all' or 'active'"},
        )
    existing_messages = sorted(session.messages, key=lambda m: m.sequence)
    return [_message_to_response(m) for m in existing_messages]




@router.post("/api/sessions/{session_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment_endpoint(
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    data = await file.read()
    try:
        meta = save_upload(session, file.filename or "upload", data, file.content_type)
    except AttachmentError as e:
        status = 413 if e.code == "TOO_LARGE" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)}) from e
    emit_audit(
        db,
        "attachment.upload",
        payload={"id": meta["id"], "filename": meta["filename"], "size": meta["size"]},
        session_id=session_id,
    )
    return AttachmentResponse(
        id=meta["id"],
        filename=meta["filename"],
        size=meta["size"],
        content_type=meta.get("content_type"),
        url=f"/api/sessions/{session_id}/attachments/{meta['id']}",
    )


@router.get("/api/sessions/{session_id}/attachments/{attachment_id}")
def download_attachment_endpoint(
    session_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    meta = load_meta(session, attachment_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        path = resolve_file(session, attachment_id)
    except AttachmentError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return FileResponse(
        path,
        filename=meta.get("filename") or path.name,
        media_type=meta.get("content_type") or "application/octet-stream",
    )

@router.get("/api/sessions/{session_id}/blobs")
def get_session_blob_endpoint(
    session_id: str,
    ref: str = Query(..., min_length=1, description="file:turns/... ref from TurnEvent.full_ref"),
    db: Session = Depends(get_db),
):
    """Fetch oversized tool payload spilled under session.data_path."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        text = read_session_blob(session, ref)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Blob not found") from None
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@router.post("/api/sessions/{session_id}/messages")
async def send_message_endpoint(
    session_id: str,
    request: MessageRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        cancel_event = try_begin_turn(session_id)
    except SessionBusyError:
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_BUSY", "message": "该会话正在处理中，请稍候或先停止当前回复"},
        )

    try:
        # Path to current leaf before appending this turn (LLM history base)
        prior_path = build_path_from_session(session)
        existing_messages = sorted(session.messages, key=lambda m: m.sequence)
        next_sequence = (existing_messages[-1].sequence + 1) if existing_messages else 1
        parent_for_user = session.leaf_id

        attachment_ids = list(request.attachment_ids or [])
        metas = list_metas_for_ids(session, attachment_ids) if attachment_ids else []
        if attachment_ids and len(metas) != len(attachment_ids):
            found = {m["id"] for m in metas}
            missing = [aid for aid in attachment_ids if aid not in found]
            raise HTTPException(
                status_code=400,
                detail={"code": "ATTACHMENT_NOT_FOUND", "message": f"unknown attachment_ids: {missing}"},
            )

        content_for_model = build_content_for_model(request.content or "", metas)
        attachments_json = json.dumps(metas, ensure_ascii=False) if metas else "[]"

        agent_cfg = load_agent_settings()
        bound_model, model_fallback, _turn_profile = _bind_turn_model(session, request.model, db)
        if not provider.profile_is_ready(_turn_profile):
            raise HTTPException(status_code=503, detail="LLM provider not configured")

        async def _summarize_for_turn(blob: str) -> str:
            return await _summarize_blob(blob, _turn_profile)

        try:
            model_name = resolve_model_for_attachments(
                bound_model,
                metas,
                vision_model=agent_cfg.get("vision_model"),
            )
        except AttachmentError as e:
            if e.code == "VISION_MODEL_REQUIRED":
                raise HTTPException(
                    status_code=400,
                    detail={"code": e.code, "message": str(e)},
                ) from e
            raise

        user_message = add_message(
            db,
            session,
            Role.USER,
            content_for_model,
            next_sequence,
            attachments=attachments_json,
            parent_id=parent_for_user,
        )
        assistant_sequence = next_sequence + 1
        assistant_message = add_message(
            db,
            session,
            Role.ASSISTANT,
            "",
            assistant_sequence,
            summary="",
            trace="[]",
            parent_id=user_message.id,
        )

        system_prompt = _system_prompt(session_id)
        memory_injected = bool(
            get_frozen_user_md(session_id).strip() or get_frozen_memory_md(session_id).strip()
        )

        loop_cfg = LoopConfig.from_settings(
            goal_mode=bool(getattr(session, "goal_mode", False)),
            preset=agent_cfg.get("loop_preset", "yolo"),
        )
        chat_messages = build_llm_messages(
            prior_path,
            convert_to_llm=loop_cfg.convert_to_llm,
            system_prompt=system_prompt,
        )
        chat_messages.append(build_user_chat_message(session, request.content or "", metas))

        prev_goal_for_stream: str | None
        turn_goal, prev_goal_for_stream, _goal_changed = _resolve_turn_goal_for_session(
            session,
            user_text=content_for_model,
            history_messages=list(prior_path),
            audit_source="extract",
            session_id=session_id,
        )

        chat_messages, compressed, compress_meta = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_for_turn,
            preserve_goal=turn_goal,
        )
        if compressed:
            _audit(
                "context.compress",
                {
                    "session_id": session_id,
                    "goal_preserved": bool(turn_goal),
                    "method": compress_meta.method,
                    "older_count": compress_meta.older_count,
                    "used_previous_summary": compress_meta.used_previous_summary,
                    "preview": compress_meta.summary_preview,
                },
                session_id=session_id,
            )

        prompt_tokens = approx_messages_tokens(chat_messages)
        started = time.time()

        async def event_stream():
            async def produce():
                from agent_window.services.provider import turn_profile_id

                turn_profile_id.set(_turn_profile or None)
                session_local = get_sessionmaker()()
                try:
                    async for line in _agent_turn_event_stream(
                        session_id=session_id,
                        session_local=session_local,
                        session_db=get_session(session_local, session_id),
                        user_message_id=user_message.id,
                        assistant_message_id=assistant_message.id,
                        chat_messages=chat_messages,
                        turn_goal=turn_goal,
                        previous_goal=prev_goal_for_stream,
                        model=model_name,
                        model_name=model_name,
                        cancel_event=cancel_event,
                        compressed=compressed,
                        memory_injected=memory_injected,
                        prompt_tokens=prompt_tokens,
                        started=started,
                        http_request=http_request,
                        agent_cfg=agent_cfg,
                        compress_method=compress_meta.method if compressed else None,
                        compress_preview=compress_meta.summary_preview if compressed else None,
                        model_fallback=model_fallback,
                        fallback_profile_id=_turn_profile or None,
                    ):
                        yield line
                finally:
                    end_turn(session_id)
                    session_local.close()

            async for line in _sse_detach_producer(produce):
                yield line

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_sse_headers())
    except Exception:
        end_turn(session_id)
        raise


@router.post("/api/sessions/{session_id}/regenerate")
async def regenerate_endpoint(
    session_id: str,
    http_request: Request,
    request: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    """Re-run the agent on the last user turn without inserting a new user message."""
    payload = request or RegenerateRequest()
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        cancel_event = try_begin_turn(session_id)
    except SessionBusyError:
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_BUSY", "message": "该会话正在处理中，请稍候或先停止当前回复"},
        )

    try:
        # Regenerate = branch: keep old assistant; new sibling under same user; update leaf
        leaf_path = build_path_from_session(session)
        if not leaf_path:
            raise HTTPException(status_code=400, detail="No messages to regenerate")

        user_message = last_user_on_path(leaf_path)
        if user_message is None:
            # Compat: last user by sequence
            by_seq = sorted(session.messages, key=lambda m: m.sequence)
            for m in reversed(by_seq):
                if m.role == Role.USER:
                    user_message = m
                    break
        if user_message is None:
            raise HTTPException(status_code=400, detail="No user turn to regenerate")

        history_path = path_ending_at(leaf_path, user_message.id)
        if not history_path or history_path[-1].id != user_message.id:
            history_path = path_ending_at(build_path_from_session(session, user_message.id), user_message.id)
        history = history_path[:-1]

        model = payload.model
        metas = parse_attachments_json(getattr(user_message, "attachments", None))
        # Prefer live metas from disk so image bytes can be re-injected.
        if metas:
            live = list_metas_for_ids(session, [str(m["id"]) for m in metas])
            if len(live) == len(metas):
                metas = live

        agent_cfg = load_agent_settings()
        bound_model, model_fallback, _turn_profile = _bind_turn_model(session, model, db)
        if not provider.profile_is_ready(_turn_profile):
            raise HTTPException(status_code=503, detail="LLM provider not configured")

        async def _summarize_for_turn(blob: str) -> str:
            return await _summarize_blob(blob, _turn_profile)

        try:
            model_name = resolve_model_for_attachments(
                bound_model,
                metas,
                vision_model=agent_cfg.get("vision_model"),
            )
        except AttachmentError as e:
            if e.code == "VISION_MODEL_REQUIRED":
                raise HTTPException(
                    status_code=400,
                    detail={"code": e.code, "message": str(e)},
                ) from e
            raise

        system_prompt = _system_prompt(session_id)
        memory_injected = bool(
            get_frozen_user_md(session_id).strip() or get_frozen_memory_md(session_id).strip()
        )
        loop_cfg = LoopConfig.from_settings(
            goal_mode=bool(getattr(session, "goal_mode", False)),
            preset=agent_cfg.get("loop_preset", "yolo"),
        )
        chat_messages = build_llm_messages(
            history,
            convert_to_llm=loop_cfg.convert_to_llm,
            system_prompt=system_prompt,
        )
        # Strip appendix from stored content when rebuilding multimodal from metas.
        user_text = (user_message.content or "")
        marker = "\n\n[附件]"
        if marker in user_text:
            user_text = user_text.split(marker, 1)[0]
        elif user_text.startswith("（见附件）"):
            user_text = ""
        chat_messages.append(build_user_chat_message(session, user_text, metas))

        turn_goal, prev_goal_for_stream, _goal_changed = _resolve_turn_goal_for_session(
            session,
            user_text=user_message.content or "",
            history_messages=list(history),
            audit_source="regenerate",
            session_id=session_id,
        )

        chat_messages, compressed, compress_meta = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_for_turn,
            preserve_goal=turn_goal,
        )
        if compressed:
            _audit(
                "context.compress",
                {
                    "session_id": session_id,
                    "goal_preserved": bool(turn_goal),
                    "method": compress_meta.method,
                    "older_count": compress_meta.older_count,
                    "used_previous_summary": compress_meta.used_previous_summary,
                    "preview": compress_meta.summary_preview,
                },
                session_id=session_id,
            )

        prompt_tokens = approx_messages_tokens(chat_messages)
        all_msgs = sorted(session.messages, key=lambda m: m.sequence)
        assistant_sequence = (all_msgs[-1].sequence + 1) if all_msgs else (user_message.sequence + 1)
        assistant_message = add_message(
            db,
            session,
            Role.ASSISTANT,
            "",
            assistant_sequence,
            summary="",
            trace="[]",
            parent_id=user_message.id,
        )
        started = time.time()

        async def event_stream():
            async def produce():
                from agent_window.services.provider import turn_profile_id

                turn_profile_id.set(_turn_profile or None)
                session_local = get_sessionmaker()()
                try:
                    async for line in _agent_turn_event_stream(
                        session_id=session_id,
                        session_local=session_local,
                        session_db=get_session(session_local, session_id),
                        user_message_id=user_message.id,
                        assistant_message_id=assistant_message.id,
                        chat_messages=chat_messages,
                        turn_goal=turn_goal,
                        previous_goal=prev_goal_for_stream,
                        model=model_name,
                        model_name=model_name,
                        cancel_event=cancel_event,
                        compressed=compressed,
                        memory_injected=memory_injected,
                        prompt_tokens=prompt_tokens,
                        started=started,
                        http_request=http_request,
                        agent_cfg=agent_cfg,
                        compress_method=compress_meta.method if compressed else None,
                        compress_preview=compress_meta.summary_preview if compressed else None,
                        model_fallback=model_fallback,
                        fallback_profile_id=_turn_profile or None,
                    ):
                        yield line
                finally:
                    end_turn(session_id)
                    session_local.close()

            async for line in _sse_detach_producer(produce):
                yield line

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_sse_headers())
    except HTTPException:
        end_turn(session_id)
        raise
    except Exception:
        end_turn(session_id)
        raise

