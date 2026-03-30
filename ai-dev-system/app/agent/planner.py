from __future__ import annotations

from pathlib import Path

from app.agent.task_spec import TaskSpec
from app.agent.state import ActionRequest
from app.profiles.base_profile import BaseProfile


class TaskPlanner:
    """Translate a bounded task string into profile-specific actions."""

    def build_plan(
        self,
        profile: BaseProfile,
        task: str | TaskSpec,
        working_directory: Path,
        *,
        dry_run_preview: bool = False,
    ) -> list[ActionRequest]:
        """Build and optionally preview the action plan before execution.

        Args:
            profile: The app profile responsible for parsing the task string.
            task: Natural-language task description.
            working_directory: Root directory for any generated artifacts.
            dry_run_preview: When True, print the plan to stdout for inspection
                             without executing anything. The plan is still returned.
        """
        if isinstance(task, TaskSpec):
            plan = profile.build_plan_from_task_spec(task, working_directory)
            preview_text = task.display_text
        else:
            normalized = self._normalize(task)
            plan = profile.build_plan(normalized, working_directory)
            preview_text = normalized

        if dry_run_preview:
            self._print_preview(profile.name, preview_text, plan)

        return plan

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(task: str) -> str:
        """Strip excess whitespace and normalize internal spacing."""
        return " ".join(task.split())

    @staticmethod
    def _print_preview(profile_name: str, task: str, plan: list[ActionRequest]) -> None:
        """Print a human-readable plan preview to stdout."""
        print(f"\n── Dry-run plan preview ─────────────────────────────────────────")
        print(f"  Profile : {profile_name}")
        print(f"  Task    : {task}")
        print(f"  Steps   : {len(plan)}")
        print()
        for i, action in enumerate(plan, start=1):
            strategies = ", ".join(action.allowed_strategies) if action.allowed_strategies else "(default)"
            checks = len(action.postconditions)
            destructive = " [DESTRUCTIVE]" if action.destructive else ""
            print(f"  {i:2}. [{action.action_type:12}] {action.name}{destructive}")
            print(f"        strategies: {strategies}")
            print(f"        postconditions: {checks}")
        print(f"─────────────────────────────────────────────────────────────────\n")
