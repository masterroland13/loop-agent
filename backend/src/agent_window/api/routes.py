"""API route handlers."""

import asyncio
import json
import time
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
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
    ToolInfo,
    ToolsResponse,
    WorkspaceBrowseResponse,
    WorkspaceSetRequest,
    WorkspaceStatusResponse,
)
from agent_window.agent.loop import run_agent_loop
from agent_window.agent.goal import (
    extract_turn_goal,
    goals_equal,
    previous_turn_goal_from_messages,
    prior_user_texts_from_history,
)
from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
from agent_window.services.attachment_context import use_attachment_session
from agent_window.services.attachments import (
    AttachmentError,
    build_content_for_model,
    list_metas_for_ids,
    load_meta,
    resolve_file,
    save_upload,
)
from agent_window.services.llm_config import public_llm_config, save_llm_config
from agent_window.services.audit import (
    audit_to_public,
    emit_audit,
    list_audit_events,
    list_audit_session_summaries,
)
from agent_window.services.compress import approx_messages_tokens, approx_tokens, compress_messages_if_needed
from agent_window.services.memory import (
    decide_memory,
    list_pending_memories,
    memory_status,
    memory_to_public,
    read_user_md,
    user_md_path,
    write_user_md,
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
    delete_message,
    delete_session,
    get_message,
    get_session,
    list_favorites,
    list_sessions,
    read_session_blob,
    toggle_message_favorite,
    update_session_title,
)
from agent_window.services.turn_trace import TurnTraceWriter, trace_for_response
from agent_window.services.workspace import (
    WorkspaceError,
    browse_directory,
    clear_workspace_root,
    get_workspace_root,
    set_workspace_root,
    workspace_status,
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
    )


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
    yield (
        "event: meta\ndata: "
        f"{json.dumps({'message_id': user_message_id, 'goal': turn_goal, 'assistant_message_id': writer.assistant_id}, ensure_ascii=False)}\n\n"
    )

    assistant_content_parts: List[str] = []

    async def _agent_events():
        with use_attachment_session(session_id):
            async for event in run_agent_loop(
                chat_messages,
                model=model,
                cancel_event=cancel_event,
                goal=turn_goal,
                previous_goal=previous_goal,
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
        ):
            mapped = writer.note_sse(event)

        if etype == "token":
            assistant_content_parts.append(event["content"])
            yield f"event: token\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype == "turn_goal":
            yield f"event: turn_goal\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif etype == "progress_checkpoint":
            yield f"event: progress_checkpoint\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
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
                "goal": turn_goal,
                "message_id": writer.assistant_id,
            }
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


