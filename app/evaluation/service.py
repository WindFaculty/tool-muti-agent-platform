from __future__ import annotations

from app.storage.repositories import ToolingRepository


class EvaluationService:
    def __init__(self, repository: ToolingRepository) -> None:
        self.repository = repository

    def evaluate_run(self, run_id: str) -> dict:
        run = self.repository.get_task_run(run_id)
        if not run:
            raise KeyError(run_id)
        steps = self.repository.list_run_steps(run_id)
        failures = sum(1 for step in steps if step.status == "failed")
        retries = sum(step.retry_count for step in steps)
        completed_bonus = 10 if run.status == "completed" else 0
        score = max(0.0, min(100.0, 100.0 - failures * 20.0 - retries * 5.0 + completed_bonus))
        metrics = {"failures": failures, "retries": retries, "steps": len(steps)}
        summary = f"Run {run_id} ended with status {run.status} and score {score:.1f}."
        self.repository.upsert_evaluation(
            run_id=run_id,
            score=score,
            metrics_json=metrics,
            summary_md=summary,
        )
        evaluation = self.repository.get_evaluation(run_id)
        assert evaluation is not None
        return evaluation.model_dump()

    def get_evaluation(self, run_id: str) -> dict | None:
        evaluation = self.repository.get_evaluation(run_id)
        return evaluation.model_dump() if evaluation else None
