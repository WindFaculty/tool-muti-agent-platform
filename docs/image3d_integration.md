# Assistant Integration Boundary

Updated: 2026-03-13

This file supersedes the old Image3D direction note during the project pivot. The filename is kept temporarily, but the active product scope is now the local desktop assistant.

## Current role of `agent-platform`
- `agent-platform` is optional for the assistant project.
- The MVP runtime path should be:
  - Unity client
  - assistant local backend
  - SQLite
  - Ollama
  - whisper.cpp
  - Piper
- The assistant must still work when `agent-platform` is not running.

## Core repo boundary
- The Unity client is the main end-user surface.
- The future assistant local backend owns task data, planner logic, conversation history, speech orchestration, and reminders.
- `agent-platform` may later provide optional automation, scripted QA flows, or operator tooling around the backend.

## If `agent-platform` is used later
Add dedicated wrappers for assistant-specific endpoints instead of overloading legacy integrations.

Candidate assistant-facing endpoints:
- `GET /v1/health`
- `GET /v1/tasks/today`
- `GET /v1/tasks/week`
- `GET /v1/tasks/overdue`
- `POST /v1/tasks`
- `PUT /v1/tasks/{id}`
- `POST /v1/tasks/{id}/complete`
- `POST /v1/tasks/{id}/reschedule`
- `POST /v1/chat`
- `POST /v1/speech/stt`
- `POST /v1/speech/tts`
- `GET /v1/settings`
- `PUT /v1/settings`

## Important guardrails
- Do not move the assistant source of truth into `agent-platform`.
- Do not let optional orchestration code absorb task or reminder business rules.
- Keep the assistant backend contract separate from any legacy tool wrappers that may still exist in this subproject.

## Transition note
- Legacy Image3D-related code may still exist in `agent-platform`, but it is not part of the active product scope for the assistant MVP.
