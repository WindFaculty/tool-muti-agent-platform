# Runbook

Updated: 2026-03-26

Windows setup, startup, smoke validation, packaging, and troubleshooting for the current assistant runtime.

## Scope

Covered here:

- backend dependency setup
- runtime preflight
- backend startup
- optional packaged-client startup
- backend smoke validation
- release packaging
- common troubleshooting

Not fully covered here:

- Unity Editor visual validation
- target-machine microphone and speaker quality checks
- production-avatar sign-off
- external runtime installs that are not already available on the machine

## 1. Prerequisites

- Windows with PowerShell
- Python available as `python`
- repo checked out locally
- optional speech runtimes if you want non-degraded speech validation
- optional Groq or Gemini credentials if you want non-degraded LLM validation

Useful paths:

- `local-backend/`
- `unity-client/`
- `scripts/`
- `tasks/task-queue.md`
- `tasks/task-people.md`

## 2. Fresh-Machine Setup

From repo root:

```powershell
.\scripts\setup_windows.ps1
```

What it does:

- resolves the backend folder
- resolves the backend Python command
- installs backend requirements
- runs runtime preflight checks for current config

Expected result:

- exit code `0`

Current setup-script exit codes:

- `10`: backend Python command could not be resolved
- `11`: dependency install or dependency validation failed
- `12`: runtime preflight diagnostics failed

## 3. Runtime Configuration

The backend reads:

- `local-backend/.env`
- shell environment variables prefixed with `assistant_`

Common settings:

- `assistant_llm_provider`
- `assistant_routing_mode`
- `assistant_fast_provider`
- `assistant_deep_provider`
- `assistant_groq_api_key`
- `assistant_gemini_api_key`
- `assistant_stt_provider`
- `assistant_faster_whisper_model_path`
- `assistant_whisper_command`
- `assistant_whisper_model_path`
- `assistant_tts_provider`
- `assistant_piper_command`
- `assistant_piper_model_path`
- `assistant_chattts_compile`

Important current-state note:

- Backend-routed LLM providers are `hybrid`, `groq`, and `gemini`.
- Ollama-related settings are still used by preflight helpers and future planning, but not by the current routed assistant backend.

## 4. Startup

From repo root:

```powershell
.\scripts\run_all.ps1
```

Useful variants:

```powershell
.\scripts\run_all.ps1 -BackendPython python
.\scripts\run_all.ps1 -UnityExecutablePath "D:\Builds\TroLy.exe"
.\scripts\run_all.ps1 -ShutdownBackendOnExit
```

What it does:

- verifies backend Python dependencies
- runs runtime preflight checks
- verifies port `8096` is free
- starts `local-backend/run_local.py`
- waits for `http://127.0.0.1:8096/v1/health`
- optionally starts a packaged Unity client executable
- optionally shuts the backend down after validation

Current startup-script exit codes:

- `20`: backend Python command could not be resolved
- `21`: backend dependency preflight failed
- `22`: runtime preflight diagnostics failed
- `23`: backend port already in use
- `24`: backend process could not be started
- `25`: backend health never became reachable
- `26`: backend health reported `error`
- `27`: Unity client launch failed
- `28`: backend shutdown-after-validation failed

## 5. Health Check

Manual health query:

```powershell
Invoke-RestMethod http://127.0.0.1:8096/v1/health | ConvertTo-Json -Depth 6
```

Interpretation:

- `ready`: database and configured runtime groups are available
- `partial`: app is usable, but one or more runtime groups are degraded
- `error`: do not continue until the database or startup problem is fixed

Current implementation note:

- speech runtime health should reflect endpoint-style probe results, not only import or path checks
- if a speech endpoint is still callable through a fallback path, keep the endpoint usable but treat the health state as degraded rather than clean `ready`

## 6. Smoke Validation

After the backend is reachable:

```powershell
python .\scripts\smoke_backend.py
```

Useful variants:

