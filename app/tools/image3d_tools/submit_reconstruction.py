from __future__ import annotations

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext
from app.tools.image3d_tools.common import perform_request, tool_result_from_job


class SubmitReconstructionInput(BaseModel):
    input_dir: str
    subject_type: str = "character_figurine"
    engine: str = "meshroom"
    quality_preset: str = "balanced"
    export_formats: list[str] = Field(default_factory=lambda: ["obj", "glb"])
    timeout_sec: int = Field(default=30, ge=1, le=120)


class SubmitMultiviewReconstructionTool(BaseTool):
    name = "submit_multiview_reconstruction"
    description = "Submit an asynchronous multi-view image to 3D reconstruction job"
    input_model = SubmitReconstructionInput

    def execute(self, context: ToolContext, input_data: dict):
        url = f"{context.settings.image3d_service_base_url.rstrip('/')}/v1/reconstructions"
        payload = perform_request(
            method="POST",
            url=url,
            timeout_sec=input_data["timeout_sec"],
            json_payload={
                "input_dir": input_data["input_dir"],
                "subject_type": input_data["subject_type"],
                "engine": input_data["engine"],
                "quality_preset": input_data["quality_preset"],
                "export_formats": input_data["export_formats"],
            },
        )
        return tool_result_from_job(payload)

