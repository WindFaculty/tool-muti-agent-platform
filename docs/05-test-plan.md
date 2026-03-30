# Test Plan - Current Validation Strategy

Updated: 2026-03-26

## Automated Validation

### Backend

Run from `local-backend/`:

```powershell
pytest -q
```

Current evidence:

- Verified on 2026-03-26
- Result: `62 passed`

Coverage present in repo includes:

- task APIs
- chat APIs
- assistant streaming APIs
- scheduler and health behavior
- STT and TTS services
- smoke script behavior
- Windows script preflight checks
- prompt-context and token-compaction related tests

### Unity

Unity test files exist under `unity-client/Assets/Tests/` for:

- EditMode:
  - view-model stores
  - health mapping and normalization
  - settings serialization
- PlayMode:
  - `AssistantApp`
  - `UiDocumentLoader`
  - `AppRouter`
  - `AppShellController`
  - screen controllers
  - subtitle presenter
  - reminder presenter
  - avatar bridge and avatar state machine

Manual note:

- Presence of these files is verified.
- Their pass status was not re-run from this terminal session.

## Smoke Validation

### Recommended Windows flow

From repo root:

```powershell
.\scripts\setup_windows.ps1
.\scripts\run_all.ps1
python .\scripts\smoke_backend.py
```

The smoke script currently exercises:

- `/v1/health`
- task create, update, reschedule, and complete flows
- `/v1/events`
- `/v1/assistant/stream`
- available and unavailable STT behavior
- available and unavailable TTS behavior

Evidence should stay split between:

- repo regression evidence
- P02 live UI or packaged-client evidence
- P03 target-machine speech evidence

## Manual Validation Required

These still require human-run verification:

- Unity Editor visual behavior
- built client behavior on a target machine
- microphone capture and playback quality
- speech runtime installs and model paths
- production-avatar integration in a real scene

## Regression Priorities

Prioritize failures in these areas:

- health and degraded-mode reporting
- assistant stream completion
- validated task mutation behavior
- reminder event delivery
- subtitle and talking-state sync
- settings load or save behavior
- packaged release startup

## Acceptance Rules

- Do not claim UI or runtime behavior is verified unless there is test, script, log, or manual evidence.
- Treat machine-local speech runtime validation as separate from repo-code validation.
- Treat design-target UI documents as out of scope for validation unless the code changed to implement them.
