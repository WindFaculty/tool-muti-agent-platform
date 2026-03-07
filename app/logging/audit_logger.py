from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=True)
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")

    def health_check(self) -> bool:
        try:
            with self.log_path.open("a", encoding="utf-8"):
                return True
        except OSError:
            return False

