from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTHUB_", env_file=".env", extra="ignore")

    app_name: str = "AgentHub API"
    environment: str = "development"
    database_url: str = Field(default="sqlite:///./agenthub.db")
    workspace_root: str = Field(default=".")
    search_provider: str | None = Field(default=None)
    searxng_base_url: str | None = Field(default=None)


settings = Settings()
