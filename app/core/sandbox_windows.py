from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

try:  # pragma: no cover - only available on Windows
    import win32api
    import win32con
    import win32job
except ImportError:  # pragma: no cover
    win32api = None  # type: ignore
    win32con = None  # type: ignore
    win32job = None  # type: ignore


class SandboxRunner:
    def __init__(self, default_timeout_sec: int, max_output_bytes: int) -> None:
        self.default_timeout_sec = default_timeout_sec
        self.max_output_bytes = max_output_bytes

    def run(
        self,
        command: list[str] | str,
        *,
        cwd: str | None = None,
        timeout_sec: int | None = None,
        env: dict[str, str] | None = None,
        memory_limit_mb: int | None = None,
    ) -> dict[str, Any]:
        timeout = timeout_sec or self.default_timeout_sec
        started = time.monotonic()
        process, job_handle = self._spawn(command, cwd, env, memory_limit_mb)

        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(process.pid)
            stdout, stderr = process.communicate()
            exit_code = -1

        duration_ms = int((time.monotonic() - started) * 1000)
        if job_handle is not None and win32api is not None:
            try:
                win32api.CloseHandle(job_handle)
            except Exception:
                pass

        return {
            "command": self._display_command(command),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout": self._truncate(stdout),
            "stderr": self._truncate(stderr),
        }

    def start_background(
        self,
        command: list[str] | str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = subprocess.Popen(
            command,
            cwd=str(Path(cwd).resolve()) if cwd else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=isinstance(command, str),
            creationflags=creation_flags,
        )
        return {"pid": process.pid, "command": self._display_command(command)}

    def _spawn(
        self,
        command: list[str] | str,
        cwd: str | None,
        env: dict[str, str] | None,
        memory_limit_mb: int | None,
    ) -> tuple[subprocess.Popen[str], Any]:
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = subprocess.Popen(
            command,
            cwd=str(Path(cwd).resolve()) if cwd else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=isinstance(command, str),
            creationflags=creation_flags,
        )
        job_handle = self._assign_job(process.pid, memory_limit_mb)
        return process, job_handle

    @staticmethod
    def _display_command(command: list[str] | str) -> str:
        if isinstance(command, list):
            return " ".join(command)
        return command

    def _truncate(self, text: str | None) -> str:
        if not text:
            return ""
        data = text.encode("utf-8", errors="replace")
        if len(data) <= self.max_output_bytes:
            return text
        return data[: self.max_output_bytes].decode("utf-8", errors="ignore")

    def _kill_tree(self, pid: int) -> None:
        if psutil is None:  # pragma: no cover
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            return

        try:
            parent = psutil.Process(pid)
        except psutil.Error:
            return

        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.Error:
                continue
        try:
            parent.kill()
        except psutil.Error:
            pass

    def _assign_job(self, pid: int, memory_limit_mb: int | None) -> Any:
        if os.name != "nt" or win32job is None or win32api is None or win32con is None:
            return None
        try:
            job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(
                job,
                win32job.JobObjectExtendedLimitInformation,
            )
            flags = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if memory_limit_mb:
                flags |= win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
                info["ProcessMemoryLimit"] = int(memory_limit_mb) * 1024 * 1024
            info["BasicLimitInformation"]["LimitFlags"] = flags
            win32job.SetInformationJobObject(
                job,
                win32job.JobObjectExtendedLimitInformation,
                info,
            )
            process_handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, pid)
            win32job.AssignProcessToJobObject(job, process_handle)
            win32api.CloseHandle(process_handle)
            return job
        except Exception:
            return None

