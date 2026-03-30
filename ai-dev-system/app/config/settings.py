from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    """Runtime settings for the Windows GUI agent."""

    dry_run: bool = False
    max_retries: int = 2
    max_actions_per_run: int = 25
    require_foreground: bool = True
    require_destructive_confirmation: bool = True
    action_delay_seconds: float = 0.15
    screenshot_confidence: float = 0.9
    emergency_stop_hotkey: str = "ctrl+alt+shift+q"
    default_window_timeout_seconds: float = 15.0
    verify_timeout_seconds: float = 5.0
    self_heal_enabled: bool = True
    vision_llm_enabled: bool = False
    vision_llm_timeout_seconds: float = 10.0
    max_heal_steps_per_action: int = 1
    layout_normalize_enabled: bool = True
    artifact_root: Path = Path(__file__).resolve().parents[2] / "logs" / "gui-agent"

    @classmethod
    def default(cls) -> "Settings":
        """Return a settings object with deterministic defaults."""
        return cls()
