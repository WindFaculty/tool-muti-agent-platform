from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "agent-tooling-platform"
    app_version: str = "1.0.0"
    environment: str = "dev"

    workspace_root: Path = Path("d:/Antigaravity_Code/tro_ly")
    tool_config_path: Path = Path("config/tools.yaml")
    policy_config_path: Path = Path("config/policies.yaml")
    model_config_path: Path = Path("config/models.yaml")
    agent_config_path: Path = Path("config/agent_config.yaml")
    memory_config_path: Path = Path("config/memory_config.yaml")
    database_path: Path = Path("data/tooling.db")
    audit_log_path: Path = Path("logs/tool_usage.jsonl")
    projects_root: Path = Path("projects")
    datasets_root: Path = Path("datasets")
    docs_root: Path = Path("docs")
    scripts_root: Path = Path("scripts")
    workflows_root: Path = Path("app/workflows/definitions")
    prompts_root: Path = Path("app/prompts")
    plugins_root: Path = Path("app/plugins")

    service_tokens_csv: str = Field(default="dev-token")

    requests_per_minute: int = 60
    max_concurrent_per_agent: int = 4
    default_timeout_sec: int = 30
    max_output_bytes: int = 200_000
    default_memory_limit_mb: int = 512
    max_run_steps: int = 20
    max_debug_attempts: int = 2
    max_review_cycles: int = 1
    knowledge_snippet_limit: int = 4
    memory_snippet_limit: int = 4

    serpapi_api_key: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_chat_model: Optional[str] = None
    llm_embedding_model: Optional[str] = None
    image3d_service_base_url: str = "http://127.0.0.1:8093"

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

    def load_yaml(self, value: Path) -> dict[str, Any]:
        resolved = self.resolve_path(value)
        if not resolved.exists():
            return {}
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
