from __future__ import annotations

from typing import Any

import requests

from app.core.errors import ExecutionError
from app.registry.base_tool import ToolResult


def perform_request(
    *,
    method: str,
    url: str,
    timeout_sec: int,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(method, url, json=json_payload, timeout=timeout_sec)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise ExecutionError(detail or f"Image3D service returned HTTP {response.status_code}")
    if not isinstance(payload, dict):
        raise ExecutionError("Image3D service returned a non-object payload")
    return payload


def tool_result_from_job(payload: dict[str, Any]) -> ToolResult:
    artifacts = []
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        artifacts.append(
            {
                "type": artifact.get("type", "generic"),
                "path": path,
                "label": artifact.get("label"),
                "metadata": artifact.get("metadata", {}),
            }
        )
    status = payload.get("status")
    return ToolResult(
        ok=True,
        data=payload,
        artifacts=artifacts if status == "completed" else [],
    )

