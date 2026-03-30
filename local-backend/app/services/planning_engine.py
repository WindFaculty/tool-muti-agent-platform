from __future__ import annotations

import json
from typing import Any

from app.models.schemas import AssistantPlanPayload
from app.services.llm import LlmService
from app.services.prompt_context import PromptContextBuilderService


class PlanningService:
    def __init__(self, llm_service: LlmService, prompt_context_builder: PromptContextBuilderService) -> None:
        self._llm_service = llm_service
        self._prompt_context_builder = prompt_context_builder

    def build_plan(
        self,
        *,
        provider: str,
        user_message: str,
        intent: str,
        selected_date: str | None,
        notes_context: str | None,
        factual_context: dict[str, Any],
        rolling_summary: str,
        long_term_memory: list[dict[str, Any]],
    ) -> tuple[AssistantPlanPayload, dict[str, Any]]:
        prompt = self._build_prompt(
            user_message=user_message,
            intent=intent,
            selected_date=selected_date,
            notes_context=notes_context,
            factual_context=factual_context,
            rolling_summary=rolling_summary,
            long_term_memory=long_term_memory,
        )
        reply = self._llm_service.complete(
            provider=provider,
            system_prompt=self._system_prompt(),
            user_prompt=prompt,
            json_output=True,
        )
        return self._parse_reply(reply.text, user_message, factual_context), reply.token_usage

    def fallback_plan(
        self,
        *,
        user_message: str,
        factual_context: dict[str, Any],
        notes_context: str | None,
    ) -> AssistantPlanPayload:
        daily = factual_context.get("daily") or factual_context.get("summary") or {}
        weekly = factual_context.get("weekly") or {}
        tasks = factual_context.get("tasks") or daily.get("items") or []
        top_titles = [item.get("title", "") for item in tasks[:3] if item.get("title")]
        suggestions = daily.get("suggestions") or []
        if not suggestions and weekly.get("overloaded_days"):
            suggestions = [f"Can bang tai vao {weekly['overloaded_days'][0]['date']}."]
        spoken_brief = " ".join(
            part for part in [
                daily.get("text"),
                f"Uu tien: {', '.join(top_titles)}." if top_titles else "",
            ] if part
        ).strip()
        return AssistantPlanPayload(
            intent="planning",
            task_type="planning",
            reasoning_summary="Fallback planning from local task context.",
            actionable_plan=suggestions or top_titles,
            task_actions=[],
            spoken_brief=spoken_brief or "Mình da tong hop lai cong viec chinh de ban bat dau.",
            ui_cards=[
                {"type": "planning_context", "payload": {"daily": daily, "weekly": weekly, "notes": notes_context or ""}},
            ],
            memory_candidates=[],
        )

    def _system_prompt(self) -> str:
        return (
            "Vietnamese planning assistant. Use only ctx. "
            "Input keys: msg, intent, date, notes, facts, roll, mem. "
            "Return JSON with keys: intent, task_type, reasoning_summary, actionable_plan, "
            "task_actions, spoken_brief, ui_cards, memory_candidates."
        )

    def _build_prompt(
        self,
        *,
        user_message: str,
        intent: str,
        selected_date: str | None,
        notes_context: str | None,
        factual_context: dict[str, Any],
        rolling_summary: str,
        long_term_memory: list[dict[str, Any]],
    ) -> str:
        return self._prompt_context_builder.build_plan_prompt(
            user_message=user_message,
            intent=intent,
            selected_date=selected_date,
            notes_context=notes_context,
            factual_context=factual_context,
            rolling_summary=rolling_summary,
            long_term_memory=long_term_memory,
        )

    def _parse_reply(self, raw_text: str, user_message: str, factual_context: dict[str, Any]) -> AssistantPlanPayload:
        try:
            data = json.loads(raw_text)
            return AssistantPlanPayload.model_validate(data)
        except Exception:
            return self.fallback_plan(
                user_message=user_message,
                factual_context=factual_context,
                notes_context=None,
            )
