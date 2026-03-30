from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from PIL import Image


@dataclass(frozen=True, slots=True)
class VisionPrediction:
    bounding_box: tuple[int, int, int, int]
    confidence: float
    target_description: str
    reason: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "VisionPrediction":
        box = payload.get("bounding_box")
        confidence = payload.get("confidence")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("Vision prediction payload must include bounding_box=[left, top, right, bottom].")
        if confidence is None:
            raise ValueError("Vision prediction payload must include confidence.")
        try:
            parsed_box = tuple(int(value) for value in box)
        except Exception as exc:
            raise ValueError("Vision prediction bounding_box values must be integers.") from exc
        parsed_confidence = float(confidence)
        if parsed_confidence <= 0 or parsed_confidence > 1:
            raise ValueError("Vision prediction confidence must be in the range (0, 1].")
        return cls(
            bounding_box=parsed_box,
            confidence=parsed_confidence,
            target_description=str(payload.get("target_description") or ""),
            reason=str(payload.get("reason") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bounding_box": list(self.bounding_box),
            "confidence": self.confidence,
            "target_description": self.target_description,
            "reason": self.reason,
        }


class VisionLocator(Protocol):
    def locate(
        self,
        *,
        image: Image.Image,
        target_description: str,
        region_hint: tuple[int, int, int, int] | None,
        candidate_actions: list[dict[str, Any]],
    ) -> VisionPrediction:
        ...


class VisionLlmLocator:
    """Provider-agnostic Vision locator.

    The concrete provider is intentionally injected as a callable so the GUI agent
    can remain provider-neutral while tests can supply deterministic predictions.
    """

    def __init__(
        self,
        resolver: Callable[[dict[str, Any]], dict[str, Any] | VisionPrediction] | None = None,
    ) -> None:
        self._resolver = resolver

    def available(self) -> bool:
        return self._resolver is not None

    def locate(
        self,
        *,
        image: Image.Image,
        target_description: str,
        region_hint: tuple[int, int, int, int] | None,
        candidate_actions: list[dict[str, Any]],
    ) -> VisionPrediction:
        if self._resolver is None:
            raise RuntimeError("Vision LLM locator is unavailable.")

        payload = {
            "image_size": list(image.size),
            "target_description": target_description,
            "region_hint": list(region_hint) if region_hint is not None else None,
            "candidate_actions": candidate_actions,
        }
        resolved = self._resolver(payload)
        if isinstance(resolved, VisionPrediction):
            return resolved
        if not isinstance(resolved, dict):
            raise ValueError("Vision locator resolver must return a dict payload or VisionPrediction.")
        return VisionPrediction.from_payload(resolved)
