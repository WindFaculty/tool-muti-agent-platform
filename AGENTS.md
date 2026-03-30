# AGENTS.md

Applies to the entire repository.

Machine-facing operating rules for Codex and similar agents.

## Repo Summary

- `local-backend/`: source of truth for API behavior, task logic, routing, memory, speech adapters, scheduler, and persistence
- `unity-client/`: source of truth for client UI, screen flow, overlays, audio playback, and avatar presentation wiring
- `scripts/`: source of truth for Windows setup, startup, packaging, and backend smoke automation
- `docs/`: maintained documentation; may include both current-state docs and target-state design docs
- `tasks/`: work tracking
- `agent-platform/`: optional adjacent subsystem, not part of the required assistant runtime

## Truth Sources

- Trust code over docs.
- Backend truth lives in:
  - `local-backend/app/api/routes.py`
  - `local-backend/app/services/`
  - `local-backend/app/models/`
  - `local-backend/app/core/`
- Unity UI truth lives in:
  - `unity-client/Assets/Resources/UI/MainUI.uxml`
  - `unity-client/Assets/Resources/UI/Shell/AppShell.uxml`
  - `unity-client/Assets/Resources/UI/Styles/*.uss`
  - `unity-client/Assets/Scripts/App/`
  - `unity-client/Assets/Scripts/Core/`
  - `unity-client/Assets/Scripts/Features/`
- Avatar integration truth lives in:
  - `unity-client/Assets/Scripts/Avatar/`
  - `unity-client/Assets/AvatarSystem/`
- Operations truth lives in:
  - `scripts/setup_windows.ps1`
  - `scripts/run_all.ps1`
  - `scripts/package_release.ps1`
  - `scripts/smoke_backend.py`

## Required Workflow

1. Analyze the request and identify the exact truth sources.
2. Plan the change before editing.
3. Execute only inside the confirmed scope.
4. Verify with tests, logs, script output, or concrete runtime evidence.
5. Do not claim done without evidence.

## No-Guessing Rules

- Do not invent features, routes, screens, runtime behavior, or architecture.
- If docs conflict with code, update docs to match code.
- If code is ambiguous, say what is uncertain and avoid stronger claims.
- Do not treat target-state design docs as implemented reality.
- Do not treat manual-only validation as already verified from terminal work.

## Documentation Labels

Use these distinctions consistently:

- `Current implementation`: behavior proven by code in this repo now
- `Planned work`: intended work not implemented yet
- `Optional subsystem`: present but not required for the assistant runtime
- `Manual validation required`: needs Unity Editor, a built client, external runtime binaries, credentials, or target-machine checks
- `Design target`: aspirational UI or architecture direction
- `Placeholder`: temporary UI, avatar, text, or runtime behavior

## Task File Rules

- Update `tasks/task-queue.md` when AI-executable repo work changes status, scope, blockers, or definition of done.
- Update `tasks/task-people.md` when a task requires a person, a target machine, Unity Editor interaction, external assets, credentials, or approvals.
- Update `tasks/done.md` when work is actually completed and there is verification or concrete evidence to justify the history entry.
- Keep queue files current-state focused.
- Keep `tasks/done.md` historical; add clarifying notes instead of rewriting history into current status.

## Safety Rules

- Do not overwrite or revert unrelated user changes.
- Do not change runtime code during a docs task unless a source comment is materially misleading.
- Do not present design-target docs as shipped features.
- Keep docs concise, specific, and grounded in files that exist.
