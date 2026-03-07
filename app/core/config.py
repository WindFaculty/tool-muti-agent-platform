from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "agent-tooling-platform"
    app_version: str = "1.0.0"
    environment: str = "dev"

    workspace_root: Path = Path("d:/Spring_2026/PRJ301")
    tool_config_path: Path = Path("config/tools.yaml")
    policy_config_path: Path = Path("config/policies.yaml")
    database_path: Path = Path("data/tooling.db")
    audit_log_path: Path = Path("logs/tool_usage.jsonl")

    service_tokens_csv: str = Field(default="dev-token")

    requests_per_minute: int = 60
    max_concurrent_per_agent: int = 4
    default_timeout_sec: int = 30
    max_output_bytes: int = 200_000
    default_memory_limit_mb: int = 512

    serpapi_api_key: Optional[str] = None

    model_config = SettingsConfigDict(
        env_prefix="AGENT_PLATFORM_",
        case_sensitive=False,
    )

    @property
    def service_tokens(self) -> set[str]:
        return {
            token.strip()
            for token in self.service_tokens_csv.split(",")
            if token.strip()
        }

    def resolve_path(self, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (BASE_DIR / value).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

