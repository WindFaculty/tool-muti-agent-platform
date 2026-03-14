from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.core.config import Settings
from app.llm.router import LLMRouter
from app.projects.service import ProjectService
from app.storage.repositories import ToolingRepository


class MemoryService:
    def __init__(
        self,
        settings: Settings,
        repository: ToolingRepository,
        project_service: ProjectService,
        llm_router: LLMRouter,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.project_service = project_service
        self.llm_router = llm_router
        self.memory_config = settings.load_yaml(settings.memory_config_path)

    def record(
        self,
        *,
        project_id: str,
        kind: str,
        title: str,
        content: str,
        source_run_id: str | None,
        tags: list[str] | None = None,
    ) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        slug = title.lower().replace(" ", "_")[:40]
        target = self.project_service.project_root(project_id) / "memory" / f"{timestamp}_{slug}.md"
        target.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        embeddings_enabled = bool(self.memory_config.get("embeddings", {}).get("enabled", True))
        try:
            embedding = self.llm_router.embed([content])[0] if embeddings_enabled else []
        except Exception:
            embedding = []
        self.repository.upsert_memory_entry(
            entry_id=f"{project_id}:{target.name}",
            project_id=project_id,
            kind=kind,
            title=title,
            content_path=str(target),
            content_sha256=digest,
            tags_json=tags or [],
            embedding_json=embedding,
            source_run_id=source_run_id,
        )

    def retrieve(self, project_id: str, query: str, limit: int) -> list[dict[str, str]]:
        query_terms = {term.lower() for term in query.split() if term.strip()}
        scored: list[tuple[int, str, str]] = []
        for record in self.repository.list_memory_entries(project_id):
            from pathlib import Path

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
