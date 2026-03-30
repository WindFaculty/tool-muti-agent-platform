from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger("llm_clients")


@dataclass
class ModelReply:
    provider: str
    model: str
    text: str
    token_usage: dict[str, Any]


class OpenAICompatibleProviderClient:
    def __init__(
        self,
        *,
        provider: str,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_sec: float,
        temperature: float,
    ) -> None:
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_sec = timeout_sec
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    def health(self) -> dict[str, Any]:
        if not self._api_key:
            return {
                "available": False,
                "provider": self.provider,
                "base_url": self._base_url,
                "model": self._model,
                "reason": "missing_api_key",
            }
        try:
            with httpx.Client(timeout=self._timeout_sec) as client:
                response = client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
                response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network branch
            logger.warning("%s health check failed for %s: %s", self.provider, self._base_url, exc)
            return {
                "available": False,
                "provider": self.provider,
                "base_url": self._base_url,
                "model": self._model,
                "reason": str(exc),
            }
        return {
            "available": True,
            "provider": self.provider,
            "base_url": self._base_url,
            "model": self._model,
        }

    def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        json_output: bool = False,
    ) -> ModelReply:
        if not self._api_key:
            raise RuntimeError(f"{self.provider} API key is not configured")

        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature if temperature is None else temperature,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=self._timeout_sec) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.provider} returned no choices")
        content = ((((choices[0] or {}).get("message") or {}).get("content")) or "").strip()
        usage = data.get("usage") or {}
        return ModelReply(
            provider=self.provider,
            model=self._model,
            text=content,
            token_usage=usage,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
