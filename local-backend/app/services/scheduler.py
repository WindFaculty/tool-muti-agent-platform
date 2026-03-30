from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.core.events import EventBus
from app.core.logging import get_logger
from app.core.time import iso_datetime, now_local, parse_datetime
from app.db.repository import SQLiteRepository
from app.services.speech import SpeechService

logger = get_logger("scheduler")


class SchedulerService:
    def __init__(
        self,
        repository: SQLiteRepository,
        event_bus: EventBus,
        settings: Settings,
        speech_service: SpeechService,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._settings = settings
        self._speech_service = speech_service

    async def tick(self) -> int:
        now = now_local()
        due = self._repository.list_due_reminders(iso_datetime(now))
        for reminder in due:
            self._repository.mark_reminder_delivered(reminder["id"], iso_datetime(now))
            scheduled_for = reminder["start_at"] or reminder["due_at"]
            minutes_until = 0
            scheduled_dt = parse_datetime(scheduled_for)
            if scheduled_dt is not None:
                minutes_until = int((scheduled_dt - now).total_seconds() // 60)
            reminder_text = f"Nhac viec: {reminder['title']} trong {minutes_until} phut."
            payload = {
                "type": "reminder_due",
                "task_id": reminder["task_id"],
                "title": reminder["title"],
                "scheduled_for": scheduled_for,
                "minutes_until": minutes_until,
                "speech_text": reminder_text,
            }
            reminder_settings = self._repository.get_settings().get("reminder", {})
            voice_settings = self._repository.get_settings().get("voice", {})
            speech_enabled = bool(reminder_settings.get("speech_enabled", True))
            if speech_enabled:
                try:
                    speech = self._speech_service.synthesize(
                        reminder_text,
                        voice=voice_settings.get("tts_voice"),
                    )
                    payload["audio_url"] = speech["audio_url"]
                    payload["audio_duration_ms"] = speech["duration_ms"]
                except Exception as exc:
                    payload["speech_fallback_reason"] = str(exc)
                    logger.warning("Reminder speech fallback triggered for %s: %s", reminder["task_id"], exc)
            await self._event_bus.publish(
                payload
            )
        if due:
            logger.info("Delivered %s due reminder(s)", len(due))
        return len(due)

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("Scheduler tick failed; continuing on next cycle")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._settings.reminder_poll_seconds)
            except asyncio.TimeoutError:
                continue
