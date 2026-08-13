from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_data_dir: str = "./data"
    default_user_id: str = "local-user"

    llm_provider: str = "litellm"
    llm_base_url: str = "https://llm-cn.gameye.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "kimi-k3"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
