from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_mcp_tools_list(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        headers=auth_headers(),
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "result" in payload
    assert len(payload["result"]["tools"]) == 18


def test_mcp_tools_call_dry_run(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        headers=auth_headers(),
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/call",
            "params": {
                "name": "read_file",
                "arguments": {"path": "agent-platform/config/tools.yaml"},
                "dry_run": True,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"] == "dry_run"
    assert payload["result"]["execution_id"] is None

