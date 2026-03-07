from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def _build_policy(workspace_root: Path, tmp_root: Path) -> dict:
    return {
        "dangerous_tokens": [
            "rm -rf",
            "del /f /s /q",
            "format c:",
            "shutdown",
            "invoke-expression",
            "powershell -enc",
        ],
        "agents": {
            "default": {
                "allow_tools": ["*"],
                "deny_tools": [],
                "path_roots": [
                    str(workspace_root),
                    str(tmp_root),
                ],
                "network_allowlist": ["*"],
                "command_allowlist": {
                    "*": [
                        "python",
                        "pip",
                        "pytest",
                        "flake8",
                        "isort",
                        "ruff",
                        "black",
                        "git",
                        "docker",
                        "npm",
                        "mvn",
                        "uvicorn",
                        "node",
                        "powershell",
                        "rg",
                    ]
                },
            }
        },
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    project_root = Path(__file__).resolve().parents[1]
    workspace_root = project_root.parent
    policy_path = tmp_path / "policies.yaml"
    policy_path.write_text(
        yaml.safe_dump(_build_policy(workspace_root, workspace_root / "agent-platform" / "tmp")),
        encoding="utf-8",
    )

    monkeypatch.setenv("AGENT_PLATFORM_SERVICE_TOKENS_CSV", "dev-token")
    monkeypatch.setenv("AGENT_PLATFORM_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("AGENT_PLATFORM_DATABASE_PATH", str(tmp_path / "tooling.db"))
    monkeypatch.setenv("AGENT_PLATFORM_AUDIT_LOG_PATH", str(tmp_path / "tool_usage.jsonl"))
    monkeypatch.setenv("AGENT_PLATFORM_TOOL_CONFIG_PATH", str(project_root / "config" / "tools.yaml"))
    monkeypatch.setenv("AGENT_PLATFORM_POLICY_CONFIG_PATH", str(policy_path))

    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def auth_headers(agent_id: str = "codex") -> dict[str, str]:
    return {
        "X-Service-Token": "dev-token",
        "X-Agent-Id": agent_id,
        "X-Request-Id": str(uuid.uuid4()),
    }

