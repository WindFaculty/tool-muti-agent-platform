from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.storage.models import ProjectRecord
from app.storage.repositories import ToolingRepository


class ProjectService:
    def __init__(self, settings: Settings, repository: ToolingRepository) -> None:
        self.settings = settings
        self.repository = repository

    def create_project(
        self,
        *,
        project_id: str,
        name: str,
        default_workflow_id: str = "feature-development",
        status: str = "active",
    ) -> ProjectRecord:
        project_root = self.project_root(project_id)
        (project_root / "tasks").mkdir(parents=True, exist_ok=True)
        (project_root / "knowledge").mkdir(parents=True, exist_ok=True)
        (project_root / "memory").mkdir(parents=True, exist_ok=True)
        (project_root / "workspace" / "runs").mkdir(parents=True, exist_ok=True)

        coding_rules_source = self.settings.resolve_path(self.settings.docs_root) / "coding_rules.md"
        defaults = {
            "project_context.md": f"# {name}\n\nProject context.\n",
            "architecture.md": f"# {name} Architecture\n\nDescribe the system architecture.\n",
            "coding_rules.md": coding_rules_source.read_text(encoding="utf-8"),
            "api_spec.md": f"# {name} API Spec\n\nDocument APIs here.\n",
        }
        for file_name, content in defaults.items():
            target = project_root / file_name
            if not target.exists():
                target.write_text(content, encoding="utf-8")

        self.repository.upsert_project(
            project_id=project_id,
            name=name,
            root_path=str(project_root),
            default_workflow_id=default_workflow_id,
            status=status,
        )
        project = self.repository.get_project(project_id)
        assert project is not None
        return project

    def get_project(self, project_id: str) -> ProjectRecord | None:
        return self.repository.get_project(project_id)

    def list_projects(self) -> list[ProjectRecord]:
        return self.repository.list_projects()

    def project_root(self, project_id: str) -> Path:
        return self.settings.resolve_path(self.settings.projects_root) / project_id
