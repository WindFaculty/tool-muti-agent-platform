from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_auth_context, get_container
from app.core.auth import AuthContext
from app.core.container import ServiceContainer
from app.core.errors import PermissionDeniedError
from app.core.executor import execute_tool


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


router = APIRouter(tags=["mcp"])


@router.post("/mcp")
def mcp_endpoint(
    payload: JsonRpcRequest,
    auth: AuthContext = Depends(get_auth_context),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    try:
        if payload.method == "tools/list":
            tools = []
            for tool in container.registry.list_tools():
                try:
                    container.permissions.check_tool_access(auth.agent_id, str(tool["name"]))
                    tools.append(tool)
                except PermissionDeniedError:
                    continue
            data = {"tools": tools}
        elif payload.method == "tools/call":
            tool_name = payload.params.get("name")
            arguments = payload.params.get("arguments", {})
            dry_run = bool(payload.params.get("dry_run", False))
            if not tool_name:
                raise ValueError("Missing params.name")
            data = execute_tool(
                container=container,
                auth=auth,
                tool_name=tool_name,
                input_data=arguments,
                dry_run=dry_run,
                request_id=auth.request_id,
            )
        else:
            return {
                "jsonrpc": "2.0",
                "id": payload.id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{payload.method}' not found",
                },
            }
        return {"jsonrpc": "2.0", "id": payload.id, "result": data}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": payload.id,
            "error": {"code": -32000, "message": str(exc)},
        }
