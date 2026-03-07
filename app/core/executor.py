from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.auth import AuthContext
from app.core.container import ServiceContainer
from app.core.errors import PermissionDeniedError, ValidationError
from app.registry.base_tool import ToolContext, ToolResult


def execute_tool(
    *,
    container: ServiceContainer,
    auth: AuthContext,
    tool_name: str,
    input_data: dict[str, Any],
    dry_run: bool,
    request_id: str | None,
) -> dict[str, Any]:
    request_identifier = request_id or auth.request_id
    registered = container.registry.get(tool_name)

    container.permissions.check_tool_access(auth.agent_id, tool_name)
    container.permissions.enforce_input(auth.agent_id, tool_name, input_data)

    if dry_run:
        return {
            "execution_id": None,
            "request_id": request_identifier,
            "tool_name": tool_name,
            "status": "dry_run",
            "result": {
                "ok": True,
                "data": {"validated": True},
                "error_code": None,
                "error_message": None,
                "artifacts": [],
                "duration_ms": 0,
            },
        }

    container.quota.acquire(auth.agent_id)
    started = time.monotonic()
    execution_id = str(uuid.uuid4())
    container.repository.create_execution(
        execution_id=execution_id,
        request_id=request_identifier,
        agent_id=auth.agent_id,
        tool_name=tool_name,
        input_payload=input_data,
    )

    status = "success"
    result = ToolResult(ok=False, error_code="INTERNAL_ERROR", error_message="Unknown error")
    try:
        context = ToolContext(
            agent_id=auth.agent_id,
            request_id=request_identifier,
            timeout_sec=container.settings.default_timeout_sec,
            resource_limits={
                "max_output_bytes": container.settings.max_output_bytes,
                "default_memory_limit_mb": container.settings.default_memory_limit_mb,
            },
            policy_snapshot=container.permissions.policy_snapshot(auth.agent_id),
            workspace_root=container.settings.workspace_root,
            sandbox=container.sandbox,
            settings=container.settings,
            permissions=container.permissions,
        )
        result = registered.tool.run(context, input_data)
        status = "success" if result.ok else "failed"
    except PermissionDeniedError as exc:
        status = "failed"
        result = ToolResult(
            ok=False,
            error_code=exc.code,
            error_message=exc.message,
            data={},
            artifacts=[],
        )
    except Exception as exc:
        status = "failed"
        result = ToolResult(
            ok=False,
            error_code="EXECUTION_ERROR",
            error_message=str(exc),
            data={},
            artifacts=[],
        )
    finally:
        container.quota.release(auth.agent_id)

    duration_ms = int((time.monotonic() - started) * 1000)
    result.duration_ms = duration_ms
    container.repository.complete_execution(
        execution_id=execution_id,
        status=status,
        output_payload=result.model_dump(),
        error_code=result.error_code,
        error_message=result.error_message,
        duration_ms=duration_ms,
    )
    for artifact in result.artifacts:
        container.repository.add_artifact(
            execution_id=execution_id,
            artifact_type=str(artifact.get("type", "generic")),
            artifact_path=artifact.get("path"),
            artifact_json=artifact,
        )

    container.audit_logger.log_event(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_identifier,
            "execution_id": execution_id,
            "agent_id": auth.agent_id,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "error_code": result.error_code,
        }
    )

    return {
        "execution_id": execution_id,
        "request_id": request_identifier,
        "tool_name": tool_name,
        "status": status,
        "result": result.model_dump(),
    }


def ensure_request_id_matches(header_request_id: str, body_request_id: str | None) -> None:
    if body_request_id and body_request_id != header_request_id:
        raise ValidationError("Body request_id must match X-Request-Id header")
