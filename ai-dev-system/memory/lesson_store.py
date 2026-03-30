from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agents.contracts import Lesson


class LessonStore:
    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, lesson: Lesson) -> None:
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(lesson), ensure_ascii=True) + "\n")
