from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import ExecutionError
from app.registry.base_tool import ToolContext
from app.tools.image3d_tools.cancel_reconstruction import CancelReconstructionTool
from app.tools.image3d_tools.get_reconstruction_status import GetReconstructionStatusTool
from app.tools.image3d_tools.submit_reconstruction import SubmitMultiviewReconstructionTool


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class DummyPermissions:
    def validate_command(self, agent_id: str, tool_name: str, command):
        return None


class DummySandbox:
    def run(self, *args, **kwargs):
        raise AssertionError("Sandbox should not be used by Image3D HTTP tools")


def make_context() -> ToolContext:
    settings = Settings(
        workspace_root=Path("D:/Antigaravity_Code/tro_ly"),
        image3d_service_base_url="http://127.0.0.1:8093",
    )
    return ToolContext(
        agent_id="codex",
        request_id="req-1",
        timeout_sec=30,
        resource_limits={},
        policy_snapshot={},
        workspace_root=Path("D:/Antigaravity_Code/tro_ly"),
        sandbox=DummySandbox(),
        settings=settings,
        permissions=DummyPermissions(),
    )


def test_submit_multiview_reconstruction_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, url: str, json=None, timeout: int = 0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8093/v1/reconstructions"
        assert json["engine"] == "meshroom"
        return DummyResponse(
            200,
            {
                "job_id": "job-123",
                "status": "queued",
                "progress": 0,
                "message": "Queued",
                "metrics": {},
                "artifacts": [],
                "cancel_requested": False,
                "request": json,
                "created_at": "2026-03-08T00:00:00+00:00",
                "updated_at": "2026-03-08T00:00:00+00:00",
                "error_message": None,
            },
        )

    monkeypatch.setattr("app.tools.image3d_tools.common.requests.request", fake_request)
    tool = SubmitMultiviewReconstructionTool()
    result = tool.execute(
        make_context(),
        {
            "input_dir": "captures/figurine",
            "subject_type": "character_figurine",
            "engine": "meshroom",
            "quality_preset": "balanced",
            "export_formats": ["obj", "glb"],
            "timeout_sec": 30,
        },
    )
    assert result.ok is True
    assert result.data["job_id"] == "job-123"


def test_get_reconstruction_status_collects_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, url: str, json=None, timeout: int = 0):
        assert method == "GET"
        assert url.endswith("/v1/reconstructions/job-123")
        return DummyResponse(
            200,
            {
                "job_id": "job-123",
                "status": "completed",
                "progress": 100,
                "message": "Done",
                "metrics": {"artifact_count": 2},
                "artifacts": [
                    {"type": "obj", "path": "D:/Antigaravity_Code/tro_ly/output/reconstructions/job-123/artifacts/model.obj", "label": "OBJ"},
                    {"type": "glb", "path": "D:/Antigaravity_Code/tro_ly/output/reconstructions/job-123/artifacts/model.glb", "label": "GLB"},
                ],
                "cancel_requested": False,
                "request": {
                    "input_dir": "captures/figurine",
                    "subject_type": "character_figurine",
                    "engine": "meshroom",
                    "quality_preset": "balanced",
                    "export_formats": ["obj", "glb"],
                },
                "created_at": "2026-03-08T00:00:00+00:00",
                "updated_at": "2026-03-08T00:00:00+00:00",
                "error_message": None,
            },
        )

    monkeypatch.setattr("app.tools.image3d_tools.common.requests.request", fake_request)
    tool = GetReconstructionStatusTool()
    result = tool.execute(make_context(), {"job_id": "job-123", "timeout_sec": 30})
    assert result.ok is True
    assert len(result.artifacts) == 2
    assert result.data["status"] == "completed"


def test_cancel_reconstruction_raises_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, url: str, json=None, timeout: int = 0):
        return DummyResponse(404, {"detail": "Job 'missing' not found"})

    monkeypatch.setattr("app.tools.image3d_tools.common.requests.request", fake_request)
    tool = CancelReconstructionTool()
    with pytest.raises(ExecutionError):
        tool.execute(make_context(), {"job_id": "missing", "timeout_sec": 30})
