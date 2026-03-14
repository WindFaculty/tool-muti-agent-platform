from __future__ import annotations

from fastapi.testclient import TestClient


def test_workflow_loader_syncs_builtin_definitions(client: TestClient) -> None:
    workflows = client.app.state.container.workflow_loader.list_workflows()
    workflow_ids = {workflow.workflow_id for workflow in workflows}
    assert {
        "feature-development",
        "bug-fix",
        "refactor",
        "deployment",
        "research",
        "reconstruct-3d",
    }.issubset(workflow_ids)
