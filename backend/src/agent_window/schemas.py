from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=255)


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)
    model: str | None = Field(default=None, max_length=128)


class RegenerateRequest(BaseModel):
    model: str | None = Field(default=None, max_length=128)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sequence: int
    is_favorite: bool
    summary: str | None = None
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


class AgentSettingsUpdateRequest(BaseModel):
    auto_compress: bool | None = None
    confirm_memory: bool | None = None
    context_limit: int | None = Field(default=None, ge=2048, le=32768)
    active_skills: List[str] | None = None


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
