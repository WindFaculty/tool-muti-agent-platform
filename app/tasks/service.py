from __future__ import annotations

from datetime import datetime, timezone

import yaml

from app.core.config import Settings
from app.projects.service import ProjectService
from app.storage.models import TaskRecord
from app.storage.repositories import ToolingRepository


class TaskService:
    def __init__(
        self,
        settings: Settings,
        repository: ToolingRepository,
        project_service: ProjectService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.project_service = project_service

    def create_task(
        self,
        *,
        project_id: str,
        title: str,
        description_md: str,
        requirements_md: str,
        expected_output_md: str,
        priority: str,
        workflow_id: str,
    ) -> TaskRecord:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        slug = title.lower().replace(" ", "_").replace("/", "_")
        task_id = f"task_{timestamp}_{slug[:32]}"
        project_root = self.project_service.project_root(project_id)
        task_path = project_root / "tasks" / f"{task_id}.md"
        front_matter = {
            "title": title,
            "description": description_md,
            "requirements": requirements_md,
            "expected_output": expected_output_md,
            "priority": priority,
            "workflow_id": workflow_id,
        }
        markdown = f"---\n{yaml.safe_dump(front_matter, sort_keys=False)}---\n"
        task_path.write_text(markdown, encoding="utf-8")
        self.repository.create_task(
            task_id=task_id,
            project_id=project_id,
            title=title,
            description_md=description_md,
            requirements_md=requirements_md,
            expected_output_md=expected_output_md,
            priority=priority,
            workflow_id=workflow_id,
            status="pending",
            task_path=str(task_path),
        )
        task = self.repository.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self.repository.get_task(task_id)

    def list_tasks(self, project_id: str | None = None) -> list[TaskRecord]:
        return self.repository.list_tasks(project_id)
