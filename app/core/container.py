from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.agents.factory import AgentFactory
from app.communication.service import CommunicationService, PromptService
from app.core.config import Settings
from app.evaluation.service import EvaluationService
from app.knowledge.service import KnowledgeService
from app.llm.router import LLMRouter
from app.memory.service import MemoryService
from app.monitoring.service import MonitoringService
from app.orchestrator.service import OrchestratorService
from app.plugins.loader import PluginLoader
from app.projects.service import ProjectService
from app.core.permissions import PermissionEngine
from app.core.quota import QuotaManager
from app.core.sandbox_windows import SandboxRunner
from app.logging.audit_logger import AuditLogger
from app.registry.tool_loader import ToolLoader
from app.registry.tool_registry import ToolRegistry
from app.storage.repositories import ToolingRepository
from app.tasks.service import TaskService
from app.workflows.loader import WorkflowLoader
from app.workspace.service import WorkspaceService


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
    llm_router: Any | None = None
    plugin_loader: Any | None = None
    prompt_service: Any | None = None
    workflow_loader: Any | None = None
    project_service: Any | None = None
    task_service: Any | None = None
    knowledge_service: Any | None = None
    memory_service: Any | None = None
    workspace_service: Any | None = None
    communication_service: Any | None = None
    evaluation_service: Any | None = None
    monitoring_service: Any | None = None
    agent_factory: Any | None = None
    orchestrator: Any | None = None


def build_container(settings: Settings) -> ServiceContainer:
    database_path = settings.resolve_path(settings.database_path)
    audit_path = settings.resolve_path(settings.audit_log_path)
    tool_config = settings.resolve_path(settings.tool_config_path)
    policy_config = settings.resolve_path(settings.policy_config_path)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.resolve_path(settings.projects_root).mkdir(parents=True, exist_ok=True)
    settings.resolve_path(settings.datasets_root).mkdir(parents=True, exist_ok=True)
    settings.resolve_path(settings.docs_root).mkdir(parents=True, exist_ok=True)
    settings.resolve_path(settings.scripts_root).mkdir(parents=True, exist_ok=True)
    settings.resolve_path(settings.plugins_root).mkdir(parents=True, exist_ok=True)

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
    container = ServiceContainer(
        settings=settings,
        registry=registry,
        permissions=permissions,
        sandbox=sandbox,
        repository=repository,
        audit_logger=audit_logger,
        quota=quota,
        start_time=time.monotonic(),
    )
    llm_router = LLMRouter(settings)
    plugin_loader = PluginLoader(settings)
    prompt_service = PromptService(settings, repository)
    prompt_service.sync_builtin_prompts(plugin_loader.discover_prompt_files())
    workflow_loader = WorkflowLoader(settings, repository)
    workflow_loader.sync_workflows(plugin_loader.discover_workflow_files())
    project_service = ProjectService(settings, repository)
    task_service = TaskService(settings, repository, project_service)
    knowledge_service = KnowledgeService(settings, repository, project_service)
    memory_service = MemoryService(settings, repository, project_service, llm_router)
    workspace_service = WorkspaceService()
    communication_service = CommunicationService(settings, repository)
    evaluation_service = EvaluationService(repository)
    monitoring_service = MonitoringService(repository)
    agent_factory = AgentFactory(
        settings=settings,
        llm_router=llm_router,
        prompt_service=prompt_service,
        knowledge_service=knowledge_service,
        memory_service=memory_service,
        repository=repository,
        container=container,
    )
    orchestrator = OrchestratorService(
        settings=settings,
        repository=repository,
        project_service=project_service,
        task_service=task_service,
        workflow_loader=workflow_loader,
        agent_factory=agent_factory,
        workspace_service=workspace_service,
        communication_service=communication_service,
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        evaluation_service=evaluation_service,
    )
    container.llm_router = llm_router
    container.plugin_loader = plugin_loader
    container.prompt_service = prompt_service
    container.workflow_loader = workflow_loader
    container.project_service = project_service
    container.task_service = task_service
    container.knowledge_service = knowledge_service
    container.memory_service = memory_service
    container.workspace_service = workspace_service
    container.communication_service = communication_service
    container.evaluation_service = evaluation_service
    container.monitoring_service = monitoring_service
    container.agent_factory = agent_factory
    container.orchestrator = orchestrator
    return container
