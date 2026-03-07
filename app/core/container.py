from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.config import Settings
from app.core.permissions import PermissionEngine
from app.core.quota import QuotaManager
from app.core.sandbox_windows import SandboxRunner
from app.logging.audit_logger import AuditLogger
from app.registry.tool_loader import ToolLoader
from app.registry.tool_registry import ToolRegistry
from app.storage.repositories import ToolingRepository


@dataclass
class ServiceContainer:
    settings: Settings
    registry: ToolRegistry
    permissions: PermissionEngine
    sandbox: SandboxRunner
    repository: ToolingRepository
    audit_logger: AuditLogger
    quota: QuotaManager
    start_time: float


def build_container(settings: Settings) -> ServiceContainer:
    database_path = settings.resolve_path(settings.database_path)
    audit_path = settings.resolve_path(settings.audit_log_path)
    tool_config = settings.resolve_path(settings.tool_config_path)
    policy_config = settings.resolve_path(settings.policy_config_path)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    settings.workspace_root.mkdir(parents=True, exist_ok=True)

    registry = ToolRegistry()
    loader = ToolLoader(tool_config)
    loader.load_into_registry(registry)

    repository = ToolingRepository(database_path)
    for tool in registry.list_tools():
        repository.upsert_tool(
            name=str(tool["name"]),
            description=str(tool["description"]),
            input_schema=dict(tool["input_schema"]),
            required_permissions=list(tool["required_permissions"]),
        )

    permissions = PermissionEngine(policy_config, settings.workspace_root)
    sandbox = SandboxRunner(
        default_timeout_sec=settings.default_timeout_sec,
        max_output_bytes=settings.max_output_bytes,
    )
    audit_logger = AuditLogger(audit_path)
    quota = QuotaManager(
        requests_per_minute=settings.requests_per_minute,
        max_concurrent_per_agent=settings.max_concurrent_per_agent,
    )

    return ServiceContainer(
        settings=settings,
        registry=registry,
        permissions=permissions,
        sandbox=sandbox,
        repository=repository,
        audit_logger=audit_logger,
        quota=quota,
        start_time=time.monotonic(),
    )

