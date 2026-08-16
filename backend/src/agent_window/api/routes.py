"""API route handlers."""

import asyncio
import json
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agent_window.config import settings
from agent_window.models import Role, get_db, get_sessionmaker
from agent_window.schemas import (
    AgentSettingsResponse,
    AgentSettingsUpdateRequest,
    AssetsResponse,
    AuditEmitRequest,
    AuditEventResponse,
    ApplyPartialRequest,
    CreateSessionRequest,
    FavoriteItemResponse,
    FavoriteToggleRequest,
    HealthResponse,
    LlmConfigResponse,
    LlmConfigUpdateRequest,
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
    WorkspaceBrowseResponse,
    WorkspaceSetRequest,
    WorkspaceStatusResponse,
)
from agent_window.agent.loop import run_agent_loop
from agent_window.services.agent_settings import load_agent_settings, save_agent_settings
from agent_window.services.llm_config import public_llm_config, save_llm_config
from agent_window.services.audit import audit_to_public, emit_audit, list_audit_events
from agent_window.services.compress import approx_messages_tokens, approx_tokens, compress_messages_if_needed
from agent_window.services.memory import (
    decide_memory,
    list_pending_memories,
    memory_status,
    memory_to_public,
    read_user_md,
)
from agent_window.services.patches import apply_partial_patch, decide_patch, list_pending, patch_to_public, retry_patch
from agent_window.services.provider import provider
from agent_window.services.session_turns import (
    SessionBusyError,
    cancel_turn,
    end_turn,
    runtime_info,
    try_begin_turn,
    watch_disconnect,
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
    toggle_message_favorite,
    update_session_title,
)
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


def _system_prompt() -> str:
    import agent_window.tools  # noqa: F401

    tool_names = ", ".join(registry.list_names()) or "(none)"
    ws_root = get_workspace_root()
    if ws_root:
        workspace_hint = (
            f"Workspace root is bound to: {ws_root}. "
            "Use list_dir, read_file, and grep for local files. "
            "To change files, call propose_edit and wait for user Apply; "
            "never claim a file was written/created/modified unless a propose_edit "
            "tool result shows status=applied. "
            "To run tests or commands, call propose_shell with argv as a string array "
            '(e.g. ["pytest","-q"] or ["git","status"]); it waits for user approval. '
            "To remember durable user preferences/facts, call propose_memory. "
            "No shell piping/redirection. Prefer old_string+new_string after read_file. "
            "Paths and cwd are relative to the workspace root. "
            "If a propose_edit/propose_shell/propose_memory is rejected and the user asks "
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

    return (
        "You are a helpful coding assistant. Answer concisely in Chinese unless the user asks otherwise. "
        "When providing code, use Markdown code blocks with the language identifier. "
        f"You have tools available: {tool_names}. "
        f"{workspace_hint} "
        "When the user asks about weather, call get_weather. "
        "Do not invent tool results — always call the tool. "
        "When the user asks you to create, edit, or run something in the workspace, "
        "you MUST call the matching tool (propose_edit, propose_shell) instead of describing the action."
        f"{memory_block}"
        f"{skills_section}"
    )


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
def list_audit_endpoint(limit: int = 50, session_id: str | None = None, db: Session = Depends(get_db)):
    events = list_audit_events(db, limit=limit, session_id=session_id)
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
    session = create_session(db, title=request.title)
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
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
    return MessageResponse(
        id=message.id,
        role=message.role.value,
        content=message.content,
        sequence=message.sequence,
        is_favorite=message.is_favorite,
        summary=message.summary or None,
        created_at=message.created_at,
    )


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
        )
        for s in sessions
    ]


