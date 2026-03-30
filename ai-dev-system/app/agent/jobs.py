from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BackgroundJob:
    job_key: str
    tool_name: str
    status_tool: str
    job_id: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "started"
    latest_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_key": self.job_key,
            "tool_name": self.tool_name,
            "status_tool": self.status_tool,
            "job_id": self.job_id,
            "params": self.params,
            "status": self.status,
            "latest_result": self.latest_result,
        }


class JobTracker:
    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}

    def start(self, *, job_key: str, tool_name: str, status_tool: str, job_id: str, params: dict[str, Any]) -> BackgroundJob:
        job = BackgroundJob(
            job_key=job_key,
            tool_name=tool_name,
            status_tool=status_tool,
            job_id=job_id,
            params=dict(params),
        )
        self._jobs[job_key] = job
        return job

    def get(self, job_key: str) -> BackgroundJob:
        if job_key not in self._jobs:
            raise KeyError(f"No background job is registered for key '{job_key}'.")
        return self._jobs[job_key]

    def update(self, job_key: str, *, status: str, result: dict[str, Any]) -> BackgroundJob:
        job = self.get(job_key)
        job.status = status
        job.latest_result = dict(result)
        return job

    def snapshot(self) -> dict[str, Any]:
        return {key: job.to_dict() for key, job in self._jobs.items()}
