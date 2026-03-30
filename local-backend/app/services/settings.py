from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import Settings
from app.db.repository import SQLiteRepository


DEFAULT_SETTINGS: dict[str, Any] = {
    "voice": {
        "input_mode": "continuous",
        "tts_voice": "vi-VN-default",
        "speak_replies": True,
        "show_transcript_preview": True,
    },
    "model": {
        "provider": "hybrid",
        "name": "groq+gemini",
        "routing_mode": "auto",
        "fast_provider": "groq",
        "deep_provider": "gemini",
    },
    "window_mode": {
        "main_app_enabled": True,
        "mini_assistant_enabled": False,
    },
    "avatar": {
        "character": "default",
        "lip_sync_mode": "amplitude",
    },
    "reminder": {
        "speech_enabled": True,
        "lead_minutes": 15,
    },
    "startup": {
        "launch_backend": True,
        "launch_main_app": True,
    },
    "memory": {
        "auto_extract": True,
        "short_term_turn_limit": 12,
    },
}


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SettingsService:
    def __init__(self, repository: SQLiteRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def get(self) -> dict[str, Any]:
        persisted = self._repository.get_settings()
        defaults = deepcopy(DEFAULT_SETTINGS)
        defaults["voice"]["tts_voice"] = self._settings.default_tts_voice
        defaults["model"]["provider"] = self._settings.llm_provider
        defaults["model"]["name"] = self._settings.active_llm_model
        defaults["model"]["routing_mode"] = self._settings.routing_mode
        defaults["model"]["fast_provider"] = self._settings.fast_provider
        defaults["model"]["deep_provider"] = self._settings.deep_provider
        defaults["reminder"]["lead_minutes"] = self._settings.reminder_lead_minutes
        defaults["memory"]["short_term_turn_limit"] = self._settings.short_term_turn_limit
        merged = _merge(defaults, persisted)
        merged["model"]["provider"] = self._settings.llm_provider
        merged["model"]["name"] = self._settings.active_llm_model
        merged["model"]["routing_mode"] = self._settings.routing_mode
        merged["model"]["fast_provider"] = self._settings.fast_provider
        merged["model"]["deep_provider"] = self._settings.deep_provider
        return merged

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        merged = _merge(current, payload)
        for key, value in merged.items():
            self._repository.set_setting(key, value)
        return merged
