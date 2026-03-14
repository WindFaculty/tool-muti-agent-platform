from __future__ import annotations

from pathlib import Path
from typing import Any


class WorkspaceService:
    def prepare_run_workspace(self, project_root: Path, run_id: str) -> Path:
        workspace = project_root / "workspace" / "runs" / run_id
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        return workspace

    def write_artifacts(
        self,
        run_workspace: Path,
        agent_id: str,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        written: list[dict[str, Any]] = []
        for artifact in artifacts:
            file_name = str(artifact.get("name", "artifact")).replace(" ", "-")
            kind = str(artifact.get("kind", "markdown"))
            suffix = ".json" if kind == "json" else ".md"
            relative_path = artifact.get("relative_path") or f"artifacts/{agent_id}-{file_name}{suffix}"
            target = (run_workspace / relative_path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            content = artifact.get("content", "")
            if kind == "json" and not isinstance(content, str):
                import json

                target.write_text(json.dumps(content, indent=2), encoding="utf-8")
            else:
                target.write_text(str(content), encoding="utf-8")
            written.append({**artifact, "path": str(target)})
        return written
