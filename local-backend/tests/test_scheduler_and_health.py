from __future__ import annotations

import asyncio
from datetime import timedelta
import wave
from pathlib import Path

from app.core.time import iso_date, iso_datetime, now_local


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)


def test_scheduler_emits_due_event(client) -> None:
    start_at = now_local().replace(second=0)  # reminder is immediately due because lead time is 15m
    end_at = start_at.replace(microsecond=0) + timedelta(minutes=30)
    response = client.post(
        "/v1/tasks",
        json={
            "title": "Nhap standup",
            "status": "planned",
            "priority": "high",
            "scheduled_date": iso_date(start_at.date()),
            "start_at": iso_datetime(start_at),
            "end_at": iso_datetime(end_at),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert response.status_code == 200
    delivered = asyncio.run(client.app.state.container.scheduler_service.tick())
    assert delivered >= 1


def test_scheduler_reminder_event_includes_audio_when_speech_succeeds(client) -> None:
    container = client.app.state.container
    container.repository.set_setting("reminder", {"speech_enabled": True})
    container.repository.set_setting("voice", {"tts_voice": "demo-voice"})
    captured: list[dict[str, object]] = []

    async def capture(payload: dict[str, object]) -> None:
        captured.append(payload)

    container.event_bus.publish = capture  # type: ignore[method-assign]
    container.speech_service.synthesize = lambda text, voice=None, cache=True: {
        "audio_path": container.settings.audio_dir / "reminder.wav",
        "audio_url": "/v1/speech/cache/reminder.wav",
        "duration_ms": 321,
        "cached": False,
    }

    start_at = now_local().replace(second=0, microsecond=0)
    end_at = start_at + timedelta(minutes=30)
    response = client.post(
        "/v1/tasks",
        json={
            "title": "Hop nhac reminder",
            "status": "planned",
            "priority": "high",
            "scheduled_date": iso_date(start_at.date()),
            "start_at": iso_datetime(start_at),
            "end_at": iso_datetime(end_at),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert response.status_code == 200

    delivered = asyncio.run(container.scheduler_service.tick())

    assert delivered == 1
    reminder_event = next(item for item in captured if item["type"] == "reminder_due")
    assert reminder_event["audio_url"] == "/v1/speech/cache/reminder.wav"
    assert reminder_event["audio_duration_ms"] == 321
    assert "speech_fallback_reason" not in reminder_event


def test_scheduler_reminder_event_keeps_text_when_speech_fails(client) -> None:
    container = client.app.state.container
    container.repository.set_setting("reminder", {"speech_enabled": True})
    captured: list[dict[str, object]] = []

    async def capture(payload: dict[str, object]) -> None:
        captured.append(payload)

    container.event_bus.publish = capture  # type: ignore[method-assign]

    def fail_synthesize(text: str, voice: str | None = None, cache: bool = True):
        raise RuntimeError("tts reminder offline")

    container.speech_service.synthesize = fail_synthesize

    start_at = now_local().replace(second=0, microsecond=0)
    end_at = start_at + timedelta(minutes=30)
    response = client.post(
        "/v1/tasks",
        json={
            "title": "Fallback reminder",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(start_at.date()),
            "start_at": iso_datetime(start_at),
            "end_at": iso_datetime(end_at),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert response.status_code == 200

    delivered = asyncio.run(container.scheduler_service.tick())

    assert delivered == 1
    reminder_event = next(item for item in captured if item["type"] == "reminder_due")
    assert reminder_event["title"] == "Fallback reminder"
    assert "Nhac viec:" in reminder_event["speech_text"]
    assert reminder_event["speech_fallback_reason"] == "tts reminder offline"
    assert "audio_url" not in reminder_event


def test_tts_endpoint_can_be_stubbed_for_smoke(client) -> None:
    audio_path = client.app.state.container.settings.audio_dir / "stub.wav"
    _write_wav(audio_path)

    def fake_synthesize(text: str, voice: str | None = None, cache: bool = True):
        return {
            "audio_path": audio_path,
            "audio_url": f"/v1/speech/cache/{audio_path.name}",
            "duration_ms": 100,
            "cached": False,
        }

    client.app.state.container.speech_service.synthesize = fake_synthesize
    response = client.post("/v1/speech/tts", json={"text": "Xin chao", "voice": "stub", "cache": True})
    assert response.status_code == 200
    assert response.json()["audio_url"].endswith("stub.wav")


def test_backend_startup_cleans_stale_audio_artifacts(settings) -> None:
    settings.ensure_directories()
    stale_stt = settings.audio_dir / "stt_old.wav"
    stale_tts_temp = settings.audio_dir / "reply.tts123.tmp.wav"
    empty_wav = settings.audio_dir / "empty.wav"
    healthy_wav = settings.audio_dir / "keep.wav"
    stale_stt.write_bytes(b"stale-stt")
    stale_tts_temp.write_bytes(b"stale-tts-temp")
    empty_wav.write_bytes(b"")
    _write_wav(healthy_wav)

    from app.main import create_app

    app = create_app(settings)
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        cleanup = test_client.app.state.audio_cleanup
        assert cleanup == {"stt_temp": 1, "tts_temp": 1, "empty_audio": 1}

    assert not stale_stt.exists()
    assert not stale_tts_temp.exists()
    assert not empty_wav.exists()
    assert healthy_wav.exists()


def test_settings_update_roundtrip(client) -> None:
    update = client.put(
        "/v1/settings",
        json={
            "voice": {"speak_replies": False},
            "window_mode": {"mini_assistant_enabled": False},
        },
    )
    assert update.status_code == 200
    current = client.get("/v1/settings")
    assert current.status_code == 200
    payload = current.json()
    assert payload["voice"]["speak_replies"] is False


def test_settings_partial_updates_preserve_other_groups(client) -> None:
    defaults = client.get("/v1/settings")
    assert defaults.status_code == 200
    default_payload = defaults.json()

    first = client.put(
        "/v1/settings",
        json={
            "startup": {"launch_backend": False},
            "reminder": {"lead_minutes": 30},
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["startup"]["launch_backend"] is False
    assert first_payload["startup"]["launch_main_app"] is True
    assert first_payload["reminder"]["lead_minutes"] == 30
    assert first_payload["voice"]["speak_replies"] == default_payload["voice"]["speak_replies"]
    assert first_payload["model"]["name"] == default_payload["model"]["name"]

    second = client.put("/v1/settings", json={"reminder": {"speech_enabled": False}})
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["startup"]["launch_backend"] is False
    assert second_payload["startup"]["launch_main_app"] is True
    assert second_payload["reminder"]["lead_minutes"] == 30
    assert second_payload["reminder"]["speech_enabled"] is False
    assert second_payload["voice"]["tts_voice"] == default_payload["voice"]["tts_voice"]


def test_stt_endpoint_returns_503_when_runtime_is_missing(client) -> None:
    response = client.post(
        "/v1/speech/stt?language=vi",
        files={"audio": ("speech.wav", b"stub-wav", "audio/wav")},
    )

    assert response.status_code == 503
    assert "whisper.cpp runtime is not configured" in response.json()["detail"]


def test_stt_endpoint_cleans_temp_audio_after_success(client) -> None:
    observed = {"path": None}

    def fake_transcribe(audio_path: Path, language: str | None = None):
        observed["path"] = audio_path
        assert audio_path.exists()
        return {"text": "xin chao", "language": language or "vi", "confidence": 1.0}

    client.app.state.container.speech_service.transcribe = fake_transcribe
    response = client.post(
        "/v1/speech/stt?language=vi",
        files={"audio": ("speech.wav", b"stub-wav", "audio/wav")},
    )

    assert response.status_code == 200
    assert observed["path"] is not None
    assert not observed["path"].exists()


def test_stt_endpoint_cleans_temp_audio_after_runtime_failure(client) -> None:
    observed = {"path": None}

    def fail_transcribe(audio_path: Path, language: str | None = None):
        observed["path"] = audio_path
        assert audio_path.exists()
        raise RuntimeError("stt crashed after temp write")

    client.app.state.container.speech_service.transcribe = fail_transcribe
    response = client.post(
        "/v1/speech/stt?language=vi",
        files={"audio": ("speech.wav", b"stub-wav", "audio/wav")},
    )

    assert response.status_code == 503
    assert "stt crashed after temp write" in response.json()["detail"]
    assert observed["path"] is not None
    assert not observed["path"].exists()


def test_tts_endpoint_returns_503_when_runtime_is_missing(client) -> None:
    response = client.post("/v1/speech/tts", json={"text": "Xin chao", "cache": True})

    assert response.status_code == 503
    assert "Piper runtime is not configured" in response.json()["detail"]


def test_tts_endpoint_returns_503_when_runtime_raises_unexpected_error(client) -> None:
    def boom(text: str, voice: str | None = None, cache: bool = True):
        raise ValueError("chattts load mismatch")

    client.app.state.container.speech_service.synthesize = boom

    response = client.post("/v1/speech/tts", json={"text": "Xin chao", "cache": True})

    assert response.status_code == 503
    assert "chattts load mismatch" in response.json()["detail"]


def test_reschedule_replaces_pending_reminder(client) -> None:
    container = client.app.state.container
    start_at = now_local().replace(second=0, microsecond=0) + timedelta(minutes=20)
    end_at = start_at + timedelta(minutes=30)
    create = client.post(
        "/v1/tasks",
        json={
            "title": "Demo reminder",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(start_at.date()),
            "start_at": iso_datetime(start_at),
            "end_at": iso_datetime(end_at),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    original_due_at = start_at - timedelta(minutes=14)
    original_due = container.repository.list_due_reminders(iso_datetime(original_due_at))
    assert [item["task_id"] for item in original_due] == [task_id]

    rescheduled_start = start_at + timedelta(days=1)
    rescheduled_end = end_at + timedelta(days=1)
    reschedule = client.post(
        f"/v1/tasks/{task_id}/reschedule",
        json={
            "scheduled_date": iso_date(rescheduled_start.date()),
            "start_at": iso_datetime(rescheduled_start),
            "end_at": iso_datetime(rescheduled_end),
        },
    )
    assert reschedule.status_code == 200

    stale_due = container.repository.list_due_reminders(iso_datetime(original_due_at))
    assert stale_due == []

    rescheduled_due_at = rescheduled_start - timedelta(minutes=14)
    refreshed_due = container.repository.list_due_reminders(iso_datetime(rescheduled_due_at))
    assert [item["task_id"] for item in refreshed_due] == [task_id]


def test_complete_task_clears_pending_reminders(client) -> None:
    container = client.app.state.container
    start_at = now_local().replace(second=0, microsecond=0) + timedelta(minutes=20)
    end_at = start_at + timedelta(minutes=30)
    create = client.post(
        "/v1/tasks",
        json={
            "title": "Complete reminder cleanup",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(start_at.date()),
            "start_at": iso_datetime(start_at),
            "end_at": iso_datetime(end_at),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    complete = client.post(f"/v1/tasks/{task_id}/complete", json={})
    assert complete.status_code == 200

    due_after_completion = container.repository.list_due_reminders(iso_datetime(start_at + timedelta(days=1)))
    assert due_after_completion == []


def test_scheduler_run_recovers_after_tick_failure(client) -> None:
    scheduler = client.app.state.container.scheduler_service
    scheduler._settings.reminder_poll_seconds = 0
    stop_event = asyncio.Event()
    calls = {"count": 0}

    async def flaky_tick() -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        stop_event.set()
        return 0

    scheduler.tick = flaky_tick  # type: ignore[method-assign]
    asyncio.run(scheduler.run(stop_event))
    assert calls["count"] >= 2