def _system_prompt() -> str:
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
            "To remember durable user preferences/facts, call propose_memory. "
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
            "You may still call propose_memory for durable preferences."
        )

    user_md = read_user_md().strip()
    memory_block = ""
    if user_md:
        memory_block = (
            "\n\n## USER.md (long-term memory; read-only here)\n"
            + user_md[:6000]
            + ("\n…" if len(user_md) > 6000 else "")
        )

    skill_blocks = skill_context_blocks()
    skills_section = ""
    if skill_blocks:
        skills_section = "\n\n" + "\n\n".join(skill_blocks)

    if system_override:
        base = system_override
    else:
        base = (
            "You are a helpful coding assistant. Answer concisely in Chinese unless the user asks otherwise. "
            "When providing code, use Markdown code blocks with the language identifier. "
            "中文回复必须使用规范的全角标点（，。：；！？），不要在中文句子里夹半角逗号、冒号或句号；"
            "代码、命令、路径、英文术语保持半角原样。 "
            f"You have tools available: {tool_names}. "
            f"{workspace_hint} "
            "If the user message includes an [附件] block with attachment ids, call read_attachment(attachment_id=...) to read those files (not workspace read_file). "
            "When the user message is only attachments (or starts with 「（见附件）」) without an explicit instruction "
            "(extract/save/write/create/convert/summarize-to-file/etc.), default to read-only: "
            "call read_attachment if the file is text-readable, then give a short verbal summary in the reply; "
            "do NOT call propose_edit, propose_delete, or propose_shell to extract/persist attachment contents "
            "into the workspace, and do not invent helper scripts — unless the user explicitly asks to write files. "
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


async def _summarize_blob(blob: str) -> str:
    turn = await provider.chat_complete(
        [
            {
                "role": "system",
                "content": "用中文极简摘要下列对话历史，保留约束与关键事实，不超过400字。",
            },
            {"role": "user", "content": blob},
        ],
        tools=None,
        model=None,
        max_tokens=512,
    )
    return (turn.get("content") or "").strip()


@router.get("/api/runtime", response_model=RuntimeResponse)
def runtime_endpoint():
    return RuntimeResponse(**runtime_info())


@router.post("/api/sessions/{session_id}/cancel")
def cancel_session_endpoint(session_id: str):
    cancelled = cancel_turn(session_id)
    return {"ok": True, "cancelled": cancelled}


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
def put_settings_endpoint(request: AgentSettingsUpdateRequest, db: Session = Depends(get_db)):
    updated = save_agent_settings(request.model_dump(exclude_unset=True))
    emit_audit(db, "settings.update", payload=updated)
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
def get_memory_content_endpoint():
    return MemoryContentResponse(content=read_user_md(), path=str(user_md_path()))


@router.put("/api/memory/content", response_model=MemoryContentResponse)
def put_memory_content_endpoint(request: MemoryContentUpdateRequest, db: Session = Depends(get_db)):
    write_user_md(request.content)
    emit_audit(db, "memory.direct_edit", payload={"size": len(request.content)})
    return MemoryContentResponse(content=read_user_md(), path=str(user_md_path()))


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
def get_memory_endpoint():
    mem = memory_status()
    return {
        "exists": mem["exists"],
        "path": mem["path"],
        "size": mem["size"],
        "preview": mem["preview"],
        "content": read_user_md(),
    }


@router.get("/api/memory/proposals", response_model=List[MemoryProposalResponse])
def list_memory_proposals_endpoint():
    return [MemoryProposalResponse(**m) for m in list_pending_memories()]


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


@router.get("/api/workspace/patches", response_model=List[PatchResponse])
def list_patches_endpoint():
    return [PatchResponse(**p) for p in list_pending()]


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
def list_shells_endpoint():
    return [ShellResponse(**s) for s in list_pending_shells()]


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
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        workspace_root=session.workspace_root,
    )


@router.patch("/api/sessions/{session_id}", response_model=SessionResponse)
def update_session_endpoint(session_id: str, request: CreateSessionRequest, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = update_session_title(db, session, request.title)
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        workspace_root=session.workspace_root,
    )


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
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            workspace_root=s.workspace_root,
        )
        for s in sessions
    ]


