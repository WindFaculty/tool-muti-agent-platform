from __future__ import annotations

import json
import shutil
import subprocess
import sys
import socket
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ASSISTANT_COMMON = REPO_ROOT / "scripts" / "assistant_common.ps1"


def _powershell_executable() -> str:
    for candidate in ("powershell", "pwsh"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    pytest.skip("PowerShell is not available in this environment")


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_powershell_executable(), "-NoProfile", "-Command", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_powershell_file(script_path: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_powershell_executable(), "-NoProfile", "-File", str(script_path), *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _process_exists(process_id: int) -> bool:
    result = _run_powershell(
        f"Get-Process -Id {process_id} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"
    )
    return result.returncode == 0 and str(process_id) in result.stdout


def _create_script_root(tmp_path: Path, script_names: list[str], include_backend: bool = False) -> Path:
    root = tmp_path / "script-root"
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True)

    for script_name in script_names:
        shutil.copy2(REPO_ROOT / "scripts" / script_name, scripts_dir / script_name)

    if include_backend:
        backend_dir = root / "local-backend"
        (backend_dir / "app").mkdir(parents=True)
        (backend_dir / "requirements.txt").write_text("fastapi\nuvicorn\nwebsockets\npydantic-settings\nhttpx\n", encoding="utf-8")
        (backend_dir / "run_local.py").write_text("print('stub backend')\n", encoding="utf-8")

    return root


def test_runtime_diagnostics_flags_directory_paths_for_runtime_files(tmp_path: Path) -> None:
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (backend_dir / ".env").write_text(
        "\n".join(
            [
                "assistant_llm_provider=groq",
                "assistant_groq_api_key=test-key",
                "assistant_tts_provider=piper",
                f"assistant_piper_command={runtime_dir}",
                f"assistant_piper_model_path={runtime_dir}",
                "assistant_stt_provider=whisper_cpp",
                f"assistant_whisper_command={runtime_dir}",
                f"assistant_whisper_model_path={runtime_dir}",
            ]
        ),
        encoding="utf-8",
    )

    command = (
        f". '{ASSISTANT_COMMON}'; "
        f"$diag = Get-RuntimeDiagnostics -BackendDirectory '{backend_dir}' -PythonCommand '{sys.executable}'; "
        "$diag | ConvertTo-Json -Depth 8"
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert "assistant_piper_command is configured but not found as an executable file" in payload["Errors"][0]
    assert any("assistant_piper_model_path must be a file, but got a directory" in item for item in payload["Errors"])
    assert any("assistant_whisper_command is configured but not found as an executable file" in item for item in payload["Errors"])
    assert any("assistant_whisper_model_path must be a file, but got a directory" in item for item in payload["Errors"])


def test_assert_release_layout_requires_core_backend_files(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    (release_dir / "backend" / "app" / "api").mkdir(parents=True)
    (release_dir / "scripts").mkdir(parents=True)

    required_files = [
        release_dir / "backend" / "requirements.txt",
        release_dir / "backend" / "run_local.py",
        release_dir / "backend" / "app" / "main.py",
        release_dir / "scripts" / "run_all.ps1",
        release_dir / "scripts" / "setup_windows.ps1",
        release_dir / "scripts" / "assistant_common.ps1",
        release_dir / "scripts" / "smoke_backend.py",
        release_dir / "scripts" / "fake_piper.py",
        release_dir / "scripts" / "fake_piper.cmd",
        release_dir / "scripts" / "fake_piper_model.onnx",
    ]

    for path in required_files:
        path.write_text("stub", encoding="utf-8")

    command = (
        f". '{ASSISTANT_COMMON}'; "
        f"Assert-ReleaseLayout -OutputDir '{release_dir}'"
    )
    result = _run_powershell(command)

    assert result.returncode != 0
    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    assert "backend\\app\\api\\routes.py" in combined


def test_stop_process_tree_safe_stops_child_processes(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    parent_script = tmp_path / "spawn_child.ps1"
    parent_script.write_text(
        "\n".join(
            [
                "param([string]$ChildPidFile)",
                "$child = Start-Process -FilePath powershell -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 120') -PassThru -WindowStyle Hidden",
                "Set-Content -Path $ChildPidFile -Value $child.Id -Encoding ASCII",
                "Start-Sleep -Seconds 120",
            ]
        ),
        encoding="utf-8",
    )

    parent = subprocess.Popen(
        [_powershell_executable(), "-NoProfile", "-File", str(parent_script), "-ChildPidFile", str(child_pid_file)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    child_pid = None
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            if child_pid_file.exists():
                try:
                    child_pid = int(child_pid_file.read_text(encoding="ascii").strip())
                    break
                except PermissionError:
                    time.sleep(0.1)
            time.sleep(0.2)

        assert child_pid is not None, "Child process PID file was not created"
        assert _process_exists(parent.pid)
        assert _process_exists(child_pid)

        stop_result = _run_powershell(
            f". '{ASSISTANT_COMMON}'; $p = Get-Process -Id {parent.pid} -ErrorAction Stop; Stop-ProcessTreeSafe -Process $p"
        )
        assert stop_result.returncode == 0, stop_result.stderr or stop_result.stdout

        deadline = time.time() + 10
        while time.time() < deadline:
            if not _process_exists(parent.pid) and not _process_exists(child_pid):
                break
            time.sleep(0.2)

        assert not _process_exists(parent.pid)
        assert not _process_exists(child_pid)
    finally:
        if parent.poll() is None:
            parent.kill()
        if child_pid is not None and _process_exists(child_pid):
            _run_powershell(f"Stop-Process -Id {child_pid} -Force -ErrorAction SilentlyContinue")


def test_setup_windows_reports_stable_exit_code_for_missing_python(tmp_path: Path) -> None:
    root = _create_script_root(tmp_path, ["assistant_common.ps1", "setup_windows.ps1"], include_backend=True)

    result = _run_powershell_file(
        root / "scripts" / "setup_windows.ps1",
        "-BackendPython",
        "python-command-that-does-not-exist",
        cwd=root,
    )

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    assert result.returncode == 10, combined
    assert "Backend Python command was not found" in combined


def test_package_release_reports_stable_exit_code_for_unsafe_output_dir(tmp_path: Path) -> None:
    root = _create_script_root(tmp_path, ["assistant_common.ps1", "package_release.ps1"])

    result = _run_powershell_file(
        root / "scripts" / "package_release.ps1",
        "-OutputDir",
        str(root),
        cwd=root,
    )

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    assert result.returncode == 30, combined
    assert "Refusing to use the repo root as a release output directory" in combined


def test_run_all_reports_stable_exit_code_when_backend_port_is_busy(tmp_path: Path) -> None:
    root = _create_script_root(tmp_path, ["assistant_common.ps1", "run_all.ps1"], include_backend=True)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 8096))
    listener.listen(1)

    try:
        result = _run_powershell_file(
            root / "scripts" / "run_all.ps1",
            "-BackendPython",
            sys.executable,
            "-ShutdownBackendOnExit",
            cwd=root,
        )
    finally:
        listener.close()

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    assert result.returncode == 23, combined
    assert "Port 8096 is already in use" in combined
