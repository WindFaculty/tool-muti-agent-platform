from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_missing_auth_headers_returns_401(client: TestClient) -> None:
    response = client.get("/v1/tools")
    assert response.status_code == 401


def test_path_traversal_is_blocked(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        headers=auth_headers(),
        json={
            "tool_name": "read_file",
            "input": {"path": "..\\..\\Windows\\System32\\drivers\\etc\\hosts"},
        },
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "PERMISSION_DENIED"


def test_dangerous_command_is_blocked(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/execute",
        headers=auth_headers(),
        json={
            "tool_name": "shell_exec",
            "input": {"command": "rm -rf /"},
        },
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "PERMISSION_DENIED"

