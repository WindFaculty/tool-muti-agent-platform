from __future__ import annotations

import pytest
from PIL import Image

from app.vision.locator import VisionLlmLocator, VisionPrediction


def test_vision_prediction_parses_valid_payload() -> None:
    prediction = VisionPrediction.from_payload(
        {
            "bounding_box": [10, 20, 30, 40],
            "confidence": 0.88,
            "target_description": "Console tab",
            "reason": "Closest label match",
        }
    )

    assert prediction.bounding_box == (10, 20, 30, 40)
    assert prediction.confidence == 0.88


def test_vision_prediction_rejects_missing_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        VisionPrediction.from_payload({"bounding_box": [10, 20, 30, 40]})


def test_vision_llm_locator_uses_provider_agnostic_resolver() -> None:
    locator = VisionLlmLocator(
        resolver=lambda payload: {
            "bounding_box": [1, 2, 11, 12],
            "confidence": 0.91,
            "target_description": payload["target_description"],
            "reason": "resolver",
        }
    )

    prediction = locator.locate(
        image=Image.new("RGB", (32, 32)),
        target_description="Settings button",
        region_hint=(0, 0, 32, 32),
        candidate_actions=[{"name": "click_settings"}],
    )

    assert prediction.bounding_box == (1, 2, 11, 12)
    assert prediction.target_description == "Settings button"
