from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import httpx  # re-exported for compatibility in tests and monkeypatching

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.time import now_local
from app.services.llm_clients import ModelReply, OpenAICompatibleProviderClient

logger = get_logger("llm")


class LlmService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients = {
            "groq": OpenAICompatibleProviderClient(
                provider="groq",
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                model=settings.groq_model,
                timeout_sec=settings.groq_timeout_sec,
                temperature=settings.groq_temperature,
            ),
            "gemini": OpenAICompatibleProviderClient(
                provider="gemini",
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                model=settings.gemini_model,
                timeout_sec=settings.gemini_timeout_sec,
                temperature=settings.gemini_temperature,
            ),
        }
        self._failure_windows: dict[str, datetime] = {}

    def health(self) -> dict[str, Any]:
        if self._settings.llm_provider in {"groq", "gemini"}:
            return self.provider_health(self._settings.llm_provider)
        fast = self.provider_health(self._settings.fast_provider)
        deep = self.provider_health(self._settings.deep_provider)
        available = fast.get("available", False) or deep.get("available", False)
        return {
            "available": available,
            "provider": self._settings.llm_provider,
            "model": self._settings.active_llm_model,
            "routing_mode": self._settings.routing_mode,
            "fast": fast,
            "deep": deep,
            "base_url": "hybrid",
            "reason": None if available else "no_provider_available",
        }

    def provider_health(self, provider: str) -> dict[str, Any]:
        return self._clients[provider].health()

    def provider_available(self, provider: str) -> bool:
        blocked_until = self._failure_windows.get(provider)
        if blocked_until and blocked_until > now_local():
            return False
        return bool(self.provider_health(provider).get("available"))

    def record_failure(self, provider: str) -> None:
        self._failure_windows[provider] = now_local() + timedelta(seconds=self._settings.llm_recent_failure_window_sec)

    def clear_failure(self, provider: str) -> None:
        self._failure_windows.pop(provider, None)

    def model_name(self, provider: str) -> str:
        if provider == "groq":
            return self._settings.groq_model
        return self._settings.gemini_model

    def complete(
        self,
        *,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        json_output: bool = False,
        temperature: float | None = None,
    ) -> ModelReply:
        client = self._clients[provider]
        try:
            reply = client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_output=json_output,
                temperature=temperature,
            )
        except Exception:
            self.record_failure(provider)
            raise
        self.clear_failure(provider)
        return reply

    def refine_reply(self, message: str, facts: dict[str, Any]) -> str | None:
        provider = self._settings.fast_provider if self._settings.llm_provider == "hybrid" else self._settings.llm_provider
        if provider not in self._clients:
            return None
        try:
            reply = self.complete(
                provider=provider,
                system_prompt=self._system_prompt(),
                user_prompt=self._build_prompt(message, facts),
            )
        except Exception as exc:
            logger.warning("Reply refinement fell back to rule-based response: %s", exc)
            return None
        return reply.text or None

    def _system_prompt(self) -> str:
        return (
            "You are the fast-response layer of a Vietnamese virtual assistant. "
            "Answer naturally, briefly, and quickly. Use only the provided facts."
        )

    def _build_prompt(self, message: str, facts: dict[str, Any]) -> str:
        return (
            f"User message: {message}\n"
            f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
            "Response:"
        )


OllamaService = LlmService
