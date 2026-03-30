from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.llm import LlmService


@dataclass
class RouteDecision:
    route: str
    reason: str
    provider: str
    complexity: int
    long_context: bool


class RouterService:
    def __init__(self, settings: Settings, llm_service: LlmService) -> None:
        self._settings = settings
        self._llm_service = llm_service

    def route_request(
        self,
        *,
        text: str,
        notes_context: str | None = None,
        voice_mode: bool = False,
    ) -> RouteDecision:
        if self._settings.routing_mode == "fast":
            return RouteDecision("groq_fast", "routing_mode_fast", self._settings.fast_provider, 1, False)
        if self._settings.routing_mode == "deep":
            return RouteDecision("gemini_deep", "routing_mode_deep", self._settings.deep_provider, 5, True)
        if self._settings.routing_mode == "hybrid":
            return RouteDecision("hybrid_plan_then_groq", "routing_mode_hybrid", self._settings.deep_provider, 4, True)

        complexity = self._estimate_complexity(text, notes_context)
        long_context = self._detect_long_context(text, notes_context)
        planning = self._contains_planning_keywords(text)

        fast_available = self._llm_service.provider_available(self._settings.fast_provider)
        deep_available = self._llm_service.provider_available(self._settings.deep_provider)

        if voice_mode and complexity <= 2 and fast_available:
            return RouteDecision("groq_fast", "voice_fast_path", self._settings.fast_provider, complexity, long_context)

        if long_context or complexity >= 4 or planning:
            if voice_mode and fast_available and deep_available:
                return RouteDecision(
                    "hybrid_plan_then_groq",
                    "deep_reasoning_with_voice_delivery",
                    self._settings.deep_provider,
                    complexity,
                    long_context,
                )
            if deep_available:
                return RouteDecision("gemini_deep", "deep_reasoning_detected", self._settings.deep_provider, complexity, long_context)
            if fast_available:
                return RouteDecision("groq_fast", "deep_provider_unavailable", self._settings.fast_provider, complexity, long_context)

        if complexity == 3 and fast_available and deep_available:
            return RouteDecision("hybrid_plan_then_groq", "medium_complexity_balanced_route", self._settings.deep_provider, complexity, long_context)

        if fast_available:
            return RouteDecision("groq_fast", "default_fast_route", self._settings.fast_provider, complexity, long_context)
        if deep_available:
            return RouteDecision("gemini_deep", "fast_provider_unavailable", self._settings.deep_provider, complexity, long_context)
        return RouteDecision("groq_fast", "no_provider_available", self._settings.fast_provider, complexity, long_context)

    def _estimate_complexity(self, text: str, notes_context: str | None) -> int:
        lowered = text.casefold()
        score = 1
        if len(lowered.split()) > 40:
            score += 1
        if notes_context and len(notes_context.split()) > 80:
            score += 2
        if self._contains_planning_keywords(lowered):
            score += 2
        if any(token in lowered for token in ("nhung", "nhieu buoc", "rang buoc", "compare", "strategy")):
            score += 1
        return min(score, 5)

    def _detect_long_context(self, text: str, notes_context: str | None) -> bool:
        if len(text.split()) >= 120:
            return True
        return bool(notes_context and len(notes_context.split()) >= 80)

    def _contains_planning_keywords(self, text: str) -> bool:
        lowered = text.casefold()
        keywords = ("lap ke hoach", "phan tich", "tong hop", "chien luoc", "toi uu", "sap xep", "chia viec")
        return any(token in lowered for token in keywords)