@router.get("/api/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages_endpoint(session_id: str, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
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

    if not provider.is_available():
        raise HTTPException(status_code=503, detail="LLM provider not configured")

    try:
        cancel_event = try_begin_turn(session_id)
    except SessionBusyError:
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_BUSY", "message": "该会话正在处理中，请稍候或先停止当前回复"},
        )

    try:
        existing_messages = sorted(session.messages, key=lambda m: m.sequence)
        next_sequence = (existing_messages[-1].sequence + 1) if existing_messages else 1

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

        user_message = add_message(
            db,
            session,
            Role.USER,
            content_for_model,
            next_sequence,
            attachments=attachments_json,
        )
        assistant_sequence = next_sequence + 1
        assistant_message = add_message(
            db, session, Role.ASSISTANT, "", assistant_sequence, summary="", trace="[]",
        )

        system_prompt = _system_prompt()
        memory_injected = bool(read_user_md().strip())

        chat_messages: List[dict] = [{"role": "system", "content": system_prompt}]
        for m in existing_messages:
            content = (m.content or "").strip()
            if not content:
                continue
            chat_messages.append({"role": m.role.value, "content": content})
        chat_messages.append({"role": "user", "content": content_for_model})

        prev_goal = previous_turn_goal_from_messages(existing_messages)
        turn_goal = extract_turn_goal(
            content_for_model,
            prior_user_texts_from_history(existing_messages),
        )
        goal_changed = bool(prev_goal) and not goals_equal(prev_goal, turn_goal)
        if goal_changed:
            _audit(
                "goal.change",
                {
                    "previous_goal": prev_goal,
                    "goal": turn_goal,
                    "source": "extract",
                },
                session_id=session_id,
            )

        agent_cfg = load_agent_settings()
        chat_messages, compressed = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_blob if provider.is_available() else None,
            preserve_goal=turn_goal,
        )
        if compressed:
            _audit(
                "context.compress",
                {"session_id": session_id, "goal_preserved": bool(turn_goal)},
                session_id=session_id,
            )

        model_name = request.model or settings.llm_model
        prompt_tokens = approx_messages_tokens(chat_messages)
        started = time.time()

        async def event_stream():
            async def produce():
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
                        previous_goal=prev_goal if goal_changed else None,
                        model=request.model,
                        model_name=model_name,
                        cancel_event=cancel_event,
                        compressed=compressed,
                        memory_injected=memory_injected,
                        prompt_tokens=prompt_tokens,
                        started=started,
                        http_request=http_request,
                        agent_cfg=agent_cfg,
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
    if not provider.is_available():
        raise HTTPException(status_code=503, detail="LLM provider not configured")

    try:
        cancel_event = try_begin_turn(session_id)
    except SessionBusyError:
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_BUSY", "message": "该会话正在处理中，请稍候或先停止当前回复"},
        )

    try:
        existing_messages = sorted(session.messages, key=lambda m: m.sequence)
        if not existing_messages:
            raise HTTPException(status_code=400, detail="No messages to regenerate")

        # Drop trailing assistant if present (failed/partial prior attempt)
        if existing_messages[-1].role == Role.ASSISTANT:
            delete_message(db, existing_messages[-1])
            existing_messages = existing_messages[:-1]

        if not existing_messages or existing_messages[-1].role != Role.USER:
            raise HTTPException(status_code=400, detail="Last message must be a user turn")

        user_message = existing_messages[-1]
        history = existing_messages[:-1]
        model = payload.model

        system_prompt = _system_prompt()
        memory_injected = bool(read_user_md().strip())
        chat_messages: List[dict] = [{"role": "system", "content": system_prompt}]
        for m in history:
            content = (m.content or "").strip()
            if not content:
                continue
            chat_messages.append({"role": m.role.value, "content": content})
        chat_messages.append({"role": "user", "content": user_message.content})

        prev_goal = previous_turn_goal_from_messages(history)
        turn_goal = extract_turn_goal(
            user_message.content or "",
            prior_user_texts_from_history(history),
        )
        goal_changed = bool(prev_goal) and not goals_equal(prev_goal, turn_goal)
        if goal_changed:
            _audit(
                "goal.change",
                {
                    "previous_goal": prev_goal,
                    "goal": turn_goal,
                    "source": "regenerate",
                },
                session_id=session_id,
            )

        agent_cfg = load_agent_settings()
        chat_messages, compressed = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_blob if provider.is_available() else None,
            preserve_goal=turn_goal,
        )
        if compressed:
            _audit(
                "context.compress",
                {"session_id": session_id, "goal_preserved": bool(turn_goal)},
                session_id=session_id,
            )

        model_name = model or settings.llm_model
        prompt_tokens = approx_messages_tokens(chat_messages)
        assistant_sequence = user_message.sequence + 1
        assistant_message = add_message(
            db, session, Role.ASSISTANT, "", assistant_sequence, summary="", trace="[]",
        )
        started = time.time()

        async def event_stream():
            async def produce():
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
                        previous_goal=prev_goal if goal_changed else None,
                        model=model,
                        model_name=model_name,
                        cancel_event=cancel_event,
                        compressed=compressed,
                        memory_injected=memory_injected,
                        prompt_tokens=prompt_tokens,
                        started=started,
                        http_request=http_request,
                        agent_cfg=agent_cfg,
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

