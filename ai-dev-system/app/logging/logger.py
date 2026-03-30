from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.json_logger import JsonLogger


class GuiAgentLogger:
    """Small wrapper around the shared JSONL logger."""

    def __init__(self, path: Path) -> None:
        self._logger = JsonLogger(path)

    def log(self, event: str, **data: Any) -> None:
        self._logger.log(event, **data)
