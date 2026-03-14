from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.factory import AgentFactory
from app.agents.schemas import AgentExecutionContext
from app.communication.service import CommunicationService
from app.core.config import Settings
from app.evaluation.service import EvaluationService
from app.knowledge.service import KnowledgeService
from app.memory.service import MemoryService
from app.projects.service import ProjectService
from app.storage.repositories import ToolingRepository
from app.tasks.service import TaskService
from app.workspace.service import WorkspaceService
from app.workflows.loader import WorkflowLoader


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


class OrchestratorService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: ToolingRepository,
        project_service: ProjectService,
        task_service: TaskService,
        workflow_loader: WorkflowLoader,
        agent_factory: AgentFactory,
        workspace_service: WorkspaceService,
        communication_service: CommunicationService,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        evaluation_service: EvaluationService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.project_service = project_service
        self.task_service = task_service
        self.workflow_loader = workflow_loader
        self.agent_factory = agent_factory
        self.workspace_service = workspace_service
        self.communication_service = communication_service
        self.memory_service = memory_service
        self.knowledge_service = knowledge_service
        self.evaluation_service = evaluation_service

    def run_task(self, task_id: str, *, auto_resume: bool = True) -> dict[str, Any]:
        task = self.task_service.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        project = self.project_service.get_project(task.project_id)
        if not project:
            raise KeyError(task.project_id)
        workflow = self.workflow_loader.get_workflow(task.workflow_id)
        run_id = str(uuid.uuid4())
        self.repository.create_task_run(
            run_id=run_id,
            task_id=task.task_id,
            project_id=project.project_id,
            workflow_id=workflow.workflow_id,
            status="queued",
            current_step_id=workflow.first_step().id,
        )
        self.repository.update_task_status(task.task_id, "running")
        return self._execute_run(run_id, auto_resume=auto_resume)

    def resume_run(self, run_id: str, *, auto_resume: bool = True) -> dict[str, Any]:
        run = self.repository.get_task_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run.status in TERMINAL_STATUSES:
            return self.get_run_bundle(run_id)
        return self._execute_run(run_id, auto_resume=auto_resume)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_task_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run.status not in TERMINAL_STATUSES:
            self.repository.update_task_run(
                run_id,
                status="cancelled",
                ended_at=self._now_iso(),
            )
        return self.get_run_bundle(run_id)

    def get_run_bundle(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_task_run(run_id)
        if not run:
            raise KeyError(run_id)
        evaluation = self.repository.get_evaluation(run_id)
        return {
            "run": run.model_dump(),
            "steps": [step.model_dump() for step in self.repository.list_run_steps(run_id)],
            "messages": self.communication_service.list_messages(run_id),
            "evaluation": evaluation.model_dump() if evaluation else None,
        }

    def _execute_run(self, run_id: str, *, auto_resume: bool) -> dict[str, Any]:
        run = self.repository.get_task_run(run_id)
        if not run:
            raise KeyError(run_id)
        task = self.task_service.get_task(run.task_id)
        project = self.project_service.get_project(run.project_id)
        if not task or not project:
            raise KeyError(run_id)
        workflow = self.workflow_loader.get_workflow(run.workflow_id)
        run_workspace = self.workspace_service.prepare_run_workspace(
            Path(project.root_path),
            run.run_id,
        )
        step_attempts = {
            step.step_id: step.retry_count for step in self.repository.list_run_steps(run.run_id)
        }
        review_cycles = 0
        current_step_id = run.current_step_id or workflow.first_step().id

        for _ in range(self.settings.max_run_steps):
            if current_step_id in TERMINAL_STATUSES:
                break
            step = workflow.get_step(current_step_id)
            attempt = step_attempts.get(step.id, -1) + 1
            if attempt > step.retry_limit:
                return self._finalize_run(
                    run,
                    task.task_id,
                    "failed",
                    f"Step '{step.id}' exceeded retry limit.",
                )
            step_attempts[step.id] = attempt
            self.repository.update_task_run(run.run_id, status="running", current_step_id=step.id)

            agent = self.agent_factory.get(step.agent)
            started_at = self._now_iso()
            result = agent.run(
                AgentExecutionContext(
                    project=project,
                    task=task,
                    run=run,
                    workflow_step=step,
                    run_workspace=str(run_workspace),
                    retry_count=attempt,
                    review_cycles=review_cycles,
                )
            )
            ended_at = self._now_iso()
            payload = result.model_dump()
            written_artifacts = self.workspace_service.write_artifacts(
                run_workspace,
                step.agent,
                payload.get("artifacts", []),
            )
            payload["artifacts"] = written_artifacts
            self.repository.upsert_run_step(
                run_id=run.run_id,
                step_id=step.id,
                agent_id=step.agent,
                status=payload["status"],
                retry_count=attempt,
                input_json={"task_id": task.task_id, "title": task.title, "step_id": step.id},
                output_json=payload,
                started_at=started_at,
                ended_at=ended_at,
            )
            self.communication_service.add_message(
                run_id=run.run_id,
                task_id=task.task_id,
                step_id=step.id,
                agent_id=step.agent,
                message_type="agent_result",
                content_md=payload["summary"],
                artifacts=written_artifacts,
            )
            self.memory_service.record(
                project_id=project.project_id,
                kind="agent_result",
                title=f"{step.agent} {step.id}",
                content=payload["summary"],
                source_run_id=run.run_id,
                tags=[step.agent, step.id],
            )

            next_step_id, run_status, review_cycles = self._transition(
                workflow_step=step,
                payload=payload,
                review_cycles=review_cycles,
                auto_resume=auto_resume,
            )
            if run_status in TERMINAL_STATUSES:
                return self._finalize_run(run, task.task_id, run_status, payload["summary"])
            if run_status in {"waiting_debug", "waiting_review"}:
                self.repository.update_task_run(
                    run.run_id,
                    status=run_status,
                    current_step_id=next_step_id,
                    result_summary=payload["summary"],
                )
                return self.get_run_bundle(run.run_id)
            current_step_id = next_step_id

        return self._finalize_run(run, task.task_id, "interrupted", "Run exceeded max step budget.")

    def _transition(
        self,
        *,
        workflow_step: Any,
        payload: dict[str, Any],
        review_cycles: int,
        auto_resume: bool,
    ) -> tuple[str | None, str, int]:
        status = payload.get("status", "success")
        if status == "success":
            target = workflow_step.on_success
        else:
            target = workflow_step.on_failure

        if status == "needs_debug" and not auto_resume:
            return target, "waiting_debug", review_cycles
        if status == "needs_revision":
            if review_cycles >= self.settings.max_review_cycles:
                return None, "failed", review_cycles
            review_cycles += 1
            if not auto_resume:
                return target, "waiting_review", review_cycles

        if target in {"completed", "failed", "cancelled", "interrupted"}:
            return None, target, review_cycles
        return target, "running", review_cycles

    def _finalize_run(
        self,
        run: Any,
        task_id: str,
        status: str,
        summary: str,
    ) -> dict[str, Any]:
        self.repository.update_task_run(
            run.run_id,
            status=status,
            result_summary=summary,
            ended_at=self._now_iso(),
        )
        self.repository.update_task_status(
            task_id,
            "completed" if status == "completed" else status,
        )
        if status in {"completed", "failed", "interrupted"}:
            self.evaluation_service.evaluate_run(run.run_id)
            self.knowledge_service.index_project(run.project_id)
        return self.get_run_bundle(run.run_id)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
