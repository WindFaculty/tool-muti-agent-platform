from __future__ import annotations

from typing import Any

from app.services.llm import LlmService
from app.services.prompt_context import PromptContextBuilderService


class FastResponseService:
    def __init__(self, llm_service: LlmService, prompt_context_builder: PromptContextBuilderService) -> None:
        self._llm_service = llm_service
        self._prompt_context_builder = prompt_context_builder

    def compose(
        self,
        *,
        provider: str,
        user_message: str,
        intent: str,
        factual_context: dict[str, Any],
        spoken_brief: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        reply = self._llm_service.complete(
            provider=provider,
            system_prompt=self._system_prompt(),
            user_prompt=self._build_prompt(user_message, intent, factual_context, spoken_brief),
        )
        return reply.text, reply.token_usage

    def fallback_compose(self, *, spoken_brief: str | None, factual_context: dict[str, Any]) -> str:
        if spoken_brief:
            return spoken_brief
        summary = factual_context.get("summary") or factual_context.get("daily") or {}
        return summary.get("text") or "Minh da tong hop xong va san sang noi ngan gon lai cho ban."

    def _system_prompt(self) -> str:
        return (
            "Vietnamese assistant. Use only ctx. "
            "Reply briefly and naturally. "
            "Keys: msg, intent, brief, facts."
        )

    def _build_prompt(
        self,
        user_message: str,
        intent: str,
        factual_context: dict[str, Any],
        spoken_brief: str | None,
    ) -> str:
        return self._prompt_context_builder.build_fast_prompt(
            user_message=user_message,
            intent=intent,
            factual_context=factual_context,
            spoken_brief=spoken_brief,
        )
