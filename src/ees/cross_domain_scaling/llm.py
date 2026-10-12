from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import ProviderSettings


class JsonGenerator(Protocol):
    def generate(self, *, system: str, prompt: str) -> dict[str, Any]: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleGenerator:
    """Small provider adapter; imported only when the optional dependency is used."""

    def __init__(self, settings: ProviderSettings) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("LLM mode requires: pip install -e '.[llm]'") from exc
        self._model = settings.model
        self._embedding_model = settings.embedding_model
        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    def generate(self, *, system: str, prompt: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        return _parse_json_object(content)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._embedding_model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def _parse_json_object(content: str) -> dict[str, Any]:
    candidate = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("model response was not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value

