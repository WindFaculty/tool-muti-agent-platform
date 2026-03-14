from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import Settings
from app.projects.service import ProjectService
from app.storage.repositories import ToolingRepository


class KnowledgeService:
    def __init__(
        self,
        settings: Settings,
        repository: ToolingRepository,
        project_service: ProjectService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.project_service = project_service

    def index_project(self, project_id: str) -> dict[str, int]:
        project_root = self.project_service.project_root(project_id)
        candidates = [
            project_root / "project_context.md",
            project_root / "architecture.md",
            project_root / "coding_rules.md",
            project_root / "api_spec.md",
            *sorted((project_root / "knowledge").glob("*.md")),
        ]
        indexed = 0
        for path in candidates:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            document_id = f"{project_id}:{path.name}"
            summary = self._summarize(content)
            self.repository.upsert_knowledge_document(
                document_id=document_id,
                project_id=project_id,
                title=path.stem,
                content_path=str(path),
                content_sha256=digest,
                tags_json=[path.stem],
                summary_md=summary,
                source="project",
            )
            indexed += 1
        return {"indexed": indexed}

    def retrieve(self, project_id: str, query: str, limit: int) -> list[dict[str, str]]:
        query_terms = {term.lower() for term in query.split() if term.strip()}
        scored: list[tuple[int, str, str]] = []
        for record in self.repository.list_knowledge_documents(project_id):
            path = Path(record.content_path)
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            haystack = f"{record.title}\n{content}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score > 0 or not query_terms:
                scored.append((score, record.title, content[:2000]))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"title": title, "content": content, "score": str(score)}
            for score, title, content in scored[:limit]
        ]

    @staticmethod
    def _summarize(content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        return "\n".join(lines[:3])
