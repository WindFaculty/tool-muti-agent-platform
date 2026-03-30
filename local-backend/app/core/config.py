from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "local-desktop-assistant-backend"
    app_version: str = "0.1.0"

    api_host: str = "127.0.0.1"
    api_port: int = 8096

    base_dir: Path = Field(default_factory=_base_dir)
    data_dir: Path | None = None
    db_path: Path | None = None
    audio_dir: Path | None = None
    cache_dir: Path | None = None
    log_dir: Path | None = None

    default_language: str = "vi"
    default_tts_voice: str = "vi-VN-default"
    llm_provider: str = "hybrid"
    routing_mode: str = "auto"
    fast_provider: str = "groq"
    deep_provider: str = "gemini"
    enable_ollama: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_sec: float = 8.0
    groq_api_key: str | None = Field(default=None, repr=False)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout_sec: float = 15.0
    groq_temperature: float = 0.2
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_sec: float = 15.0
    gemini_temperature: float = 0.2
    llm_recent_failure_window_sec: int = 120

    stt_provider: str = "faster_whisper"
    faster_whisper_model_path: str | None = None
    faster_whisper_model_size: str = "small"
    faster_whisper_device: str = "auto"
    faster_whisper_compute_type: str = "auto"

    whisper_command: str | None = None
    whisper_model_path: str | None = None
    whisper_timeout_sec: float = 60.0

    piper_command: str | None = None
    piper_model_path: str | None = None
    piper_timeout_sec: float = 30.0
    tts_provider: str = "piper"
    tts_retry_attempts: int = 2
    chattts_compile: bool = False
    chattts_sample_rate: int = 24000

    reminder_lead_minutes: int = 15
    reminder_poll_seconds: int = 5
    due_soon_window_hours: int = 4
    occurrence_horizon_days: int = 60
    speech_cache_enabled: bool = True
    short_term_turn_limit: int = 12
    fast_context_task_limit: int = 3
    deep_context_task_limit: int = 5
    notes_context_word_limit: int = 120
    rolling_summary_line_limit: int = 4
    long_term_memory_limit: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="assistant_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def finalize_paths(self) -> "Settings":
        self.llm_provider = self.llm_provider.strip().lower()
        if self.llm_provider not in {"hybrid", "gemini", "groq"}:
            raise ValueError("assistant_llm_provider must be one of 'hybrid', 'gemini', or 'groq'")
        self.routing_mode = self.routing_mode.strip().lower()
        if self.routing_mode not in {"auto", "fast", "deep", "hybrid"}:
            raise ValueError("assistant_routing_mode must be one of 'auto', 'fast', 'deep', or 'hybrid'")
        self.fast_provider = self.fast_provider.strip().lower()
        self.deep_provider = self.deep_provider.strip().lower()
        if self.fast_provider not in {"groq", "gemini"}:
            raise ValueError("assistant_fast_provider must be either 'groq' or 'gemini'")
        if self.deep_provider not in {"groq", "gemini"}:
            raise ValueError("assistant_deep_provider must be either 'groq' or 'gemini'")
        self.stt_provider = self.stt_provider.strip().lower()
        if self.stt_provider not in {"faster_whisper", "whisper_cpp"}:
            raise ValueError("assistant_stt_provider must be either 'faster_whisper' or 'whisper_cpp'")
        self.tts_provider = self.tts_provider.strip().lower()
        if self.tts_provider not in {"piper", "chattts"}:
            raise ValueError("assistant_tts_provider must be either 'piper' or 'chattts'")
        if self.fast_context_task_limit < 1:
            raise ValueError("assistant_fast_context_task_limit must be >= 1")
        if self.deep_context_task_limit < 1:
            raise ValueError("assistant_deep_context_task_limit must be >= 1")
        if self.notes_context_word_limit < 1:
            raise ValueError("assistant_notes_context_word_limit must be >= 1")
        if self.rolling_summary_line_limit < 1:
            raise ValueError("assistant_rolling_summary_line_limit must be >= 1")
        if self.long_term_memory_limit < 1:
            raise ValueError("assistant_long_term_memory_limit must be >= 1")
        if self.tts_retry_attempts < 1:
            raise ValueError("assistant_tts_retry_attempts must be >= 1")
        self.ollama_base_url = self.ollama_base_url.rstrip("/")
        self.groq_base_url = self.groq_base_url.rstrip("/")
        self.gemini_base_url = self.gemini_base_url.rstrip("/")
        if self.data_dir is None:
            self.data_dir = self.base_dir / "data"
        if self.db_path is None:
            self.db_path = self.data_dir / "app.db"
        if self.audio_dir is None:
            self.audio_dir = self.data_dir / "audio"
        if self.cache_dir is None:
            self.cache_dir = self.data_dir / "cache"
        if self.log_dir is None:
            self.log_dir = self.data_dir / "logs"
        return self

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.audio_dir, self.cache_dir, self.log_dir):
            if path is not None:
                path.mkdir(parents=True, exist_ok=True)

    @property
    def active_llm_model(self) -> str:
        if self.llm_provider == "hybrid":
            return f"{self.groq_model} | {self.gemini_model}"
        if self.llm_provider == "gemini":
            return self.gemini_model
        if self.llm_provider == "groq":
            return self.groq_model
        return f"{self.groq_model} | {self.gemini_model}"

    @property
    def active_llm_provider_label(self) -> str:
        if self.llm_provider == "hybrid":
            return f"{self.fast_provider}->{self.deep_provider}"
        return self.llm_provider
