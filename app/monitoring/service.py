from __future__ import annotations

from app.storage.repositories import ToolingRepository


class MonitoringService:
    def __init__(self, repository: ToolingRepository) -> None:
        self.repository = repository

    def summary(self) -> dict:
        return self.repository.get_monitoring_summary()
