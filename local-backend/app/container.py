from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.events import EventBus
from app.db.repository import SQLiteRepository
from app.services.action_validator import ActionValidator
from app.services.assistant_orchestrator import AssistantOrchestrator
from app.services.conversation import ConversationService
from app.services.fast_response import FastResponseService
from app.services.llm import LlmService
from app.services.memory import MemoryService
from app.services.planning_engine import PlanningService
from app.services.planner import PlannerService
from app.services.prompt_context import PromptContextBuilderService
from app.services.router import RouterService
from app.services.scheduler import SchedulerService
from app.services.settings import SettingsService
from app.services.speech import SpeechService
from app.services.tasks import TaskService


@dataclass
class AppContainer:
    settings: Settings
    repository: SQLiteRepository
    event_bus: EventBus
    settings_service: SettingsService
    llm_service: LlmService
    speech_service: SpeechService
    task_service: TaskService
    planner_service: PlannerService
    action_validator: ActionValidator
    router_service: RouterService
    memory_service: MemoryService
    deep_planning_service: PlanningService
    fast_response_service: FastResponseService
    assistant_orchestrator: AssistantOrchestrator
    conversation_service: ConversationService
    scheduler_service: SchedulerService


def build_container(settings: Settings) -> AppContainer:
    settings.ensure_directories()
    repository = SQLiteRepository(settings.db_path)
    repository.initialize()
    event_bus = EventBus()
    settings_service = SettingsService(repository, settings)
    llm_service = LlmService(settings)
    speech_service = SpeechService(settings)
    task_service = TaskService(repository, settings)
    planner_service = PlannerService(task_service)
    action_validator = ActionValidator(task_service, planner_service)
    router_service = RouterService(settings, llm_service)
    memory_service = MemoryService(repository, short_term_turn_limit=settings.short_term_turn_limit)
    prompt_context_builder = PromptContextBuilderService(settings)
    deep_planning_service = PlanningService(llm_service, prompt_context_builder)
    fast_response_service = FastResponseService(llm_service, prompt_context_builder)
    assistant_orchestrator = AssistantOrchestrator(
        repository=repository,
        event_bus=event_bus,
        action_validator=action_validator,
        router_service=router_service,
        planning_service=deep_planning_service,
        fast_response_service=fast_response_service,
        memory_service=memory_service,
        speech_service=speech_service,
        settings_service=settings_service,
        llm_service=llm_service,
    )
    conversation_service = ConversationService(assistant_orchestrator)
    scheduler_service = SchedulerService(repository, event_bus, settings, speech_service)
    return AppContainer(
        settings=settings,
        repository=repository,
        event_bus=event_bus,
        settings_service=settings_service,
        llm_service=llm_service,
        speech_service=speech_service,
        task_service=task_service,
        planner_service=planner_service,
        action_validator=action_validator,
        router_service=router_service,
        memory_service=memory_service,
        deep_planning_service=deep_planning_service,
        fast_response_service=fast_response_service,
        assistant_orchestrator=assistant_orchestrator,
        conversation_service=conversation_service,
        scheduler_service=scheduler_service,
    )
