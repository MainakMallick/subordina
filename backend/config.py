"""Runtime settings loaded from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str
    default_model: str = "claude-opus-4-7"
    db_path: Path = Path("subordina.db")
    project_root: Path = Path(".")
    max_cost_cents_per_invocation: int = Field(default=5000, ge=0)

    def model_post_init(self, __context) -> None:
        # normalize db_path to absolute
        if not self.db_path.is_absolute():
            object.__setattr__(self, "db_path", self.db_path.resolve())
        if not self.project_root.is_absolute():
            object.__setattr__(self, "project_root", self.project_root.resolve())


def get_settings() -> Settings:
    return Settings()
