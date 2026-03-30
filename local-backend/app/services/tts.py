from __future__ import annotations

import hashlib
import importlib
import re
import shutil
import subprocess
import time
import typing
import wave
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.ids import make_id
from app.core.logging import get_logger

logger = get_logger("tts")


def _apply_chattts_torch_compat() -> None:
    import torch

    # ChatTTS 0.1.1 still references torch.serialization.FILE_LIKE in annotations.
    if not hasattr(torch.serialization, "FILE_LIKE"):
        torch.serialization.FILE_LIKE = typing.Any

    # Fix for PyTorch 2.6+ blocking object loading (e.g. BertTokenizerFast, GPT models)
    if not getattr(torch, "_chattts_patched", False):
        _original_load = torch.load

        def _patched_load(*args: Any, **kwargs: Any) -> Any:
            if "weights_only" not in kwargs:
                kwargs["weights_only"] = False
            return _original_load(*args, **kwargs)

        torch.load = _patched_load
        torch._chattts_patched = True


class TtsService:
    _HEALTH_CACHE_TTL_SECONDS = 60.0

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._chattts: Any | None = None
        self._chattts_module: Any | None = None
        self._chattts_speakers: dict[str, Any] = {}
        self._health_cache: dict[str, Any] | None = None
        self._health_checked_at = 0.0

    def health(self) -> dict[str, Any]:
        if self._health_cache is not None and (time.monotonic() - self._health_checked_at) < self._HEALTH_CACHE_TTL_SECONDS:
            payload = dict(self._health_cache)
            payload["probe_cached"] = True
            return payload

        if self._settings.tts_provider == "chattts":
            payload = self._chattts_health()
        else:
            payload = self._piper_health(probe_endpoint=True)
        payload["probe_cached"] = False
        self._health_cache = dict(payload)
        self._health_checked_at = time.monotonic()
        return payload

    def _piper_health(self, *, probe_endpoint: bool) -> dict[str, Any]:
        command = self._resolve_command(self._settings.piper_command)
        model_path = self._resolve_model_path(self._settings.piper_model_path)
        issues: list[str] = []
        if command is None:
            issues.append("command_not_configured_or_not_found")
        if model_path is None:
            issues.append("model_path_not_configured_or_not_found")
        payload: dict[str, Any] = {
            "available": len(issues) == 0,
            "provider": "piper",
        }
        if self._settings.piper_command:
            payload["command"] = self._settings.piper_command
        if self._settings.piper_model_path:
            payload["model_path"] = self._settings.piper_model_path
        if issues:
            payload["reason"] = issues[0]
            payload["issues"] = issues
            return payload

        if probe_endpoint:
            try:
                self._probe_piper()
            except Exception as exc:
                logger.warning("Piper health probe failed: %s", exc)
                payload["available"] = False
                payload["reason"] = "probe_failed"
                payload["error"] = str(exc)
                return payload

        payload["effective_provider"] = "piper"
        return payload

    def _chattts_health(self) -> dict[str, Any]:
        try:
            chattts_module = self._import_chattts()
        except ModuleNotFoundError:
            return {
                "available": False,
                "provider_available": False,
                "provider": "chattts",
                "reason": "module_not_installed",
                "sample_rate": self._settings.chattts_sample_rate,
            }
        except Exception as exc:
            logger.warning("ChatTTS import failed during health check: %s", exc)
            return {
                "available": False,
                "provider_available": False,
                "provider": "chattts",
                "reason": "import_failed",
                "error": str(exc),
                "sample_rate": self._settings.chattts_sample_rate,
            }
        try:
            self._load_chattts(chattts_module)
        except Exception as exc:
            logger.warning("ChatTTS load failed during health check: %s", exc)
            return {
                "available": False,
                "provider_available": False,
                "provider": "chattts",
                "reason": "load_failed",
                "error": str(exc),
                "sample_rate": self._settings.chattts_sample_rate,
            }
        try:
            self._probe_chattts()
        except Exception as exc:
            logger.warning("ChatTTS inference probe failed during health check: %s", exc)
            return {
                "available": False,
                "provider_available": False,
                "provider": "chattts",
                "reason": "probe_failed",
                "error": str(exc),
                "sample_rate": self._settings.chattts_sample_rate,
            }
        return {
            "available": True,
            "provider_available": True,
            "provider": "chattts",
            "compile": self._settings.chattts_compile,
            "sample_rate": self._settings.chattts_sample_rate,
            "effective_provider": "chattts",
        }

    def synthesize(self, text: str, voice: str | None = None, cache: bool = True) -> dict[str, Any]:
        key = hashlib.sha256(
            f"{self._settings.tts_provider}:{voice or self._settings.default_tts_voice}:{text}".encode("utf-8")
        ).hexdigest()
        output_path = self._settings.audio_dir / f"{key}.wav"
        cached = cache and output_path.exists()
        if not cached:
            last_error: Exception | None = None
            for attempt in range(1, self._settings.tts_retry_attempts + 1):
                temp_output_path = self._settings.audio_dir / f"{key}.{make_id('tts')}.tmp.wav"
                try:
                    if self._settings.tts_provider == "chattts":
                        self._synthesize_with_chattts(text, temp_output_path, voice)
                    else:
                        self._synthesize_with_piper(text, temp_output_path, voice)
                    temp_output_path.replace(output_path)
                    last_error = None
                    break
                except Exception as exc:
                    self._invalidate_health_cache()
                    last_error = exc
                    temp_output_path.unlink(missing_ok=True)
                    logger.warning("Removed incomplete TTS audio artifact for %s", output_path.name)
                    if attempt >= self._settings.tts_retry_attempts or not self._is_retryable_tts_error(exc):
                        raise
                    logger.warning(
                        "Retrying TTS synthesis for %s after attempt %s/%s failed: %s",
                        output_path.name,
                        attempt,
                        self._settings.tts_retry_attempts,
                        exc,
                    )
            if last_error is not None:
                raise last_error

        return {
            "audio_path": output_path,
            "audio_url": f"/v1/speech/cache/{output_path.name}",
            "duration_ms": self._audio_duration_ms(output_path),
            "cached": cached,
        }

    def split_sentences(self, text: str) -> list[str]:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]
        return sentences or ([text.strip()] if text.strip() else [])

    def synthesize_sentences(self, text: str, voice: str | None = None, cache: bool = True) -> list[dict[str, Any]]:
        results = []
        for sentence in self.split_sentences(text):
            synthesis = self.synthesize(sentence, voice=voice, cache=cache)
            synthesis["text"] = sentence
            results.append(synthesis)
        return results

    def _is_retryable_tts_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        non_retryable_markers = (
            "runtime is not configured",
            "model path is not configured",
            "is not installed",
            "import failed",
        )
        return not any(marker in message for marker in non_retryable_markers)

    def _resolve_command(self, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value)
        if path.exists():
            return str(path) if path.is_file() else None
        return shutil.which(value)

    def _resolve_model_path(self, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value)
        if not path.exists() or not path.is_file():
            return None
        return str(path)

    def _synthesize_with_piper(self, text: str, output_path: Path, voice: str | None) -> None:
        command = self._resolve_command(self._settings.piper_command)
        if command is None:
            logger.warning("TTS requested but Piper runtime is not configured")
            raise RuntimeError("Piper runtime is not configured")
        model_path = self._resolve_model_path(self._settings.piper_model_path)
        if model_path is None:
            logger.warning("TTS requested but Piper model path is not configured")
            raise RuntimeError("Piper model path is not configured")

        process = subprocess.run(
            [
                command,
                "-m",
                model_path,
                "-f",
                str(output_path),
            ],
            input=text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self._settings.piper_timeout_sec,
            check=False,
        )
        if process.returncode != 0:
            logger.error(
                "Piper synthesis failed for voice %s: %s",
                voice or self._settings.default_tts_voice,
                process.stderr.strip(),
            )
            raise RuntimeError(process.stderr.strip() or "Piper synthesis failed")

    def _synthesize_with_chattts(self, text: str, output_path: Path, voice: str | None) -> None:
        try:
            chattts_module = self._import_chattts()
        except ModuleNotFoundError:
            logger.warning("TTS requested but ChatTTS is not installed")
            raise RuntimeError("ChatTTS is not installed")
        except Exception as exc:
            logger.warning("TTS requested but ChatTTS failed to import: %s", exc)
            raise RuntimeError(f"ChatTTS import failed: {exc}") from exc

        try:
            chat = self._load_chattts(chattts_module)
            infer_kwargs: dict[str, Any] = {}
            speaker = self._chattts_speaker(chat, voice)
            infer_code_params = getattr(chattts_module.Chat, "InferCodeParams", None)
            if speaker is not None and callable(infer_code_params):
                infer_kwargs["params_infer_code"] = infer_code_params(spk_emb=speaker)
            wavs = chat.infer([text], **infer_kwargs)
        except Exception as exc:
            logger.error("ChatTTS synthesis failed for voice %s: %s", voice or self._settings.default_tts_voice, exc)
            raise RuntimeError(f"ChatTTS synthesis failed: {exc}") from exc

        if not wavs:
            raise RuntimeError("ChatTTS did not return audio data")
        self._write_pcm16_wav(output_path, wavs[0], self._settings.chattts_sample_rate)

    def _import_chattts(self) -> Any:
        if self._chattts_module is None:
            _apply_chattts_torch_compat()
            self._chattts_module = importlib.import_module("ChatTTS")
        return self._chattts_module

    def _load_chattts(self, chattts_module: Any) -> Any:
        if self._chattts is None:
            chat = chattts_module.Chat()
            success = chat.load(compile=self._settings.chattts_compile, source="huggingface")
            if not success:
                raise RuntimeError("ChatTTS model weights failed to load.")
            self._chattts = chat
        return self._chattts

    def _chattts_speaker(self, chat: Any, voice: str | None) -> Any | None:
        speaker_key = voice or self._settings.default_tts_voice
        if speaker_key in self._chattts_speakers:
            return self._chattts_speakers[speaker_key]
        sample_random_speaker = getattr(chat, "sample_random_speaker", None)
        if not callable(sample_random_speaker):
            return None
        speaker = sample_random_speaker()
        self._chattts_speakers[speaker_key] = speaker
        return speaker

    def _write_pcm16_wav(self, output_path: Path, samples: Any, sample_rate: int) -> None:
        import numpy as np

        if hasattr(samples, "detach"):
            samples = samples.detach().cpu().numpy()
        elif hasattr(samples, "cpu") and hasattr(samples, "numpy"):
            samples = samples.cpu().numpy()

        audio = np.asarray(samples)
        audio = np.squeeze(audio)
        if audio.ndim == 2:
            audio = audio[0]
        if audio.ndim != 1:
            audio = audio.reshape(-1)

        if np.issubdtype(audio.dtype, np.integer):
            pcm = audio.astype(np.int16, copy=False)
        else:
            audio = np.nan_to_num(audio.astype(np.float32, copy=False))
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 1.0:
                audio = audio / peak
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)

        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(pcm.tobytes())

    def _audio_duration_ms(self, output_path: Path) -> int:
        with wave.open(str(output_path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        return int((frames / rate) * 1000)

    def _probe_piper(self) -> None:
        output_path = self._settings.audio_dir / f"{make_id('ttsprobe')}.wav"
        try:
            self._synthesize_with_piper("health probe", output_path, None)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("Piper probe did not produce audio output")
        finally:
            output_path.unlink(missing_ok=True)

    def _probe_chattts(self) -> None:
        output_path = self._settings.audio_dir / f"{make_id('ttsprobe')}.wav"
        try:
            self._synthesize_with_chattts("health probe", output_path, None)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("ChatTTS probe did not produce audio output")
        finally:
            output_path.unlink(missing_ok=True)

    def _invalidate_health_cache(self) -> None:
        self._health_cache = None
        self._health_checked_at = 0.0
