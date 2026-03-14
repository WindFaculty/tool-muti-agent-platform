from __future__ import annotations

from pathlib import Path

import yaml

from app.core.config import Settings
from app.storage.repositories import ToolingRepository
from app.workflows.models import WorkflowDefinition


class WorkflowLoader:
    def __init__(self, settings: Settings, repository: ToolingRepository) -> None:
        self.settings = settings
        self.repository = repository

    def sync_workflows(self, extra_files: list[Path] | None = None) -> None:
        workflow_paths = sorted(self.settings.resolve_path(self.settings.workflows_root).glob("*.yaml"))
        for workflow_path in [*workflow_paths, *(extra_files or [])]:
            definition = WorkflowDefinition.model_validate(
                yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
            )
            self.repository.upsert_workflow_definition(
                workflow_id=definition.workflow_id,
                version=definition.version,
                description=definition.description,
                steps_yaml=yaml.safe_dump(definition.model_dump(), sort_keys=False),
                is_builtin=workflow_path.is_relative_to(
                    self.settings.resolve_path(self.settings.workflows_root)
                ),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition:
        record = self.repository.get_workflow_definition(workflow_id)
        if not record:
            raise KeyError(workflow_id)
        return WorkflowDefinition.model_validate(yaml.safe_load(record.steps_yaml) or {})

    def list_workflows(self) -> list[WorkflowDefinition]:
        return [
            WorkflowDefinition.model_validate(yaml.safe_load(record.steps_yaml) or {})
            for record in self.repository.list_workflow_definitions()
        ]
