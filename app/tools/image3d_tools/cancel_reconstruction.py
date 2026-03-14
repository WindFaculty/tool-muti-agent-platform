from __future__ import annotations

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext
from app.tools.image3d_tools.common import perform_request, tool_result_from_job


class CancelReconstructionInput(BaseModel):
    job_id: str
    timeout_sec: int = Field(default=30, ge=1, le=120)


class CancelReconstructionTool(BaseTool):
    name = "cancel_reconstruction"
    description = "Cancel an asynchronous 3D reconstruction job"
    input_model = CancelReconstructionInput

    def execute(self, context: ToolContext, input_data: dict):
        url = (
            f"{context.settings.image3d_service_base_url.rstrip('/')}/v1/reconstructions/"
            f"{input_data['job_id']}/cancel"
        )
        payload = perform_request(
            method="POST",
            url=url,
            timeout_sec=input_data["timeout_sec"],
        )
        return tool_result_from_job(payload)
