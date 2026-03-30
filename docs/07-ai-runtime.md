# AI Runtime - Current Backend Behavior

Updated: 2026-03-26

This document describes the implemented AI stack in the repo today.

## Core Principles

- The backend owns task state, session state, reminder state, and persistence.
- LLMs help phrase or plan, but they do not write directly to SQLite.
- Every task mutation goes through validated backend actions.
- The runtime should degrade cleanly when LLM, STT, or TTS providers are unavailable.

## Implemented Turn Flow

1. The client sends a turn through `POST /v1/chat` or `WS /v1/assistant/stream`.
2. `AssistantOrchestrator` creates or resumes the conversation and assistant session.
3. `ActionValidator` classifies the request into a validated intent.
4. `RouterService` selects a route based on routing mode, complexity, notes length, planning signals, voice mode, and provider availability.
5. The backend responds with one of three paths:
   - `groq_fast`
   - `gemini_deep`
   - `hybrid_plan_then_groq`
6. If a task action is required, `TaskService` applies it before the response is finalized.
7. `MemoryService` refreshes rolling summary and optionally stores conservative long-term memory items.
8. The backend records route logs and emits stream or event updates.

## Current Route Types

- `groq_fast`
  - short replies and low-latency voice turns
- `gemini_deep`
  - deeper planning and longer-context requests
- `hybrid_plan_then_groq`
  - deeper plan first, then shorter delivery phrasing

## Task Safety Contract

The assistant is task-aware, not a general autonomous agent.

Current validated intents include:

- day summary lookup
- week summary lookup
- overdue lookup
- urgency lookup
- free-time lookup
- create task
- complete task
- reschedule task
- change task priority
- planning from current task context

Important consequences:

- Model output is not trusted as a direct database command.
- Backend validation and task services decide what actually changes.

## Deterministic Planning Layer

`PlannerService` already provides deterministic summaries from real task data:

- daily summary
- weekly summary
- overdue summary
- urgency summary
- free slots

These can answer a turn directly or feed deeper planning prompts.

## Memory Model

### Short-term memory

- recent conversation messages
- rolling conversation summary stored in SQLite

### Long-term memory

- optional auto-extraction from explicit user preference, routine, project, or goal statements
- simple token-overlap retrieval against stored memory items

Persistence tables used by the AI layer include:

- conversations
- messages
- assistant sessions
- conversation summaries
- memory items
- route logs

## Streaming Behavior

`WS /v1/assistant/stream` supports:

- text turns
- partial and final transcripts from voice input
- assistant state updates
- chunked assistant text output
- sentence-level TTS readiness events
- final route and latency metadata

This is the preferred assistant path for the Unity client.

## Current Runtime Providers

### LLM

- routed providers in current backend code:
  - `groq`
  - `gemini`
- current top-level backend setting values:
  - `hybrid`
  - `groq`
  - `gemini`

Important note:

- Ollama settings still exist in config and Windows preflight helpers, but Ollama is not an active routed provider in the current backend implementation.

### Speech

- STT:
  - `faster_whisper`
  - `whisper_cpp`
- TTS:
  - `piper`
  - `chattts`

## Current Limitations

- The default LLM path is not fully offline.
- Intent parsing is still keyword and regex driven.
- Memory extraction is intentionally narrow and conservative.
- Speech reliability depends on local machine setup.
- Unity-side behavior still needs manual validation outside terminal-only inspection.

## Source Files

- `local-backend/app/services/assistant_orchestrator.py`
- `local-backend/app/services/action_validator.py`
- `local-backend/app/services/router.py`
- `local-backend/app/services/planning_engine.py`
- `local-backend/app/services/fast_response.py`
- `local-backend/app/services/memory.py`
- `local-backend/app/services/tasks.py`
- `local-backend/app/services/planner.py`
- `local-backend/app/services/speech.py`
- `local-backend/app/api/routes.py`
