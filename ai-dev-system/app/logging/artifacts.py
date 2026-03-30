from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ArtifactManager:
    """Manage timestamped run folders and evidence files."""

    root: Path
    run_id: str
    run_dir: Path
    screenshots_dir: Path
    started_at: str = ""

    @classmethod
    def create(cls, root: Path, profile_name: str) -> "ArtifactManager":
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{timestamp}-{profile_name}"
        run_dir = root / run_id
        screenshots_dir = run_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            root=root,
            run_id=run_id,
            run_dir=run_dir,
            screenshots_dir=screenshots_dir,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    def screenshot_path(self, label: str) -> Path:
        safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in label).strip("-") or "shot"
        return self.screenshots_dir / f"{safe_label}.png"

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.run_dir / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.run_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def write_summary(
        self,
        *,
        status: str,
        action_count: int,
        success_count: int,
        failure_count: int,
        elapsed_seconds: float,
    ) -> Path:
        """Write a human-readable summary.json to the run directory."""
        summary = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "action_count": action_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_count / action_count, 3) if action_count else 0.0,
        }
        return self.write_json("summary.json", summary)

