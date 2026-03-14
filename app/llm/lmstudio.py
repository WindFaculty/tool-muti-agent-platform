from __future__ import annotations

import json
from typing import Any

import requests
from pydantic import BaseModel

from app.core.errors import ExecutionError
from app.llm.base import BaseLLMProvider
from app.llm.models import LLMGenerateContext


class LMStudioProvider(BaseLLMProvider):
    def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        context: LLMGenerateContext,
    ) -> BaseModel:
        response = self._chat_completion(prompt, response_model, context)
        return response_model.model_validate(self._extract_json_payload(response))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.config.embedding_model:
            return [[] for _ in texts]
        response = requests.post(
            f"{self.config.base_url}/embeddings",
            json={"model": self.config.embedding_model, "input": texts},
            timeout=self.config.timeout_sec,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        return [list(item.get("embedding", [])) for item in data]

    def _chat_completion(
        self,
        prompt: str,
        response_model: type[BaseModel],
        context: LLMGenerateContext,
    ) -> str:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=True)
        system_prompt = (
            "Return valid JSON only. "
            f"Agent={context.agent_name}. "
            f"Match this schema exactly: {schema}"
        )
        payload = {
            "model": self.config.chat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            json=payload,
            timeout=self.config.timeout_sec,
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        if not choices:
            raise ExecutionError("LM Studio returned no choices")
        return str(choices[0].get("message", {}).get("content", ""))

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ExecutionError("LM Studio did not return a JSON object")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExecutionError(f"Failed to decode LM Studio JSON response: {exc}") from exc
