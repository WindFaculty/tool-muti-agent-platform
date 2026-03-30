# AI Dev System

Current implementation: `ai-dev-system/` now contains two automation tracks:

- Unity MCP automation for bounded Unity Editor tasks.
- A desktop-automation agent under `app/` that currently runs in production on Windows, including a hybrid `unity-editor` profile that routes Unity work through MCP first and falls back to GUI-only editor macros when needed.

This folder is intentionally separate from `local-backend/` and `unity-client/`. It extends the repo with automation tooling without changing the shipped assistant runtime.

## Folder Layout

- `app/`: Windows GUI agent package, CLI, hybrid Unity control plane, profiles, logging, safety guards, vision fallback, and tests.
- `agents/`, `planner/`, `executor/`, `memory/`, `tools/`, `workflows/`, `unity-interface/`: existing Unity MCP workflow scaffold.
- `logs/`: run artifacts for both systems. GUI-agent runs are stored under `logs/gui-agent/`.
- `tasks/`: Unity MCP demo and smoke task definitions.

## Windows GUI Agent

### Architecture overview

The GUI agent follows a bounded observe -> decide -> act -> verify -> recover loop:

1. `automation/windows_driver.py` observes top-level windows, active window state, and launch readiness.
2. `agent/planner.py` asks the selected app profile for a narrow, deterministic action plan.
3. `agent/controller.py` executes one action at a time, captures screenshots, verifies outcomes, and switches strategy only when verification fails.
4. `agent/verifier.py` checks control existence, control text, window text, file existence, and screenshot/template evidence.
5. `agent/recovery.py`, `agent/healing.py`, and `vision/locator.py` move through the configured fallback order and stop cleanly when uncertainty remains.
6. `logging/` writes timestamped JSONL logs, screenshots, control-tree dumps, and failure reports.

### Selector strategy

Current implementation:

- Prefer `pywinauto` first.
- Use `uia` first for modern apps such as current Notepad and Calculator.
- Use `win32` when a legacy or classic dialog is more reliable. The Notepad Save As dialog is handled this way.
- Build selectors from observed window title, class name, control type, automation ID, and child ordering.
- Use image fallback only when a structured selector is unavailable for that specific action.
- Use coordinate fallback only when a profile explicitly provides coordinates for that action.

Uncertainty handling:

- If a selector cannot be resolved, the action is logged as a failed attempt.
- The controller tries the next allowed strategy in order.
- If no verified strategy remains, the run stops and writes `failure-report.json`.

### Fallback order

The GUI agent uses this exact priority order:

1. Structured UI automation via `pywinauto`
2. Self-healing via whitelisted UI recovery steps
3. Optional Vision LLM location
4. Vision-assisted fallback via `PyAutoGUI`
5. Coordinate fallback when the profile explicitly allows it

The controller prunes fallbacks that are not actually configured for the current action, so a missing heal hint, vision provider, template, or coordinate profile does not create fake retries.

### Safety model

Current implementation:

- Interactive desktop required for mutating runs.
- Foreground window verification before input.
- Emergency stop hotkey registration via `ctrl+alt+shift+q`.
- Deterministic action delay.
- Max action cap and bounded fallback chains per action.
- Destructive actions require explicit confirmation wiring.
- Fail closed behavior: if the target window cannot be confirmed, healing is ambiguous, or vision evidence is not good enough, the run stops instead of clicking blind.

Manual validation required:

- Cross-machine hotkey registration behavior.
- Additional profiles beyond Notepad and Calculator.
- Any coordinate fallbacks you add later.

### Installation

