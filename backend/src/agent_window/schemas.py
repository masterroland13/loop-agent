from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class CreateSessionRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=255)
    workspace_root: str | None = Field(default=None, max_length=1024)


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    goal_mode: bool | None = None
    pinned_goal: str | None = Field(default=None, max_length=240)
    workspace_root: str | None = Field(default=None, max_length=1024)
    profile_id: str | None = Field(default=None, max_length=64)
    model_id: str | None = Field(default=None, max_length=128)
    title_locked: bool | None = None

    @model_validator(mode="after")
    def require_title_or_goal_mode(self):
        if (
            self.title is None
            and self.goal_mode is None
            and self.title_locked is None
            and "pinned_goal" not in self.model_fields_set
            and "workspace_root" not in self.model_fields_set
            and "profile_id" not in self.model_fields_set
            and "model_id" not in self.model_fields_set
        ):
            raise ValueError("title, goal_mode, pinned_goal, workspace_root, profile_id, or model_id required")
        if self.title is not None and not self.title.strip():
            raise ValueError("title must not be empty")
        return self


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    workspace_root: str | None = None
    goal_mode: bool = False
    pinned_goal: str | None = None
    leaf_id: str | None = None
    profile_id: str | None = None
    model_id: str | None = None
    title_locked: bool = False
    last_prompt_at: datetime | None = None

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


class CompactRequest(BaseModel):
    focus: str | None = Field(default=None, max_length=240)


class ContextUsageResponse(BaseModel):
    tokens: int
    context_limit: int
    percent: int
    message_count: int


class CompactResponse(BaseModel):
    compressed: bool
    method: str
    tokens_before: int
    tokens_after: int
    percent_before: int
    percent_after: int
    context_limit: int
    older_count: int = 0
    focus: str | None = None


class SteerRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)


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
    parent_id: str | None = None
    entry_type: str = "message"

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


class WorkspaceMkdirRequest(BaseModel):
    parent: str = Field(..., min_length=1, max_length=4096)
    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceMkdirResponse(BaseModel):
    path: str


class WorkspaceBrowseResponse(BaseModel):
    path: str
    parent: str | None = None
    directories: list[dict]


class WorkspaceFileEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None


class WorkspaceFilesListResponse(BaseModel):
    path: str
    entries: list[WorkspaceFileEntry]
    truncated: bool = False


class WorkspaceFileReadResponse(BaseModel):
    path: str
    content: str
    mtime_ns: str
    size: int
    encoding: str = "utf-8"


class WorkspaceFileWriteRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    content: str
    if_match_mtime_ns: int | str | None = None
    if_match_base_content: str | None = None
    encoding: str = "utf-8"


class WorkspaceFileWriteResponse(BaseModel):
    path: str
    mtime_ns: str
    size: int


class WorkspaceFilePathRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)


class WorkspaceFilePathResponse(BaseModel):
    path: str


class WorkspaceFileRenameRequest(BaseModel):
    from_path: str = Field(..., alias="from", min_length=1, max_length=4096)
    to_path: str = Field(..., alias="to", min_length=1, max_length=4096)

    model_config = {"populate_by_name": True}


class WorkspaceFileRenameResponse(BaseModel):
    from_path: str = Field(..., serialization_alias="from")
    path: str

    model_config = {"populate_by_name": True}


class WorkspaceFileCopyRequest(BaseModel):
    from_path: str = Field(..., alias="from", min_length=1, max_length=4096)
    to_path: str = Field(..., alias="to", min_length=1, max_length=4096)

    model_config = {"populate_by_name": True}


class WorkspaceFileCopyResponse(BaseModel):
    from_path: str = Field(..., serialization_alias="from")
    path: str

    model_config = {"populate_by_name": True}


class WorkspaceFileTreeStatsResponse(BaseModel):
    path: str
    file_count: int
    dir_count: int


class WorkspaceFileDeleteResponse(BaseModel):
    path: str
    recursive: bool = False


class WorkspaceFileRevealResponse(BaseModel):
    path: str
    revealed: str


class PatchResponse(BaseModel):
    id: str
    path: str
    unified_diff: str
    is_new_file: bool
    status: str
    error: str | None = None
    hunk_count: int | None = None
    applied_hunks: list[int] | None = None
    session_id: str | None = None


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
    session_id: str | None = None


class AgentSettingsResponse(BaseModel):
    auto_compress: bool
    confirm_memory: bool
    context_limit: int
    active_skills: List[str] = []
    approval_timeout_sec: int = 300
    disabled_tools: List[str] = []
    max_tool_iters: int = 24
    checkpoint_every_n_tools: int = 4
    exploration_repeat_threshold: int = 6
    vision_model: str = ""
    loop_preset: str = "yolo"
    user_md_char_limit: int = 1375
    memory_md_char_limit: int = 2200


class AgentSettingsUpdateRequest(BaseModel):
    auto_compress: bool | None = None
    confirm_memory: bool | None = None
    context_limit: int | None = Field(default=None, ge=2048, le=32768)
    active_skills: List[str] | None = None
    approval_timeout_sec: int | None = Field(default=None, ge=30, le=3600)
    disabled_tools: List[str] | None = None
    max_tool_iters: int | None = Field(default=None, ge=8, le=64)
    checkpoint_every_n_tools: int | None = Field(default=None, ge=0, le=16)
    exploration_repeat_threshold: int | None = Field(default=None, ge=0, le=12)
    vision_model: str | None = Field(default=None, max_length=128)
    loop_preset: str | None = None
    user_md_char_limit: int | None = Field(default=None, ge=500, le=8000)
    memory_md_char_limit: int | None = Field(default=None, ge=500, le=8000)


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


class ProviderPresetResponse(BaseModel):
    id: str
    label: str
    base_url: str
    model_id: str
    inherit_base_url: bool


class LlmTestResponse(BaseModel):
    ok: bool
    latency_ms: int | None = None
    model_count: int | None = None
    error: str | None = None


class ModelProfileResponse(BaseModel):
    id: str
    label: str
    enabled: bool
    base_url: str
    model_id: str
    api: str = "openai-completions"
    api_key_configured: bool
    supports_reasoning: bool = False
    reasoning_mode: str = "none"


class ModelProfilesListResponse(BaseModel):
    active_id: str
    temperature: float
    max_tokens: int
    profiles: List[ModelProfileResponse]


class ModelProfileCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=128)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    model_id: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    activate: bool = False
    supports_reasoning: bool | None = None
    reasoning_mode: str | None = Field(default=None, max_length=64)


class ModelProfileUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=128)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    model_id: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=256, le=200000)
    supports_reasoning: bool | None = None
    reasoning_mode: str | None = Field(default=None, max_length=64)


class ModelGlobalsUpdateRequest(BaseModel):
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=256, le=200000)


class ToolInfo(BaseModel):
    name: str
    description: str


class ToolsResponse(BaseModel):
    tools: List[ToolInfo]
    disabled_tools: List[str]


class MemoryContentResponse(BaseModel):
    content: str
    path: str
    target: str = "user"
    chars: int = 0
    limit: int = 1375


class MemoryContentUpdateRequest(BaseModel):
    content: str = Field(default="", max_length=100000)
    target: str = "user"


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
    target: str = "user"
    status: str
    error: str | None = None
    session_id: str | None = None


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
    memory_md_exists: bool = False
    memory_md_path: str = ""
    memory_md_size: int = 0
    user_md_chars: int = 0
    user_md_limit: int = 1375
    memory_md_chars: int = 0
    memory_md_limit: int = 2200
    workspace_configured: bool
    workspace_root: str | None = None
    settings: AgentSettingsResponse
