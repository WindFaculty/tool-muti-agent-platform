from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.stt import SttService
from app.services.tts import TtsService

logger = get_logger("speech")


class SpeechService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.stt = SttService(settings)
        self.tts = TtsService(settings)

    def stt_health(self) -> dict[str, Any]:
        return self.stt.health()

    def tts_health(self) -> dict[str, Any]:
        return self.tts.health()

    def transcribe(self, audio_path: Path, language: str | None = None) -> dict[str, Any]:
        return self.stt.transcribe(audio_path, language)

    def transcribe_bytes(self, wav_bytes: bytes, language: str | None = None) -> dict[str, Any]:
        return self.stt.transcribe_bytes(wav_bytes, language)

    def synthesize(self, text: str, voice: str | None = None, cache: bool = True) -> dict[str, Any]:
        return self.tts.synthesize(text, voice, cache)

    def synthesize_sentences(self, text: str, voice: str | None = None, cache: bool = True) -> list[dict[str, Any]]:
        return self.tts.synthesize_sentences(text, voice, cache)

    def cleanup_audio_artifacts(self) -> dict[str, int]:
        removed = {
            "stt_temp": 0,
            "tts_temp": 0,
            "empty_audio": 0,
        }
        audio_dir = self._settings.audio_dir
        if audio_dir is None or not audio_dir.exists():
            return removed

        for path in audio_dir.iterdir():
            if not path.is_file():
                continue

            if path.name.startswith("stt_"):
                path.unlink(missing_ok=True)
                removed["stt_temp"] += 1
                continue

            if path.name.endswith(".tmp.wav"):
                path.unlink(missing_ok=True)
                removed["tts_temp"] += 1
                continue

            if path.suffix.lower() == ".wav" and path.stat().st_size == 0:
                path.unlink(missing_ok=True)
                removed["empty_audio"] += 1

        total_removed = sum(removed.values())
        if total_removed > 0:
            logger.info(
                "Removed %s stale audio artifact(s): stt_temp=%s tts_temp=%s empty_audio=%s",
                total_removed,
                removed["stt_temp"],
                removed["tts_temp"],
                removed["empty_audio"],
            )
        return removed


SttService = SttService
TtsService = TtsService
