# Tool Multi Agent Platform

Extracted AI-focused package from `WindFaculty/app_tro_ly`.

This repository intentionally keeps the parts of the source project that are directly related to AI runtime, orchestration, and automation:

- `ai/`: prompt, memory, and agent-facing context files
- `ai-dev-system/`: Windows GUI agent and Unity MCP automation tooling
- `local-backend/`: FastAPI backend for assistant orchestration, routing, speech adapters, memory, and task-safe AI actions
- `scripts/`: setup, startup, packaging, and backend smoke helpers
- `docs/`: runtime and architecture documents relevant to the AI stack
- `AGENTS.md`: repo-wide machine-facing operating rules copied from the source project

Excluded on purpose:

- `unity-client/`
- `release/`
- generated logs, caches, screenshots, databases, and local virtual environments
- unrelated Blender and asset-production tooling

## Quick Start

### Backend

```powershell
cd local-backend
python -m pip install -r requirements.txt
python run_local.py
```

### AI Dev System

```powershell
cd ai-dev-system
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe verify_connection.py
```

## Notes

- This export preserves folder names from the source repo to reduce churn and keep internal documentation accurate.
- The packaged scope is centered on AI runtime and automation, not the Unity client shell.
