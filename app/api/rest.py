from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_auth_context, get_container
from app.core.auth import AuthContext
from app.core.container import ServiceContainer
from app.core.errors import PermissionDeniedError, ValidationError
from app.core.executor import ensure_request_id_matches, execute_tool


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    dry_run: bool = False


router = APIRouter(prefix="/v1", tags=["tooling"])


@router.get("/tools")
def list_tools(
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    tools = container.registry.list_tools()
    visible_tools = []
    for tool in tools:
        try:
            container.permissions.check_tool_access(auth.agent_id, str(tool["name"]))
            visible_tools.append(tool)
        except PermissionDeniedError:
            continue
    return {"tools": visible_tools}


@router.post("/tools/execute")
def execute_tool_endpoint(
    payload: ToolExecuteRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    ensure_request_id_matches(auth.request_id, payload.request_id)
    return execute_tool(
        container=container,
        auth=auth,
        tool_name=payload.tool_name,
        input_data=payload.input,
        dry_run=payload.dry_run,
        request_id=payload.request_id,
    )


@router.get("/executions/{execution_id}")
def get_execution(
    execution_id: str,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    record = container.repository.get_execution(execution_id)
    if not record:
        raise ValidationError(f"Execution '{execution_id}' not found")
    if record.agent_id != auth.agent_id and auth.agent_id != "admin":
        raise PermissionDeniedError("Cannot access another agent execution")
    return record.model_dump()


@router.get("/health")
def health(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    _ = auth
    uptime_sec = int(time.monotonic() - container.start_time)
    return {
        "status": "ok",
        "service": request.app.state.settings.app_name,
        "version": request.app.state.settings.app_version,
        "db": container.repository.health_check(),
        "audit_log": container.audit_logger.health_check(),
        "uptime_sec": uptime_sec,
    }
