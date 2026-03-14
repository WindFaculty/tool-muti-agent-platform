# Global Coding Rules

1. Preserve boundaries between the Unity client, the assistant local backend, and the optional `agent-platform` layer.
2. Keep task logic, planner logic, reminder logic, and conversation state in the local backend. Unity should not become the business-rule owner.
3. Keep Ollama, whisper.cpp, and Piper behind backend adapters with explicit health checks and actionable error messages.
4. Prefer typed API contracts and schema-backed payloads over implicit string parsing between components.
5. Keep persistence changes explicit. Task, reminder, conversation, and settings changes must be reflected in repositories, migrations, and docs together.
6. Fail soft on optional runtimes. Missing STT, TTS, or LLM runtimes should degrade features cleanly instead of crashing the whole app.
7. Write or update tests for the affected flow: task CRUD, today/week aggregation, chat action routing, reminder scheduling, voice I/O, or avatar state mapping.
8. Keep `docs/` and `tasks/` aligned with the real repo state, especially while the project is transitioning from the previous product direction.
