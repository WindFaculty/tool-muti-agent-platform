from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "app.db",
        audio_dir=tmp_path / "data" / "audio",
        cache_dir=tmp_path / "data" / "cache",
        log_dir=tmp_path / "data" / "logs",
        llm_provider="hybrid",
        stt_provider="whisper_cpp",
        whisper_command=None,
        piper_command=None,
        tts_provider="piper",
        reminder_poll_seconds=1,
    )


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
