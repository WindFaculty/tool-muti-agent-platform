from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_devos_project_task_run_flow(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        headers=auth_headers(),
        json={"project_id": "demo", "name": "Demo Project"},
    )
    assert project_response.status_code == 200
    assert project_response.json()["project_id"] == "demo"

    task_response = client.post(
        "/v1/tasks",
        headers=auth_headers(),
        json={
            "project_id": "demo",
            "title": "Build task runner",
            "description_md": "Create an automated task execution flow.",
            "requirements_md": "Need planning, coding, testing, and review.",
            "expected_output_md": "A completed run with artifacts.",
            "priority": "high",
            "workflow_id": "feature-development",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["task_id"]

    workflow_response = client.get("/v1/workflows", headers=auth_headers())
    assert workflow_response.status_code == 200
    assert len(workflow_response.json()["workflows"]) >= 5

    knowledge_response = client.post(
        "/v1/knowledge/index",
        headers=auth_headers(),
        json={"project_id": "demo"},
    )
    assert knowledge_response.status_code == 200
    assert knowledge_response.json()["indexed"] >= 4

    run_response = client.post(
        f"/v1/tasks/{task_id}/run",
        headers=auth_headers(),
        json={"auto_resume": True},
    )
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["run"]["status"] == "completed"
    assert len(payload["steps"]) >= 5
    assert len(payload["messages"]) >= 5
    assert payload["evaluation"]["score"] > 0

    run_id = payload["run"]["run_id"]
    get_run_response = client.get(f"/v1/runs/{run_id}", headers=auth_headers())
    assert get_run_response.status_code == 200
    assert get_run_response.json()["run"]["run_id"] == run_id

    messages_response = client.get(f"/v1/runs/{run_id}/messages", headers=auth_headers())
    assert messages_response.status_code == 200
    assert len(messages_response.json()["messages"]) >= 5

    monitoring_response = client.get("/v1/monitoring/summary", headers=auth_headers())
    assert monitoring_response.status_code == 200
    assert monitoring_response.json()["runs"] >= 1

    evaluation_response = client.get(f"/v1/evaluations/{run_id}", headers=auth_headers())
    assert evaluation_response.status_code == 200
    assert evaluation_response.json()["run_id"] == run_id
