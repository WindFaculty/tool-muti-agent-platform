from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class DependencyAnalyzerInput(BaseModel):
    path: str = "."


class DependencyAnalyzerTool(BaseTool):
    name = "dependency_analyzer"
    description = "Analyze dependencies from common project manifests"
    input_model = DependencyAnalyzerInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        base = Path(input_data["path"])
        if not base.is_absolute():
            base = context.workspace_root / base
        base = base.resolve(strict=False)

        dependencies = {
            "python": self._parse_requirements(base / "requirements.txt"),
            "node": self._parse_package_json(base / "package.json"),
            "maven": self._parse_pom(base / "pom.xml"),
        }
        summary = {key: len(value) for key, value in dependencies.items()}
        return ToolResult(ok=True, data={"path": str(base), "summary": summary, "dependencies": dependencies})

    @staticmethod
    def _parse_requirements(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        lines = file_path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    @staticmethod
    def _parse_package_json(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        deps = payload.get("dependencies", {})
        dev_deps = payload.get("devDependencies", {})
        return [f"{name}:{version}" for name, version in {**deps, **dev_deps}.items()]

    @staticmethod
    def _parse_pom(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}")[0].strip("{")
        prefix = f"{{{namespace}}}" if namespace else ""
        dependencies = []
        for dep in root.findall(f".//{prefix}dependency"):
            group = dep.findtext(f"{prefix}groupId", default="")
            artifact = dep.findtext(f"{prefix}artifactId", default="")
            version = dep.findtext(f"{prefix}version", default="")
            if group or artifact:
                dependencies.append(f"{group}:{artifact}:{version}")
        return dependencies

