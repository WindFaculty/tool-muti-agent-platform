from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult

LANGUAGE_SUFFIX = {
    "python": ".py",
    "powershell": ".ps1",
    "javascript": ".js",
}


class RunCodeInput(BaseModel):
    language: str | None = None
    code: str | None = None
    file_path: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_sec: int | None = Field(default=None, ge=1, le=300)


class RunCodeTool(BaseTool):
    name = "run_code"
    description = "Run source code from a file or inline text"
    input_model = RunCodeInput

    def execute(self, context: ToolContext, input_data: dict[str, Any]) -> ToolResult:
        if not input_data.get("code") and not input_data.get("file_path"):
            raise ValidationError("Either code or file_path is required")

        cleanup_path: Path | None = None
        script_path: Path
        if input_data.get("code"):
            language = (input_data.get("language") or "python").lower()
            suffix = LANGUAGE_SUFFIX.get(language)
            if not suffix:
                raise ValidationError(f"Unsupported language: {language}")
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=suffix,
                delete=False,
                dir=context.settings.resolve_path(Path("tmp")),
                encoding="utf-8",
            )
            tmp_file.write(input_data["code"])
            tmp_file.close()
            script_path = Path(tmp_file.name)
            cleanup_path = script_path
        else:
            script_path = Path(input_data["file_path"])
            if not script_path.is_absolute():
                script_path = context.workspace_root / script_path
            script_path = script_path.resolve(strict=False)

        try:
            command = self._build_command(script_path, input_data.get("language"), input_data["args"])
            result = context.sandbox.run(
                command,
                cwd=input_data.get("cwd"),
                timeout_sec=input_data.get("timeout_sec"),
                memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
            )
            return ToolResult(ok=result["exit_code"] == 0, data=result)
        finally:
            if cleanup_path and cleanup_path.exists():
                cleanup_path.unlink(missing_ok=True)

    @staticmethod
    def _build_command(script_path: Path, language: str | None, args: list[str]) -> list[str]:
        resolved_language = (language or "").lower()
        if not resolved_language:
            suffix = script_path.suffix.lower()
            if suffix == ".py":
                resolved_language = "python"
            elif suffix in {".ps1", ".psm1"}:
                resolved_language = "powershell"
            elif suffix == ".js":
                resolved_language = "javascript"

        if resolved_language == "python":
            return [sys.executable, str(script_path), *args]
        if resolved_language == "powershell":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path), *args]
        if resolved_language == "javascript":
            return ["node", str(script_path), *args]
        raise ValidationError(f"Unsupported language: {resolved_language or script_path.suffix}")

