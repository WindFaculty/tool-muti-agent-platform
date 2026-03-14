from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowStepDefinition(BaseModel):
    id: str
    agent: str
    input_template: str
    allowed_tools: list[str] = Field(default_factory=list)
    retry_limit: int = 1
    on_success: str
    on_failure: str
    artifacts_to_capture: list[str] = Field(default_factory=list)


class WorkflowDefinition(BaseModel):
    workflow_id: str
    version: str
    description: str
    steps: list[WorkflowStepDefinition]

    def first_step(self) -> WorkflowStepDefinition:
        return self.steps[0]

    def get_step(self, step_id: str) -> WorkflowStepDefinition:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def has_step(self, step_id: str) -> bool:
        return any(step.id == step_id for step in self.steps)
