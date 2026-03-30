# Architecture As-Is

Updated: 2026-03-26

This document is the implementation snapshot for the repo as it exists now.

## Repo Topology

- `local-backend/` is the active assistant backend.
- `unity-client/` is the active assistant client.
- `agent-platform/` still exists, but it is optional and not required for the assistant runtime.
- `docs/` and `tasks/` now track the assistant rather than the older project direction.

## What Exists Today

### Backend

- FastAPI app with `/v1` routes
- SQLite persistence and repositories
- health endpoint with runtime diagnostics and recovery actions
- task CRUD, day or week or overdue or inbox or completed queries
- planner summaries derived from real task data
- shared assistant orchestration for REST and stream flows
- route logging, conversation history, rolling summaries, and long-term memory items
- reminder scheduler and event bus
- speech adapters for STT and TTS
- Windows setup, startup, packaging, and smoke helpers

### Unity client

- UI Toolkit shell loaded from `Assets/Resources/UI/MainUI.uxml`
- `AppShell.uxml` with Home, Schedule, and Settings content areas
- chat panel, subtitle overlay, reminder overlay, health display, and backend-backed settings
- REST and WebSocket clients for backend integration
- placeholder avatar-state handling, audio playback, and lip-sync fallback behavior

### Avatar groundwork

- `Assets/AvatarSystem/` contains runtime controllers, production-asset folders, validators, import tools, and prototype assets
- animation assets referenced by current avatar tasks are checked in
- the shell does not yet provide a fully finished production-avatar experience by itself

## What Is Still Partial

- The schedule center panel is still a placeholder text surface rather than a real calendar UI.
- The schedule-side panel is largely static placeholder content.
- The top-level chat panel contains some placeholder copy such as the fixed model badge.
- Production-avatar integration still depends on Unity scene setup and manual validation.
- A compact mini-assistant mode is not implemented.

## Verification Snapshot

- Backend tests were executed on 2026-03-26 in `local-backend/` and passed: `62 passed`.
- Unity test files exist, but Unity Editor or built-client execution was not re-run in this terminal session.

## Adjacent Or Optional Code

- `agent-platform/` may still be useful later, but it is not part of the required assistant runtime.
- Ollama-related settings and preflight checks exist, but the current backend does not route live assistant requests to Ollama.

## Practical Reading Order

If you need current implementation truth, read in this order:

1. `local-backend/app/api/routes.py`
2. `local-backend/app/container.py`
3. `local-backend/app/services/`
4. `unity-client/Assets/Scripts/Core/AssistantApp.cs`
5. `unity-client/Assets/Scripts/App/`
6. `unity-client/Assets/Scripts/Features/`
7. `unity-client/Assets/Resources/UI/`
