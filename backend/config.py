"""Runtime settings loaded from environment variables."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

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
    # Which AgentRunner implementation main.py should wire up (Task 16).
    # Default "raw" so the unit-tested hand-rolled loop is used in tests and
    # any environment that hasn't explicitly opted into the Agent SDK runner.
    # Production deployments override via AGENT_RUNNER=agent_sdk.
    agent_runner: Literal["agent_sdk", "raw"] = "raw"

    def model_post_init(self, __context) -> None:
        # normalize db_path to absolute
        if not self.db_path.is_absolute():
            object.__setattr__(self, "db_path", self.db_path.resolve())
        if not self.project_root.is_absolute():
            object.__setattr__(self, "project_root", self.project_root.resolve())


def get_settings() -> Settings:
    return Settings()
