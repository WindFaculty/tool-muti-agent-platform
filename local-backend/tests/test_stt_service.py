from __future__ import annotations

from pathlib import Path
from app.core.config import Settings
from app.services.stt import SttService


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "app.db",
        audio_dir=tmp_path / "data" / "audio",
        cache_dir=tmp_path / "data" / "cache",
        log_dir=tmp_path / "data" / "logs",
        reminder_poll_seconds=1,
        **overrides,
    )


def test_whisper_cpp_health_requires_command_and_model_file(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        stt_provider="whisper_cpp",
        whisper_command=str(tmp_path / "whisper-cli.exe"),
        whisper_model_path=str(tmp_path / "models"),
    )
    settings.ensure_directories()
    Path(settings.whisper_command).write_text("stub", encoding="utf-8")
    Path(settings.whisper_model_path).mkdir(parents=True)
    service = SttService(settings)

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "whisper.cpp"
    assert payload["reason"] == "model_path_not_configured_or_not_found"
    assert "model_path_not_configured_or_not_found" in payload["issues"]


def test_whisper_cpp_transcribe_raises_when_model_path_is_missing(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        stt_provider="whisper_cpp",
        whisper_command=str(tmp_path / "whisper-cli.exe"),
        whisper_model_path=str(tmp_path / "missing.bin"),
    )
    settings.ensure_directories()
    Path(settings.whisper_command).write_text("stub", encoding="utf-8")
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"stub")
    service = SttService(settings)

    try:
        service.transcribe(audio_path)
    except RuntimeError as exc:
        assert "whisper.cpp model path is not configured" in str(exc)
    else:
        raise AssertionError("Expected missing whisper.cpp model path to raise RuntimeError")


def test_faster_whisper_health_reports_fallback_endpoint_when_primary_probe_fails(tmp_path: Path) -> None:
    settings = _settings(tmp_path, stt_provider="faster_whisper")
    settings.ensure_directories()
    service = SttService(settings)
    service._ensure_faster_whisper_model = lambda: (_ for _ in ()).throw(RuntimeError("missing cublas64_12.dll"))  # type: ignore[method-assign]
    service._whisper_cpp_health = lambda probe_endpoint=True: {  # type: ignore[method-assign]
        "available": True,
        "provider": "whisper.cpp",
        "effective_provider": "whisper.cpp",
    }

    payload = service.health()

    assert payload["available"] is True
    assert payload["provider"] == "faster-whisper"
    assert payload["provider_available"] is False
    assert payload["reason"] == "probe_failed"
    assert payload["effective_provider"] == "whisper.cpp"
    assert payload["fallback"]["available"] is True


def test_whisper_cpp_health_probe_failure_marks_runtime_unavailable(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        stt_provider="whisper_cpp",
        whisper_command=str(tmp_path / "whisper-cli.exe"),
        whisper_model_path=str(tmp_path / "ggml-base.bin"),
    )
    settings.ensure_directories()
    Path(settings.whisper_command).write_text("stub", encoding="utf-8")
    Path(settings.whisper_model_path).write_text("stub", encoding="utf-8")
    service = SttService(settings)
    service._probe_whisper_cpp = lambda: (_ for _ in ()).throw(RuntimeError("process crashed"))  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["reason"] == "probe_failed"
    assert "process crashed" in payload["error"]


def test_stt_health_uses_cache_until_ttl_expires(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, stt_provider="whisper_cpp")
    settings.ensure_directories()
    service = SttService(settings)
    calls = {"count": 0}
    clock = {"value": 100.0}

    def fake_health(probe_endpoint: bool) -> dict[str, object]:
        calls["count"] += 1
        return {"available": True, "provider": "whisper.cpp", "effective_provider": "whisper.cpp"}

    monkeypatch.setattr("app.services.stt.time.monotonic", lambda: clock["value"])
    service._whisper_cpp_health = fake_health  # type: ignore[method-assign]

    first = service.health()
    second = service.health()
    clock["value"] += 61.0
    third = service.health()

    assert calls["count"] == 2
    assert first["probe_cached"] is False
    assert second["probe_cached"] is True
    assert third["probe_cached"] is False
