from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_list_tools_returns_18(client: TestClient) -> None:
    response = client.get("/v1/tools", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["tools"]) == 18


def test_execute_and_get_execution(client: TestClient) -> None:
    execute_response = client.post(
        "/v1/tools/execute",
        headers=auth_headers("codex"),
        json={
            "tool_name": "list_files",
            "input": {
                "path": "agent-platform/config",
                "pattern": "*.yaml",
                "recursive": False,
                "limit": 20,
            },
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]
    assert execution_id

    get_response = client.get(
        f"/v1/executions/{execution_id}",
        headers=auth_headers("codex"),
    )
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["execution_id"] == execution_id
    assert payload["tool_name"] == "list_files"


def test_health(client: TestClient) -> None:
    response = client.get("/v1/health", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["db"] is True
    assert payload["audit_log"] is True

