from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from app.agent.controller import AgentController
from app.config.settings import Settings
from app.profiles.calculator_profile import CalculatorProfile


def _build_settings(tmp_path: Path) -> Settings:
    settings = Settings.default()
    settings.artifact_root = tmp_path / "logs"
    return settings


@pytest.mark.integration
def test_calculator_compute_flow() -> None:
    if shutil.which("calc.exe") is None:
        raise AssertionError("Calculator is not available on this machine.")

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        controller = AgentController(_build_settings(tmp_path))
        result = controller.run(CalculatorProfile(), "compute 125*4")

        assert result["status"] == "completed"
        last_attempt = result["attempts"][-1]
        verification = last_attempt["details"]["verification"]
        assert verification["passed"] is True
