from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.communication.service import PromptService
from app.core.auth import AuthContext
from app.core.executor import execute_tool
from app.knowledge.service import KnowledgeService
from app.llm.models import LLMGenerateContext
from app.llm.router import LLMRouter
from app.memory.service import MemoryService
from app.storage.repositories import ToolingRepository

from app.agents.schemas import AgentExecutionContext, BaseAgentResult, ToolCallModel


class AgentToolExecutor:
    def __init__(self, container: Any) -> None:
        self.container = container

    def execute_calls(
        self,
        *,
        agent_name: str,
        allowed_tools: set[str],
        max_calls: int,
        tool_calls: list[ToolCallModel],
    ) -> list[dict[str, Any]]:
        if not allowed_tools or max_calls <= 0:
            return []
        executed: list[dict[str, Any]] = []
        for tool_call in tool_calls[:max_calls]:
            if allowed_tools and tool_call.tool_name not in allowed_tools:
                continue
            auth = AuthContext(
                service_token="internal",
                agent_id=agent_name,
                request_id=str(uuid.uuid4()),
            )
            executed.append(
                execute_tool(
                    container=self.container,
                    auth=auth,
                    tool_name=tool_call.tool_name,
                    input_data=tool_call.input,
                    dry_run=False,
                    request_id=auth.request_id,
                )
            )
        return executed


class BaseAgent:
    agent_name = "base"
    result_model: type[BaseModel] = BaseAgentResult

    def __init__(
        self,
        *,
        llm_router: LLMRouter,
        prompt_service: PromptService,
        knowledge_service: KnowledgeService,
        memory_service: MemoryService,
        repository: ToolingRepository,
        tool_executor: AgentToolExecutor,
        prompt_name: str,
        agent_config: dict[str, Any],
    ) -> None:
        self.llm_router = llm_router
        self.prompt_service = prompt_service
        self.knowledge_service = knowledge_service
        self.memory_service = memory_service
        self.repository = repository
        self.tool_executor = tool_executor
        self.prompt_name = prompt_name
        self.agent_config = agent_config

    def run(self, context: AgentExecutionContext) -> BaseModel:
        prompt = self.prompt_service.build_prompt(
            self.prompt_name,
            {
                "agent": self.agent_name,
                "project": context.project.model_dump(),
                "task": context.task.model_dump(),
                "run": context.run.model_dump(),
                "workflow_step": context.workflow_step.model_dump(),
                "knowledge": self.knowledge_service.retrieve(
                    context.project.project_id,
                    context.task.title,
                    limit=4,
                ),
                "memory": self.memory_service.retrieve(
                    context.project.project_id,
                    context.task.title,
                    limit=4,
                ),
            },
        )
        try:
            result = self.llm_router.generate_structured(
                prompt,
                self.result_model,
                LLMGenerateContext(
                    agent_name=self.agent_name,
                    project_id=context.project.project_id,
                    task_id=context.task.task_id,
                    run_id=context.run.run_id,
                    step_id=context.workflow_step.id,
                    metadata={"task_title": context.task.title},
                ),
            )
        except Exception as exc:
            result = self.result_model.model_validate(self._fallback_payload(context, exc))

        result = self._augment_result(context, result)
        return result

    def allowed_tools(self, context: AgentExecutionContext) -> set[str]:
        step_tools = set(context.workflow_step.allowed_tools)
        config_tools = set(self.agent_config.get("allowed_tools", []))
        if not step_tools:
            return set()
        if not config_tools:
            return step_tools
        return step_tools & config_tools

    def max_tool_calls(self) -> int:
        return int(self.agent_config.get("max_tool_calls", 1))

    def execute_tool_calls(
        self,
        context: AgentExecutionContext,
        result: BaseAgentResult,
    ) -> BaseAgentResult:
        if not result.tool_calls:
            return result
        executed = self.tool_executor.execute_calls(
            agent_name=self.agent_name,
            allowed_tools=self.allowed_tools(context),
            max_calls=self.max_tool_calls(),
            tool_calls=result.tool_calls,
        )
        if not executed:
            return result
        payload = result.model_dump()
        payload["metadata"] = {**payload.get("metadata", {}), "tool_results": executed}
        return result.__class__.model_validate(payload)

    def _augment_result(self, context: AgentExecutionContext, result: BaseModel) -> BaseModel:
        if isinstance(result, BaseAgentResult):
            result = self.execute_tool_calls(context, result)
        return result

    def _fallback_payload(
        self,
        context: AgentExecutionContext,
        error: Exception,
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "summary": f"{self.agent_name} produced a fallback result for {context.task.title}.",
            "findings": [str(error)],
            "next_steps": [],
            "tool_calls": [],
            "artifacts": [],
            "metadata": {"fallback": True, "error": str(error)},
        }
