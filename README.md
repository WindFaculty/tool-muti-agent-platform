# Agent Platform

Optional operator and automation layer for the local desktop assistant project.

## Role in the new project
- `agent-platform` is not part of the MVP runtime critical path.
- The assistant should run with the Unity client, the assistant local backend, SQLite, and local AI runtimes only.
- This subproject may later host:
  - scripted QA flows
  - operator tooling
  - assistant-specific tool wrappers
  - dataset and prompt fixture helpers

## Current repo status
- The folder still contains an existing Python tool platform and some legacy integration assumptions from the previous project direction.
- Those modules are not the source of truth for task data, planning logic, speech orchestration, or avatar behavior in the new assistant product.
- The active product architecture is documented in the root `docs/` folder.

## Non-goals for this subproject
- Replacing the assistant local backend
- Owning the primary task database
- Embedding Unity avatar or UI logic
- Becoming a hidden dependency for offline startup

## Local documentation
- `docs/coding_rules.md`
- `docs/image3d_integration.md`
- `datasets/README.md`
