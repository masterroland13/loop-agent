import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def default_user_data_dir() -> str:
    """Data dir when APP_DATA_DIR is unset. Not the process cwd."""
    return str(Path.home() / ".local" / "share" / "loop-agent")


class Settings(BaseSettings):
    app_data_dir: str = Field(default_factory=default_user_data_dir)
    default_user_id: str = "local-user"

    llm_provider: str = "litellm"
    llm_base_url: str = "https://llm-cn.gameye.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "kimi-k3"
    # Used when the turn has image attachments and the selected model is not vision-capable.
    llm_vision_model: str = "deepseek-v4-flash-vision-exp"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7

    approval_timeout_sec: int = 300

    @field_validator("app_data_dir", mode="before")
    @classmethod
    def _blank_app_data_dir(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default_user_data_dir()
        return value

    class Config:
        # Desktop shell sets LOOP_SHELL so the window does not inherit backend/.env.
        env_file = None if os.environ.get("LOOP_SHELL") == "1" else ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
