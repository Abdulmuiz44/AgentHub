from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTHUB_", env_file=".env", extra="ignore")

    app_name: str = "AgentHub API"
    environment: str = "development"
    database_url: str = Field(default="sqlite:///./agenthub.db")
    workspace_root: str = Field(default=".")

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_default_model: str = "gpt-4o-mini"

    ollama_base_url: str | None = None
    ollama_default_model: str = "llama3.1"


settings = Settings()
