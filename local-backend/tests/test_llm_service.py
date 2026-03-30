from __future__ import annotations

from typing import Any

import app.services.llm as llm_module
from app.core.config import Settings
from app.services.llm import LlmService


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_groq_health_requires_api_key(tmp_path) -> None:
    service = LlmService(
        Settings(
            _env_file=None,
            base_dir=tmp_path,
            llm_provider="groq",
            groq_api_key=None,
        )
    )

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "groq"
    assert payload["reason"] == "missing_api_key"


def test_groq_refine_reply_uses_chat_completions(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json or {}
            return _FakeResponse({"choices": [{"message": {"content": "Ban co 2 viec hom nay."}}]})

    monkeypatch.setattr(llm_module.httpx, "Client", _FakeClient)

    service = LlmService(
        Settings(
            _env_file=None,
            base_dir=tmp_path,
            llm_provider="groq",
            groq_api_key="test-key",
            groq_model="llama-3.1-8b-instant",
            groq_timeout_sec=12.0,
        )
    )

    reply = service.refine_reply("Hom nay co gi?", {"reply": "Co 2 viec", "actions": []})

    assert reply == "Ban co 2 viec hom nay."
    assert captured["timeout"] == 12.0
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "llama-3.1-8b-instant"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"


def test_gemini_health_requires_api_key(tmp_path) -> None:
    service = LlmService(
        Settings(
            _env_file=None,
            base_dir=tmp_path,
            llm_provider="gemini",
            gemini_api_key=None,
        )
    )

    payload = service.health()

    assert payload["available"] is False
    assert payload["provider"] == "gemini"
    assert payload["reason"] == "missing_api_key"


def test_gemini_refine_reply_uses_chat_completions(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json or {}
            return _FakeResponse({"choices": [{"message": {"content": "Hom nay ban co 2 viec."}}]})

    monkeypatch.setattr(llm_module.httpx, "Client", _FakeClient)

    service = LlmService(
        Settings(
            _env_file=None,
            base_dir=tmp_path,
            llm_provider="gemini",
            gemini_api_key="test-key",
            gemini_model="gemini-2.5-flash",
            gemini_timeout_sec=10.0,
        )
    )

    reply = service.refine_reply("Hom nay co gi?", {"reply": "Co 2 viec", "actions": []})

    assert reply == "Hom nay ban co 2 viec."
    assert captured["timeout"] == 10.0
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "gemini-2.5-flash"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"
