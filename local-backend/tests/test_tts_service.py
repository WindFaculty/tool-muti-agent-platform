from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from app.core.config import Settings
from app.services.tts import TtsService, _apply_chattts_torch_compat


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


def test_chattts_health_reports_missing_module(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)
    service._import_chattts = lambda: (_ for _ in ()).throw(ModuleNotFoundError())  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "chattts"
    assert payload["reason"] == "module_not_installed"


def test_piper_health_requires_command_and_model_file(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        tts_provider="piper",
        piper_command=str(tmp_path / "piper.exe"),
        piper_model_path=str(tmp_path / "models"),
    )
    settings.ensure_directories()
    Path(settings.piper_command).write_text("stub", encoding="utf-8")
    Path(settings.piper_model_path).mkdir(parents=True)
    service = TtsService(settings)

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "piper"
    assert payload["reason"] == "model_path_not_configured_or_not_found"
    assert "model_path_not_configured_or_not_found" in payload["issues"]


def test_piper_synthesize_raises_when_model_path_is_missing(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        tts_provider="piper",
        piper_command=str(tmp_path / "piper.exe"),
        piper_model_path=str(tmp_path / "missing.onnx"),
    )
    settings.ensure_directories()
    Path(settings.piper_command).write_text("stub", encoding="utf-8")
    service = TtsService(settings)

    try:
        service.synthesize("Xin chao")
    except RuntimeError as exc:
        assert "Piper model path is not configured" in str(exc)
    else:
        raise AssertionError("Expected missing Piper model path to raise RuntimeError")


def test_chattts_health_reports_import_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)
    service._import_chattts = lambda: (_ for _ in ()).throw(ImportError("transformers mismatch"))  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "chattts"
    assert payload["reason"] == "import_failed"
    assert "transformers mismatch" in payload["error"]


def test_chattts_health_reports_load_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)
    service._import_chattts = lambda: SimpleNamespace(Chat=object())  # type: ignore[method-assign]
    service._load_chattts = lambda chattts_module: (_ for _ in ()).throw(RuntimeError("weights mismatch"))  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "chattts"
    assert payload["reason"] == "load_failed"
    assert "weights mismatch" in payload["error"]


def test_chattts_health_reports_probe_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)
    service._import_chattts = lambda: SimpleNamespace(Chat=object())  # type: ignore[method-assign]
    service._load_chattts = lambda chattts_module: object()  # type: ignore[method-assign]
    service._probe_chattts = lambda: (_ for _ in ()).throw(RuntimeError("'Chat' object has no attribute 'gpt'"))  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["reason"] == "probe_failed"
    assert "attribute 'gpt'" in payload["error"]


def test_piper_health_reports_probe_failure(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        tts_provider="piper",
        piper_command=str(tmp_path / "piper.exe"),
        piper_model_path=str(tmp_path / "voice.onnx"),
    )
    settings.ensure_directories()
    Path(settings.piper_command).write_text("stub", encoding="utf-8")
    Path(settings.piper_model_path).write_text("stub", encoding="utf-8")
    service = TtsService(settings)
    service._probe_piper = lambda: (_ for _ in ()).throw(RuntimeError("piper failed to initialize"))  # type: ignore[method-assign]

    payload = service.health()

    assert payload["available"] is False
    assert payload["reason"] == "probe_failed"
    assert "failed to initialize" in payload["error"]


def test_chattts_synthesize_writes_cached_wav(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)

    class _FakeChat:
        def __init__(self) -> None:
            self.load_calls: list[bool] = []

        def load(self, compile: bool = False) -> None:
            self.load_calls.append(compile)

        def sample_random_speaker(self) -> str:
            return "speaker-1"

        def infer(self, texts: list[str], **_: object) -> list[np.ndarray]:
            assert texts == ["Xin chao"]
            return [np.linspace(-0.25, 0.25, 2400, dtype=np.float32)]

    fake_chat = _FakeChat()

    class _FakeChatFactory:
        InferCodeParams = staticmethod(lambda **kwargs: kwargs)

        def __call__(self) -> _FakeChat:
            return fake_chat

    service._import_chattts = lambda: SimpleNamespace(Chat=_FakeChatFactory())  # type: ignore[method-assign]

    first = service.synthesize("Xin chao", voice="demo")
    second = service.synthesize("Xin chao", voice="demo")

    assert first["cached"] is False
    assert second["cached"] is True
    assert first["audio_path"].exists()
    assert first["duration_ms"] > 0
    assert fake_chat.load_calls == [False]


