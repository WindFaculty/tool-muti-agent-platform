from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class RunnerInput(BaseModel):
    framework: str = "auto"
    path: str = "."
    extra_args: list[str] = Field(default_factory=list)
    timeout_sec: int = Field(default=120, ge=1, le=1800)


class TestRunnerTool(BaseTool):
    name = "test_runner"
    description = "Run project test suites"
    input_model = RunnerInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        project_path = Path(input_data["path"])
        if not project_path.is_absolute():
            project_path = context.workspace_root / project_path
        project_path = project_path.resolve(strict=False)

        framework = input_data["framework"].lower()
        if framework == "auto":
            framework = self._detect_framework(project_path)

        command = self._build_command(framework, input_data["extra_args"])
        result = context.sandbox.run(
            command,
            cwd=str(project_path),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(
            ok=result["exit_code"] == 0,
            data={"framework": framework, "path": str(project_path), **result},
        )

    @staticmethod
    def _detect_framework(project_path: Path) -> str:
        if (project_path / "pom.xml").exists():
            return "maven"
        if (project_path / "package.json").exists():
            return "npm"
        return "pytest"

    @staticmethod
    def _build_command(framework: str, extra_args: list[str]) -> list[str]:
        if framework == "maven":
            return ["mvn", "test", *extra_args]
        if framework == "npm":
            return ["npm", "test", "--", *extra_args]
        return ["pytest", *extra_args]
