# Architecture - Current Assistant Runtime

Updated: 2026-03-26

This document describes the current implementation in the repo. It does not treat target-state design notes as already shipped.

## High-Level Topology

```text
Unity client
  -> REST and WebSocket clients
     -> FastAPI backend
        -> AssistantOrchestrator
           -> ActionValidator
           -> RouterService
           -> PlanningService
           -> FastResponseService
           -> MemoryService
           -> TaskService / PlannerService
           -> SpeechService
        -> SchedulerService
        -> SQLiteRepository
```

## Unity Client

### Entry and composition

- `Assets/Scripts/Core/AssistantApp.cs` is the runtime coordinator.
- `Assets/Scripts/App/AppCompositionRoot.cs` creates the runtime camera, UI document, audio playback, subtitle presenter, reminder presenter, and placeholder avatar-state runtime pieces.
- `Assets/Scripts/Core/UiDocumentLoader.cs` loads `Assets/Resources/UI/MainUI.uxml`.

### UI structure

- `Assets/Resources/UI/MainUI.uxml` only wraps `Shell/AppShell.uxml`.
- `Assets/Resources/UI/Shell/AppShell.uxml` composes the visible shell from:
  - top bar
  - left sidebar
  - center-stage screen templates
  - right-side chat or schedule-side panel
  - subtitle overlay
  - reminder overlay
- Runtime styles live in `Assets/Resources/UI/Styles/*.uss`.
- `Assets/Resources/UI/MainStyle.uss` is deprecated and not the active style source.

### Screen flow and controllers

- `AppRouter` switches among:
  - `Today`
  - `Week`
  - `Inbox`
  - `Completed`
  - `Settings`
- `HomeScreenController` renders the Home view task summary and quick-add input.
- `ScheduleScreenController` renders week, inbox, and completed text into the current placeholder calendar area.
- `SettingsScreenController` binds backend-backed toggles and save or reload actions.
- `ChatPanelController` binds the text input, send button, mic button, and transcript rendering.
- `AppShellController` renders health and stage status in the shell header or sidebar areas.

### Network integration

- `LocalApiClient` handles REST requests for health, tasks, settings, STT, TTS, and compatibility chat.
- `EventsClient` consumes `WS /v1/events`.
- `AssistantStreamClient` consumes `WS /v1/assistant/stream`.
- `AssistantApp` prefers the streaming path and falls back to compatibility chat when the stream is unavailable.

### Client-side state

- `TaskViewModelStore` keeps today, week, inbox, and completed snapshots.
- `ChatViewModelStore` keeps transcript, assistant draft, transcript preview, and routing diagnostics.
- `SettingsViewModelStore` keeps the backend-backed settings snapshot currently used by the client.

### Avatar and presentation

- `AvatarStateMachine` drives placeholder state visuals.
- `AudioPlaybackController` plus `SubtitlePresenter` manage spoken reply playback and subtitle visibility.
- `LipSyncController` applies amplitude-based lip sync to a fallback face mesh or transform.
- `Assets/AvatarSystem/` contains the production-avatar groundwork:
  - `AvatarConversationBridge`
  - `AvatarAnimatorBridge`
  - `AvatarRootController`
  - `AvatarLipSyncDriver`
  - production-asset and validator scaffolding
- The assistant shell does not instantiate a production avatar by itself. It integrates with `AvatarConversationBridge` only if one exists in the active Unity scene.

## Backend

### Application composition

- `local-backend/app/main.py` creates the FastAPI app and starts scheduler lifecycle management.
- `local-backend/app/container.py` wires:
  - `SQLiteRepository`
  - `EventBus`
  - `SettingsService`
  - `LlmService`
  - `SpeechService`
  - `TaskService`
  - `PlannerService`
  - `ActionValidator`
  - `RouterService`
  - `MemoryService`
  - `PlanningService`
  - `FastResponseService`
  - `AssistantOrchestrator`
  - `ConversationService`
  - `SchedulerService`

### API surface

- Routes live in `local-backend/app/api/routes.py`.
- REST endpoints cover health, tasks, chat, speech, settings, and cached speech files.
- WebSockets cover event streaming and assistant turn streaming.

### Assistant pipeline

- `AssistantOrchestrator` is the shared pipeline behind `POST /v1/chat` and `WS /v1/assistant/stream`.
- `ActionValidator` performs deterministic intent analysis and approved task actions before any write.
- `RouterService` chooses `groq_fast`, `gemini_deep`, or `hybrid_plan_then_groq`.
- `PlanningService` generates deeper structured planning output.
- `FastResponseService` turns validated context into short final phrasing.
- `MemoryService` manages recent-message context, rolling summaries, and conservative long-term memory extraction.

### Task and planning logic

- `TaskService` owns task CRUD, occurrence generation, conflict detection, overdue queries, inbox queries, completed queries, and reminder sync.
- `PlannerService` derives daily, weekly, overdue, urgency, and free-slot summaries from task data.
- `SchedulerService` polls reminders and publishes due events.

### Speech and runtime health

- `SpeechService` delegates to `SttService` and `TtsService`.
- STT providers:
  - `faster_whisper`
  - `whisper_cpp`
- TTS providers:
  - `piper`
  - `chattts`
- Health payloads report `ready`, `partial`, or `error` based on database and runtime availability.
- Recovery actions are generated from actual configured runtime state.

## Persistence

SQLite stores:

- tasks
- reminders
- conversations
- messages
- assistant sessions
- conversation summaries
- memory items
- route logs
- app settings
- session state

## Ownership Boundaries

- The backend is the source of truth for task mutations, summaries, routing, memory, settings persistence, and reminder logic.
- The Unity client is the source of truth for presentation, screen flow, overlays, audio playback, and user interaction wiring.
- `agent-platform/` is optional and must not be treated as a hidden runtime dependency.

## Known Gaps

- The current client still contains placeholder UI content in several panels.
- The default LLM route is not fully local.
- Production-avatar runtime behavior still needs scene-level integration and manual validation.
- Unity client verification still requires Editor or built-client runs outside terminal-only inspection.
