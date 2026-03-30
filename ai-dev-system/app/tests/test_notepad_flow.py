from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from app.agent.controller import AgentController
from app.config.settings import Settings
from app.profiles.notepad_profile import NotepadProfile


def _build_settings(tmp_path: Path) -> Settings:
    settings = Settings.default()
    settings.artifact_root = tmp_path / "logs"
    return settings


@pytest.mark.integration
def test_notepad_type_and_save_flow() -> None:
    if shutil.which("notepad.exe") is None:
        raise AssertionError("Notepad is not available on this machine.")

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        controller = AgentController(_build_settings(tmp_path))
        result = controller.run(NotepadProfile(), "type hello from pytest and save")

        assert result["status"] == "completed"
        output_file = Path(result["artifact_dir"]) / "notepad-output.txt"
        assert output_file.exists()
        assert "hello from pytest" in output_file.read_text(encoding="utf-8")