@router.get("/api/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages_endpoint(session_id: str, db: Session = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    existing_messages = sorted(session.messages, key=lambda m: m.sequence)
    return [
        MessageResponse(
            id=m.id,
            role=m.role.value,
            content=m.content,
            sequence=m.sequence,
            is_favorite=m.is_favorite,
            summary=m.summary or None,
            created_at=m.created_at,
        )
        for m in existing_messages
    ]


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

        user_message = add_message(db, session, Role.USER, request.content, next_sequence)

        system_prompt = _system_prompt()
        memory_injected = bool(read_user_md().strip())

        chat_messages: List[dict] = [{"role": "system", "content": system_prompt}]
        for m in existing_messages:
            content = (m.content or "").strip()
            if not content:
                continue
            chat_messages.append({"role": m.role.value, "content": content})
        chat_messages.append({"role": "user", "content": request.content})

        agent_cfg = load_agent_settings()
        chat_messages, compressed = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_blob if provider.is_available() else None,
        )
        if compressed:
            _audit("context.compress", {"session_id": session_id}, session_id=session_id)

        model_name = request.model or settings.llm_model
        prompt_tokens = approx_messages_tokens(chat_messages)
        assistant_content_parts: List[str] = []
        assistant_sequence = next_sequence + 1
        started = time.time()

        async def event_stream():
            watcher = asyncio.create_task(watch_disconnect(http_request, cancel_event))
            session_local = get_sessionmaker()()
            try:
                session_db = get_session(session_local, session_id)
                if not session_db:
                    yield f"event: error\ndata: {json.dumps({'code': 'SESSION_NOT_FOUND', 'message': 'Session not found'}, ensure_ascii=False)}\n\n"
                    return

                yield f"event: meta\ndata: {json.dumps({'message_id': user_message.id}, ensure_ascii=False)}\n\n"

                async for event in run_agent_loop(
                    chat_messages, model=request.model, cancel_event=cancel_event
                ):
                    etype = event.get("type")
                    if etype == "token":
                        assistant_content_parts.append(event["content"])
                        yield f"event: token\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
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
                        yield f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    elif etype == "error":
                        yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                        return
                    elif etype == "done":
                        full_content = "".join(assistant_content_parts).strip()
                        if not full_content:
                            yield (
                                "event: error\ndata: "
                                f"{json.dumps({'code': 'EMPTY_RESPONSE', 'message': '模型返回为空，请重试'}, ensure_ascii=False)}\n\n"
                            )
                            return
                        assistant_message = add_message(
                            session_local, session_db, Role.ASSISTANT, full_content, assistant_sequence,
                            summary=json.dumps({
                                "type": "turn_meta",
                                "model": model_name,
                                "elapsed_ms": int((time.time() - started) * 1000),
                                "approx_prompt_tokens": prompt_tokens,
                                "approx_completion_tokens": approx_tokens(full_content),
                                "compressed": compressed,
                                "memory_injected": memory_injected,
                                "message_id": "PENDING",
                            }, ensure_ascii=False),
                        )
                        turn_meta = {
                            "type": "turn_meta",
                            "model": model_name,
                            "elapsed_ms": int((time.time() - started) * 1000),
                            "approx_prompt_tokens": prompt_tokens,
                            "approx_completion_tokens": approx_tokens(full_content),
                            "compressed": compressed,
                            "memory_injected": memory_injected,
                            "message_id": assistant_message.id,
                        }
                        assistant_message.summary = json.dumps(turn_meta, ensure_ascii=False)
                        session_local.add(assistant_message)
                        session_local.commit()
                        yield f"event: turn_meta\ndata: {json.dumps(turn_meta, ensure_ascii=False)}\n\n"
                        yield f"event: done\ndata: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'code': 'INTERNAL_ERROR', 'message': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                cancel_event.set()
                watcher.cancel()
                try:
                    await watcher
                except Exception:
                    pass
                end_turn(session_id)
                session_local.close()

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

        agent_cfg = load_agent_settings()
        chat_messages, compressed = await compress_messages_if_needed(
            chat_messages,
            auto_compress=agent_cfg["auto_compress"],
            context_limit=agent_cfg["context_limit"],
            summarize=_summarize_blob if provider.is_available() else None,
        )
        if compressed:
            _audit("context.compress", {"session_id": session_id}, session_id=session_id)

        model_name = model or settings.llm_model
        prompt_tokens = approx_messages_tokens(chat_messages)
        assistant_content_parts: List[str] = []
        assistant_sequence = user_message.sequence + 1
        started = time.time()

        async def event_stream():
            watcher = asyncio.create_task(watch_disconnect(http_request, cancel_event))
            session_local = get_sessionmaker()()
            try:
                session_db = get_session(session_local, session_id)
                if not session_db:
                    yield f"event: error\ndata: {json.dumps({'code': 'SESSION_NOT_FOUND', 'message': 'Session not found'}, ensure_ascii=False)}\n\n"
                    return

                yield f"event: meta\ndata: {json.dumps({'message_id': user_message.id}, ensure_ascii=False)}\n\n"

                async for event in run_agent_loop(chat_messages, model=model, cancel_event=cancel_event):
                    etype = event.get("type")
                    if etype == "token":
                        assistant_content_parts.append(event["content"])
                        yield f"event: token\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
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
                        yield f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    elif etype == "error":
                        yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                        return
                    elif etype == "done":
                        full_content = "".join(assistant_content_parts).strip()
                        if not full_content:
                            yield (
                                "event: error\ndata: "
                                f"{json.dumps({'code': 'EMPTY_RESPONSE', 'message': '模型返回为空，请重试'}, ensure_ascii=False)}\n\n"
                            )
                            return
                        assistant_message = add_message(
                            session_local, session_db, Role.ASSISTANT, full_content, assistant_sequence,
                            summary=json.dumps({
                                "type": "turn_meta",
                                "model": model_name,
                                "elapsed_ms": int((time.time() - started) * 1000),
                                "approx_prompt_tokens": prompt_tokens,
                                "approx_completion_tokens": approx_tokens(full_content),
                                "compressed": compressed,
                                "memory_injected": memory_injected,
                                "message_id": "PENDING",
                            }, ensure_ascii=False),
                        )
                        turn_meta = {
                            "type": "turn_meta",
                            "model": model_name,
                            "elapsed_ms": int((time.time() - started) * 1000),
                            "approx_prompt_tokens": prompt_tokens,
                            "approx_completion_tokens": approx_tokens(full_content),
                            "compressed": compressed,
                            "memory_injected": memory_injected,
                            "message_id": assistant_message.id,
                        }
                        assistant_message.summary = json.dumps(turn_meta, ensure_ascii=False)
                        session_local.add(assistant_message)
                        session_local.commit()
                        yield f"event: turn_meta\ndata: {json.dumps(turn_meta, ensure_ascii=False)}\n\n"
                        yield f"event: done\ndata: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'code': 'INTERNAL_ERROR', 'message': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                cancel_event.set()
                watcher.cancel()
                try:
                    await watcher
                except Exception:
                    pass
                end_turn(session_id)
                session_local.close()

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_sse_headers())
    except HTTPException:
        end_turn(session_id)
        raise
    except Exception:
        end_turn(session_id)
        raise