From `ai-dev-system/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Dependencies added for the GUI agent:

- `pywinauto`
- `pyautogui`
- `pillow`
- `opencv-python`
- `keyboard`
- `psutil`
- `PyYAML`
- `pytest`

### CLI

Run from `ai-dev-system/`:

```powershell
.\.venv\Scripts\python.exe -m app.main list-windows
.\.venv\Scripts\python.exe -m app.main inspect --app notepad
.\.venv\Scripts\python.exe -m app.main inspect --app calculator
.\.venv\Scripts\python.exe -m app.main inspect --app unity-editor
.\\.venv\\Scripts\\python.exe -m app.main list-capabilities --profile unity-editor
.\.venv\Scripts\python.exe -m app.main run --profile notepad --task "type hello and save"
.\.venv\Scripts\python.exe -m app.main run --profile calculator --task "compute 125*4"
.\.venv\Scripts\python.exe -m app.main --dry-run run --profile unity-editor --task "assert layout ready"
```

Optional flags:

```powershell
.\.venv\Scripts\python.exe -m app.main --dry-run run --profile notepad --task "type hello and save"
.\.venv\Scripts\python.exe -m app.main run --profile notepad --task "type hello and save" --confirm-destructive
.\.venv\Scripts\python.exe -m app.main --dry-run run --profile unity-editor --task-file .\tasks\unity-editor-open-scene.yaml
```

### Unity Editor profile

Current implementation:

- `unity-editor` is now a hybrid profile. It opens a per-run Unity MCP runtime, builds a live capability matrix, prefers MCP-backed capabilities, and only falls back to GUI macros for editor-surface tasks such as layout assertions, window opening, console snapshots, and control-tree capture.
- The controller now understands optional `heal_hints`, `layout_policy`, and action-level `execution` metadata for self-healing, layout normalization, and background MCP jobs.
- The profile accepts both narrow natural-language aliases and structured `actions[]` task specs. Natural-language input is parsed into capability-backed actions before execution; unsupported prompts fail closed instead of generating blind click sequences.
- Preflight is hybrid. It checks MCP connectivity, capability availability, project match, and tool-group visibility for every run, and it only enforces pinned-layout GUI checks when the requested task actually needs GUI fallback. When the current layout is wrong and MCP is available, it now attempts `editor.layout.normalize` before failing.
- `inspect --app unity-editor` writes the usual control trees plus per-surface screenshots based on the pinned layout map.
- `list-capabilities --profile unity-editor` prints the live capability matrix for the current project and machine, including `supported_via_mcp`, `supported_via_gui_fallback`, `manual_validation_required`, and `unsupported` statuses. The matrix now also surfaces `shader.manage`, `texture.manage`, `vfx.manage`, `animator.graph.manage`, `editor.layout.normalize`, and planned-but-unsupported graph capabilities such as `timeline.manage`.
- Successful or failed Unity runs write `unity-summary.json` in the run directory with preflight data, capability coverage, per-action backend selection, and task-level verification results.

Example task file:

```yaml
profile: unity-editor
actions:
  - capability: scene.manage
    params:
      action: load
      path: Assets/Scenes/SampleScene.unity
    heal_hints:
      focus_surface: project
  - capability: tests.run
    params:
      mode: EditMode
    execution:
      mode: background_job_start
      job_key: editmode-tests
  - capability: editor.layout.assert
    backend: gui
    allow_fallback: false
layout_policy:
  required: default-6000
  normalize_if_needed: true
  strict_after_normalize: true
verify:
  - kind: active_scene_path_is
    params:
      path: Assets/Scenes/SampleScene.unity
confirm_destructive: false
requires_layout: default-6000
```

### Artifacts and logs

Every run writes a timestamped folder under:

```text
logs/gui-agent/<timestamp>-<profile>/
```

Current implementation writes:

- `run.jsonl`
- `screenshots/*.png`
- `control-tree-uia.json` and `control-tree-win32.json` for `inspect`
- `failure-report.json` for failed runs
- `healing-trace.json` when self-healing runs
- `vision-locator.json` when Vision LLM fallback runs
- `unity-summary.json` for `unity-editor` runs

### Adding a new app profile

1. Create a new file under `app/profiles/`.
2. Subclass `BaseProfile`.
3. Set the executable, top-level window selector, and any region or coordinate hints.
4. Build a narrow task parser that returns `ActionRequest` objects.
5. Prefer automation IDs and control types before visible text.
6. Add a real integration test under `app/tests/`.
7. Update `app/main.py` to register the profile.

Keep the task parser narrow. If the profile cannot understand the task safely, raise a `ValueError` and stop rather than guessing.

### Troubleshooting

- If `list-windows` works but a mutating run fails immediately, check that the Windows desktop is interactive and unlocked.
- If the wrong window gets input focus, inspect the latest `failure-report.json` and `run.jsonl` under `logs/gui-agent/`.
- If a structured selector fails on a Windows update, re-run `inspect --app <name>` and refresh the selector from the new control tree.
- If `unity-editor` reports a layout or modal block, restore the repo's `default-6000` layout and close the blocking dialog before retrying.
- If Vision LLM fallback is not configured, the controller skips that stage and continues to template matching or coordinate fallback if they are explicitly allowed.
- If image matching is needed, prefer a small region and a stable template. Full-screen matching is intentionally the least preferred vision path.
- If the emergency stop hotkey cannot register, the GUI agent will refuse to send input.

## Unity MCP Workflow

Current implementation: the original Unity automation scaffold remains intact.

### What it does

- Verifies a live MCP connection to a running Unity Editor
- Plans a bounded Unity task into structured execution steps
- Executes Unity changes through MCP tool calls
- Reads Unity console output for verification and debugging context
- Saves structured run logs and lessons learned
- Ships reusable demo and smoke-check workflows

### Run

```powershell
.\.venv\Scripts\python.exe verify_connection.py
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe -m pytest tests -q
```

Example smoke-check task:

```powershell
.\.venv\Scripts\python.exe run_demo.py --task tasks\demo_scene_smoke_check.json
```

### Existing Unity notes

- This workflow is deterministic by design.
- Prompt templates and agent-role scaffolding are still present for future expansion.
- The Unity workflow and the Windows GUI agent share the same `logs/` root, but they do not share runtime code paths.
