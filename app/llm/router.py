from __future__ import annotations

from pydantic import BaseModel

from app.core.config import Settings
from app.llm.base import BaseLLMProvider
from app.llm.lmstudio import LMStudioProvider
from app.llm.mock import MockProvider
from app.llm.models import LLMGenerateContext, ProviderConfig


class LLMRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = self._build_provider()

    def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        context: LLMGenerateContext,
    ) -> BaseModel:
        return self.provider.generate_structured(prompt, response_model, context)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed(texts)

    def _build_provider(self) -> BaseLLMProvider:
        config = self.settings.load_yaml(self.settings.model_config_path)
        provider_name = self.settings.llm_provider or config.get("default_provider", "lmstudio")
        providers = config.get("providers", {})
        provider_data = providers.get(provider_name, {})
        provider_config = ProviderConfig(
            name=provider_name,
            base_url=self.settings.llm_base_url or provider_data.get("base_url"),
            chat_model=self.settings.llm_chat_model or provider_data.get("chat_model", "local-model"),
            embedding_model=(
                self.settings.llm_embedding_model or provider_data.get("embedding_model")
            ),
            timeout_sec=int(provider_data.get("timeout_sec", 60)),
        )
        if provider_name == "mock":
            return MockProvider(provider_config)
        return LMStudioProvider(provider_config)
