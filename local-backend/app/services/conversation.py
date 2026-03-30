from __future__ import annotations

from app.models.schemas import ChatRequest, ChatResponse
from app.services.assistant_orchestrator import AssistantOrchestrator


class ConversationService:
    def __init__(self, assistant_orchestrator: AssistantOrchestrator) -> None:
        self._assistant_orchestrator = assistant_orchestrator

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        return await self._assistant_orchestrator.handle_chat(request)
