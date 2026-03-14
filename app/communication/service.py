from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings
from app.security.redaction import redact_mapping, redact_text
from app.storage.repositories import ToolingRepository


class PromptService:
    def __init__(self, settings: Settings, repository: ToolingRepository) -> None:
        self.settings = settings
        self.repository = repository

    def sync_builtin_prompts(self, extra_prompt_paths: list[Path] | None = None) -> None:
        prompt_paths = sorted(self.settings.resolve_path(self.settings.prompts_root).glob("*_prompt.md"))
        for prompt_path in [*prompt_paths, *(extra_prompt_paths or [])]:
            role_name = prompt_path.stem.replace("_prompt", "")
            self.repository.upsert_prompt_template(
                prompt_name=prompt_path.name,
                role_name=role_name,
                template_body=prompt_path.read_text(encoding="utf-8"),
            )

    def build_prompt(self, prompt_name: str, context: dict[str, Any]) -> str:
        prompt_record = self.repository.get_prompt_template(prompt_name)
        template_body = prompt_record.template_body if prompt_record else ""
        rendered_context = yaml.safe_dump(context, sort_keys=False, allow_unicode=False)
        return f"{template_body.strip()}\n\nContext:\n{rendered_context}".strip()


class CommunicationService:
    def __init__(self, settings: Settings, repository: ToolingRepository) -> None:
        self.settings = settings
        self.repository = repository

    def add_message(
        self,
        *,
        run_id: str,
        task_id: str,
        step_id: str | None,
        agent_id: str,
        message_type: str,
        content_md: str,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> None:
        secrets = [self.settings.serpapi_api_key or ""]
        self.repository.add_agent_message(
            message_id=str(uuid.uuid4()),
            run_id=run_id,
            task_id=task_id,
            step_id=step_id,
            agent_id=agent_id,
            message_type=message_type,
            content_md=redact_text(content_md, secrets),
            artifacts_json=redact_mapping(artifacts or [], secrets),
        )

    def list_messages(self, run_id: str) -> list[dict[str, Any]]:
        return [record.model_dump() for record in self.repository.list_agent_messages(run_id)]
