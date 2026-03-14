from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.llm.models import LLMGenerateContext, ProviderConfig


class BaseLLMProvider(ABC):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        context: LLMGenerateContext,
    ) -> BaseModel:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]

    @staticmethod
    def _stringify(value: Any) -> str:
        return str(value) if value is not None else ""
