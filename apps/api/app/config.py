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
    cors_allowed_origins_csv: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins_csv.split(",") if origin.strip()]


settings = Settings()
