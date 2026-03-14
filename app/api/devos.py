from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_auth_context, get_container
from app.core.auth import AuthContext
from app.core.container import ServiceContainer
from app.core.errors import ValidationError


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    default_workflow_id: str = "feature-development"


class TaskCreateRequest(BaseModel):
    project_id: str
    title: str
    description_md: str = ""
    requirements_md: str = ""
    expected_output_md: str = ""
    priority: str = "medium"
    workflow_id: str = "feature-development"


class RunActionRequest(BaseModel):
    auto_resume: bool = True


class KnowledgeIndexRequest(BaseModel):
    project_id: str


router = APIRouter(prefix="/v1", tags=["dev-os"])


@router.get("/projects")
def list_projects(
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return {"projects": [project.model_dump() for project in container.project_service.list_projects()]}


@router.post("/projects")
def create_project(
    payload: ProjectCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    project = container.project_service.create_project(
        project_id=payload.project_id,
        name=payload.name,
        default_workflow_id=payload.default_workflow_id,
    )
    return project.model_dump()


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    project = container.project_service.get_project(project_id)
    if not project:
        raise ValidationError(f"Project '{project_id}' not found")
    return project.model_dump()


@router.get("/tasks")
def list_tasks(
    project_id: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return {"tasks": [task.model_dump() for task in container.task_service.list_tasks(project_id)]}


@router.post("/tasks")
def create_task(
    payload: TaskCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    if not container.project_service.get_project(payload.project_id):
        raise ValidationError(f"Project '{payload.project_id}' not found")
    task = container.task_service.create_task(
        project_id=payload.project_id,
        title=payload.title,
        description_md=payload.description_md,
        requirements_md=payload.requirements_md,
        expected_output_md=payload.expected_output_md,
        priority=payload.priority,
        workflow_id=payload.workflow_id,
    )
    return task.model_dump()


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    task = container.task_service.get_task(task_id)
    if not task:
        raise ValidationError(f"Task '{task_id}' not found")
    return task.model_dump()


@router.post("/tasks/{task_id}/run")
def run_task(
    task_id: str,
    payload: RunActionRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    try:
        return container.orchestrator.run_task(task_id, auto_resume=payload.auto_resume)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    try:
        return container.orchestrator.get_run_bundle(run_id)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/runs/{run_id}/resume")
def resume_run(
    run_id: str,
    payload: RunActionRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    try:
        return container.orchestrator.resume_run(run_id, auto_resume=payload.auto_resume)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    try:
        return container.orchestrator.cancel_run(run_id)
    except KeyError as exc:
        raise ValidationError(str(exc)) from exc


@router.get("/runs/{run_id}/messages")
def run_messages(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return {"messages": container.communication_service.list_messages(run_id)}


@router.get("/workflows")
def list_workflows(
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return {"workflows": [workflow.model_dump() for workflow in container.workflow_loader.list_workflows()]}


@router.post("/knowledge/index")
def index_knowledge(
    payload: KnowledgeIndexRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return container.knowledge_service.index_project(payload.project_id)


@router.get("/monitoring/summary")
def monitoring_summary(
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    return container.monitoring_service.summary()


@router.get("/evaluations/{run_id}")
def get_evaluation(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    evaluation = container.evaluation_service.get_evaluation(run_id)
    if not evaluation:
        raise ValidationError(f"Evaluation for run '{run_id}' not found")
    return evaluation
