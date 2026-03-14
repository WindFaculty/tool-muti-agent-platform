from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.llm.base import BaseLLMProvider
from app.llm.models import LLMGenerateContext


class MockProvider(BaseLLMProvider):
    def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        context: LLMGenerateContext,
    ) -> BaseModel:
        agent_name = context.agent_name
        task_title = str(context.metadata.get("task_title", "task"))
        task_slug = task_title.lower().replace(" ", "-")

        payload: dict[str, Any] = {
            "status": "success",
            "summary": f"{agent_name} completed work for {task_title}.",
            "findings": [],
            "next_steps": [],
            "tool_calls": [],
            "artifacts": [],
            "metadata": {"provider": "mock"},
        }

        if response_model.__name__ == "PlannerResult":
            payload.update(
                {
                    "plan": [
                        f"Inspect context for {task_title}.",
                        "Design the implementation approach.",
                        "Prepare workspace outputs.",
                        "Validate with tests and review.",
                    ],
                    "requires_architecture": True,
                }
            )
        elif response_model.__name__ == "ArchitectResult":
            payload.update(
                {
                    "modules": ["api", "orchestrator", "storage"],
                    "apis": ["/v1/tasks", "/v1/runs"],
                    "risks": ["Mock provider uses deterministic outputs."],
                }
            )
        elif response_model.__name__ == "CoderResult":
            payload.update(
                {
                    "implementation_notes": [
                        "Generate workspace artifacts first.",
                        "Preserve repository compatibility.",
                    ],
                    "files_to_create": [f"{task_slug}.md"],
                    "artifacts": [
                        {
                            "name": "implementation",
                            "kind": "markdown",
                            "content": f"# Implementation\n\nPrepared mock implementation for {task_title}.\n",
                        }
                    ],
                }
            )
        elif response_model.__name__ == "TestResult":
            payload.update(
                {
                    "passed": True,
                    "test_commands": ["pytest -q"],
                    "failures": [],
                    "artifacts": [
                        {
                            "name": "test-report",
                            "kind": "markdown",
                            "content": "# Test Report\n\nMock provider reports passing validation.\n",
                        }
                    ],
                }
            )
        elif response_model.__name__ == "DebuggerResult":
            payload.update(
                {
                    "root_cause": "Mock failure reproduction path.",
                    "proposed_fixes": ["Adjust failing step output.", "Rerun tests."],
                    "remaining_risks": [],
                }
            )
        elif response_model.__name__ == "ReviewResult":
            payload.update(
                {
                    "approved": True,
                    "findings": [],
                    "artifacts": [
                        {
                            "name": "review",
                            "kind": "markdown",
                            "content": "# Review\n\nApproved by mock reviewer.\n",
                        }
                    ],
                }
            )
        elif response_model.__name__ == "DevOpsResult":
            payload.update(
                {
                    "deployment_steps": ["docker build .", "Run local smoke test."],
                    "docker_commands": ["docker build . -t local/dev-os"],
                }
            )

        return response_model.model_validate(payload)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            length = float(len(text))
            tokens = float(len(text.split()))
            checksum = float(sum(ord(ch) for ch in text[:64]) % 997)
            embeddings.append([length, tokens, checksum])
        return embeddings
