from __future__ import annotations

from typing import Any

from app.agents.base import AgentToolExecutor
from app.agents.implementations import (
    ArchitectAgent,
    CoderAgent,
    DebuggerAgent,
    DevOpsAgent,
    PlannerAgent,
    ReviewerAgent,
    TestAgent,
)
from app.communication.service import PromptService
from app.core.config import Settings
from app.knowledge.service import KnowledgeService
from app.llm.router import LLMRouter
from app.memory.service import MemoryService
from app.storage.repositories import ToolingRepository


class AgentFactory:
    def __init__(
        self,
        *,
        settings: Settings,
        llm_router: LLMRouter,
        prompt_service: PromptService,
        knowledge_service: KnowledgeService,
        memory_service: MemoryService,
        repository: ToolingRepository,
        container: Any,
    ) -> None:
        self.settings = settings
        self.llm_router = llm_router
        self.prompt_service = prompt_service
        self.knowledge_service = knowledge_service
        self.memory_service = memory_service
        self.repository = repository
        self.tool_executor = AgentToolExecutor(container)
        self.agent_config = settings.load_yaml(settings.agent_config_path)
        self._agents = self._build_agents()

    def get(self, agent_name: str) -> Any:
        return self._agents[agent_name]

    def _build_agents(self) -> dict[str, Any]:
        config = self.agent_config.get("agents", {})
        common = {
            "llm_router": self.llm_router,
            "prompt_service": self.prompt_service,
            "knowledge_service": self.knowledge_service,
            "memory_service": self.memory_service,
            "repository": self.repository,
            "tool_executor": self.tool_executor,
        }
        return {
            "planner": PlannerAgent(
                prompt_name=config["planner"]["prompt"],
                agent_config=config["planner"],
                **common,
            ),
            "architect": ArchitectAgent(
                prompt_name=config["architect"]["prompt"],
                agent_config=config["architect"],
                **common,
            ),
            "coder": CoderAgent(
                prompt_name=config["coder"]["prompt"],
                agent_config=config["coder"],
                **common,
            ),
            "tester": TestAgent(
                prompt_name=config["tester"]["prompt"],
                agent_config=config["tester"],
                **common,
            ),
            "debugger": DebuggerAgent(
                prompt_name=config["debugger"]["prompt"],
                agent_config=config["debugger"],
                **common,
            ),
            "reviewer": ReviewerAgent(
                prompt_name=config["reviewer"]["prompt"],
                agent_config=config["reviewer"],
                **common,
            ),
            "devops": DevOpsAgent(
                prompt_name=config["devops"]["prompt"],
                agent_config=config["devops"],
                **common,
            ),
        }
