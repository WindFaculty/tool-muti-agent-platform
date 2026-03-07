# Agent Tooling Platform (V1)

Python-based tooling platform for multi-agent coding workflows (Codex, Claude, Gemini) with:

- REST API (`/v1/*`)
- MCP-compatible JSON-RPC endpoint (`/mcp`)
- Tool registry + metadata
- Allowlist-based security checks
- Sandbox execution (Windows-focused)
- SQLite execution/audit persistence
- JSONL audit log

## Implemented Tool Set (18)

1. `read_file`
2. `write_file`
3. `edit_file`
4. `list_files`
5. `web_search`
6. `fetch_page`
7. `scraper`
8. `run_code`
9. `test_runner`
10. `linter`
11. `formatter`
12. `code_search`
13. `dependency_analyzer`
14. `shell_exec`
15. `git_commit`
16. `install_dependency`
17. `run_server`
18. `docker_build`

## Project Layout

```text
agent-platform/
  app/
    api/
    core/
    registry/
    tools/
    storage/
    logging/
  config/
    tools.yaml
    policies.yaml
  tests/
```

## Setup

```powershell
cd d:\Spring_2026\PRJ301\agent-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment Variables

```powershell
$env:AGENT_PLATFORM_SERVICE_TOKENS_CSV="dev-token"
$env:AGENT_PLATFORM_WORKSPACE_ROOT="d:\Spring_2026\PRJ301"
$env:AGENT_PLATFORM_SERPAPI_API_KEY="<your_serpapi_key>"
```

Optional overrides:

- `AGENT_PLATFORM_DATABASE_PATH`
- `AGENT_PLATFORM_AUDIT_LOG_PATH`
- `AGENT_PLATFORM_POLICY_CONFIG_PATH`
- `AGENT_PLATFORM_TOOL_CONFIG_PATH`
- `AGENT_PLATFORM_REQUESTS_PER_MINUTE`
- `AGENT_PLATFORM_MAX_CONCURRENT_PER_AGENT`

## Run Service

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8088 --reload
```

## API

Headers required for protected endpoints:

- `X-Service-Token`
- `X-Agent-Id`
- `X-Request-Id` (UUID)

### `GET /v1/tools`

List available tools and input schemas.

### `POST /v1/tools/execute`

```json
{
  "tool_name": "read_file",
  "input": { "path": "agent-platform/config/tools.yaml" },
  "request_id": "optional-uuid-must-match-header",
  "dry_run": false
}
```

### `GET /v1/executions/{execution_id}`

Get persisted execution details.

### `GET /v1/health`

Service + DB + audit health status.

### `POST /mcp`

JSON-RPC methods:

- `tools/list`
- `tools/call`

## Testing

```powershell
pytest
```

## QA

```powershell
flake8
isort --check-only .
```

