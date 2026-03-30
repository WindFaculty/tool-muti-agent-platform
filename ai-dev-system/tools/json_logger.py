from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data: Any) -> None:
        record = {"event": event, **data}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