```powershell
python .\scripts\smoke_backend.py --base-url http://127.0.0.1:8096
python .\scripts\smoke_backend.py --allow-health-status ready partial
python .\scripts\smoke_backend.py --timeout 20
```

The smoke script currently verifies:

- `/v1/health`
- task create, update, reschedule, and complete flows
- `/v1/events`
- `/v1/assistant/stream`
- available versus unavailable STT responses
- available versus unavailable TTS responses

Evidence split for current validation:

- repo regression evidence: automated backend or Unity test output
- P02 live UI evidence: Unity Editor Game view and packaged-client captures
- P03 speech evidence: target-machine STT or TTS runtime install and end-to-end voice validation

Treat smoke failure as blocking when:

- health never becomes reachable
- stream flow never reaches `assistant_final`
- task update events do not match mutation results
- STT or TTS behavior does not match health availability

## 7. Packaging

From repo root:

```powershell
.\scripts\package_release.ps1
```

Useful variants:

```powershell
.\scripts\package_release.ps1 -UnityBuildPath "D:\Builds\TroLyClient"
.\scripts\package_release.ps1 -OutputDir "D:\Releases\TroLy"
```

What it does:

- validates the output directory
- prepares a clean release folder
- copies backend files and helper scripts
- optionally copies a Unity build
- validates the packaged layout

Current packaging exit codes:

- `30`: output path or packaging input validation failed
- `31`: release folder preparation failed
- `32`: backend or script copy failed
- `33`: Unity client copy failed
- `34`: packaged release layout validation failed

## 8. Release Folder Validation

From the packaged release root:

```powershell
cd .\release
.\scripts\setup_windows.ps1
.\scripts\run_all.ps1
python .\scripts\smoke_backend.py
```

Use this when you want evidence that the packaged backend and scripts still work outside the repo checkout.

Historical note:

- Release-folder validation has already been recorded as completed work in `tasks/task-people.md`.
- You may still need to repeat it on a different target machine if runtime binaries, models, or permissions differ.

## 9. Troubleshooting

### Setup fails on Python dependencies

Run:

```powershell
python -m pip install -r local-backend\requirements.txt
```

Then confirm the Python path you are using:

```powershell
python -c "import sys; print(sys.executable)"
```

### Runtime preflight fails

Typical causes:

- invalid Piper executable path
- invalid Piper model path
- invalid whisper.cpp executable path
- invalid whisper.cpp model path
- missing Python modules for selected runtime
- missing API keys for the chosen LLM path

Fix the configured path or remove the broken override if degraded mode is acceptable.

### Health reports `partial`

Actions:

- inspect `recovery_actions`
- decide whether degraded mode is acceptable for the current test
- rerun startup and smoke after fixing the missing runtime if not acceptable
- for manual smoke, keep P02 live UI evidence separate from any remaining P03 speech blocker

### Health reports `error`

Actions:

- stop and inspect `/v1/health`
- fix the underlying startup or database issue
- rerun `.\scripts\run_all.ps1`

### ChatTTS validation varies by machine

Current repo state:

- backend tests and degraded-path code exist
- actual ChatTTS availability still depends on local Python and torch compatibility

Practical advice:

- use Piper for baseline validation if you only need a stable smoke path
- validate ChatTTS explicitly on the target machine when that runtime matters

### Backend never becomes reachable

Try manual backend start:

```powershell
cd .\local-backend
python run_local.py
```

Port check:

```powershell
Get-NetTCPConnection -LocalPort 8096 -ErrorAction SilentlyContinue
```

## 10. Evidence To Keep

When handing off or reporting status, keep:

- setup script exit code
- startup script exit code
- health JSON
- smoke summary JSON
- P02 checklist entries from `tasks/p02-manual-checklist.md` when the pass includes live UI or packaged-client evidence
- release path if packaging was used
- any runtime warnings or errors

## 11. Validation Rule

Do not mark runtime, packaging, or Unity behavior done from docs alone.
Use tests, script output, logs, or manual evidence.
