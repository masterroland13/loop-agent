from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class CreateSessionRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=255)
    workspace_root: str | None = Field(default=None, max_length=1024)


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    workspace_root: str | None = None

    class Config:
        from_attributes = True


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    size: int
    content_type: str | None = None
    url: str


class MessageRequest(BaseModel):
    content: str = Field(default="", max_length=100000)
    model: str | None = Field(default=None, max_length=128)
    attachment_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_content_or_attachments(self):
        text = (self.content or "").strip()
        ids = [a for a in (self.attachment_ids or []) if a]
        if not text and not ids:
            raise ValueError("content or attachment_ids required")
        self.attachment_ids = ids
        return self


class RegenerateRequest(BaseModel):
    model: str | None = Field(default=None, max_length=128)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sequence: int
    is_favorite: bool
    summary: str | None = None
    trace: list[dict] = Field(default_factory=list)
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    provider: str
    provider_available: bool


class RuntimeResponse(BaseModel):
    boot_id: str
    started_at: float
    active_sessions: List[str]


class ModelInfo(BaseModel):
    id: str


class ModelsResponse(BaseModel):
    models: List[ModelInfo]
    default: str
    source: str  # "provider" | "fallback"


class FavoriteToggleRequest(BaseModel):
    is_favorite: bool


class FavoriteItemResponse(BaseModel):
    id: str
    session_id: str
    session_title: str
    user_content: str
    assistant_content: str
    created_at: datetime


class WorkspaceStatusResponse(BaseModel):
    configured: bool
    root: str | None = None
    name: str | None = None


class WorkspaceSetRequest(BaseModel):
    root: str = Field(..., min_length=1, max_length=4096)


class WorkspaceBrowseResponse(BaseModel):
    path: str
    parent: str | None = None
    directories: list[dict]


class PatchResponse(BaseModel):
    id: str
    path: str
    unified_diff: str
    is_new_file: bool
    status: str
    error: str | None = None
    hunk_count: int | None = None
    applied_hunks: list[int] | None = None


class ApplyPartialRequest(BaseModel):
    hunk_ids: list[int] = Field(..., min_length=1)


class ShellResponse(BaseModel):
    id: str
    argv: list[str]
    cwd: str
    command: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    error: str | None = None


class AgentSettingsResponse(BaseModel):
    auto_compress: bool
    confirm_memory: bool
    context_limit: int
    active_skills: List[str] = []
    approval_timeout_sec: int = 300
    disabled_tools: List[str] = []
    max_tool_iters: int = 24
    checkpoint_every_n_tools: int = 4


class AgentSettingsUpdateRequest(BaseModel):
    auto_compress: bool | None = None
    confirm_memory: bool | None = None
    context_limit: int | None = Field(default=None, ge=2048, le=32768)
    active_skills: List[str] | None = None
    approval_timeout_sec: int | None = Field(default=None, ge=30, le=3600)
    disabled_tools: List[str] | None = None
    max_tool_iters: int | None = Field(default=None, ge=8, le=64)
    checkpoint_every_n_tools: int | None = Field(default=None, ge=0, le=16)


class LlmConfigResponse(BaseModel):
    api_key_configured: bool
    base_url: str
    default_model: str
    temperature: float
    max_tokens: int


class LlmConfigUpdateRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=4096)
    base_url: str | None = Field(default=None, max_length=2048)
    default_model: str | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=256, le=200000)


class LlmTestResponse(BaseModel):
    ok: bool
    latency_ms: int | None = None
    model_count: int | None = None
    error: str | None = None


class ToolInfo(BaseModel):
    name: str
    description: str


class ToolsResponse(BaseModel):
    tools: List[ToolInfo]
    disabled_tools: List[str]


class MemoryContentResponse(BaseModel):
    content: str
    path: str


class MemoryContentUpdateRequest(BaseModel):
    content: str = Field(default="", max_length=100000)


class SkillInfo(BaseModel):
    id: str
    name: str
    path: str
    preview: str
    description: str = ""


class SkillsResponse(BaseModel):
    workspace_configured: bool
    workspace_root: str | None = None
    skills: List[SkillInfo]
    active_skills: List[str]
    agents_md_exists: bool


class SkillActivateRequest(BaseModel):
    active_skills: List[str]


class MemoryProposalResponse(BaseModel):
    id: str
    mode: str
    preview: str
    content: str
    status: str
    error: str | None = None


class AuditEventResponse(BaseModel):
    id: str
    session_id: str | None = None
    event_type: str
    payload: dict
    created_at: datetime


class AuditEmitRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    payload: dict | None = None
    session_id: str | None = None


class AuditSessionSummary(BaseModel):
    session_id: str
    event_count: int
    last_at: datetime | None = None


class AssetsResponse(BaseModel):
    status: str
    provider: str
    provider_available: bool
    session_count: int
    user_md_exists: bool
    user_md_path: str
    user_md_size: int
    workspace_configured: bool
    workspace_root: str | None = None
    settings: AgentSettingsResponse