def test_chattts_synthesize_raises_runtime_error_when_import_fails(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)
    service._import_chattts = lambda: (_ for _ in ()).throw(ImportError("transformers mismatch"))  # type: ignore[method-assign]

    try:
        service.synthesize("Xin chao")
    except RuntimeError as exc:
        assert "ChatTTS import failed" in str(exc)
        assert "transformers mismatch" in str(exc)
    else:
        raise AssertionError("Expected ChatTTS import failure to raise RuntimeError")


def test_synthesize_cleans_incomplete_temp_audio_when_provider_fails(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts")
    settings.ensure_directories()
    service = TtsService(settings)

    def fail_after_partial_write(text: str, output_path: Path, voice: str | None) -> None:
        output_path.write_bytes(b"partial-audio")
        raise RuntimeError("chattts crashed mid-write")

    service._synthesize_with_chattts = fail_after_partial_write  # type: ignore[method-assign]

    try:
        service.synthesize("Xin chao")
    except RuntimeError as exc:
        assert "chattts crashed mid-write" in str(exc)
    else:
        raise AssertionError("Expected provider failure to raise RuntimeError")

    assert list(settings.audio_dir.glob("*.tmp.wav")) == []
    assert list(settings.audio_dir.glob("*.wav")) == []


def test_synthesize_retries_transient_provider_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts", tts_retry_attempts=2)
    settings.ensure_directories()
    service = TtsService(settings)
    attempts = {"count": 0}

    def flaky_provider(text: str, output_path: Path, voice: str | None) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            output_path.write_bytes(b"partial-audio")
            raise RuntimeError("temporary tts overload")
        service._write_pcm16_wav(output_path, np.linspace(-0.1, 0.1, 800, dtype=np.float32), 24000)

    service._synthesize_with_chattts = flaky_provider  # type: ignore[method-assign]

    result = service.synthesize("Xin chao")

    assert attempts["count"] == 2
    assert result["audio_path"].exists()
    assert result["duration_ms"] > 0
    assert list(settings.audio_dir.glob("*.tmp.wav")) == []


def test_synthesize_does_not_retry_non_retryable_configuration_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tts_provider="chattts", tts_retry_attempts=3)
    settings.ensure_directories()
    service = TtsService(settings)
    attempts = {"count": 0}

    def fail_config(text: str, output_path: Path, voice: str | None) -> None:
        attempts["count"] += 1
        raise RuntimeError("ChatTTS import failed: transformers mismatch")

    service._synthesize_with_chattts = fail_config  # type: ignore[method-assign]

    try:
        service.synthesize("Xin chao")
    except RuntimeError as exc:
        assert "ChatTTS import failed" in str(exc)
    else:
        raise AssertionError("Expected non-retryable configuration error to raise RuntimeError")

    assert attempts["count"] == 1


def test_apply_chattts_torch_compat_restores_file_like_symbol() -> None:
    original = getattr(torch.serialization, "FILE_LIKE", None)
    had_original = hasattr(torch.serialization, "FILE_LIKE")
    if had_original:
        delattr(torch.serialization, "FILE_LIKE")

    try:
        _apply_chattts_torch_compat()
        assert hasattr(torch.serialization, "FILE_LIKE")
    finally:
        if had_original:
            torch.serialization.FILE_LIKE = original
        elif hasattr(torch.serialization, "FILE_LIKE"):
            delattr(torch.serialization, "FILE_LIKE")


def test_tts_health_uses_cache_until_ttl_expires(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, tts_provider="piper")
    settings.ensure_directories()
    service = TtsService(settings)
    calls = {"count": 0}
    clock = {"value": 200.0}

    def fake_health(probe_endpoint: bool) -> dict[str, object]:
        calls["count"] += 1
        return {"available": True, "provider": "piper", "effective_provider": "piper"}

    monkeypatch.setattr("app.services.tts.time.monotonic", lambda: clock["value"])
    service._piper_health = fake_health  # type: ignore[method-assign]

    first = service.health()
    second = service.health()
    clock["value"] += 61.0
    third = service.health()

    assert calls["count"] == 2
    assert first["probe_cached"] is False
    assert second["probe_cached"] is True
    assert third["probe_cached"] is False
