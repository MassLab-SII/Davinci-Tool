from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    api_key: str
    base_url: str
    model: str
    embedding_model: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> ProviderSettings:
        api_key = os.getenv("CROSS_DOMAIN_SCALING_API_KEY", "").strip()
        if not api_key:
            raise ValueError("CROSS_DOMAIN_SCALING_API_KEY is required for LLM mode")
        base_url = os.getenv(
            "CROSS_DOMAIN_SCALING_BASE_URL", "https://api.openai.com/v1"
        ).strip()
        model = os.getenv("CROSS_DOMAIN_SCALING_MODEL", "gpt-4.1-mini").strip()
        embedding_model = os.getenv(
            "CROSS_DOMAIN_SCALING_EMBEDDING_MODEL", "text-embedding-3-large"
        ).strip()
        try:
            timeout = float(os.getenv("CROSS_DOMAIN_SCALING_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ValueError("CROSS_DOMAIN_SCALING_TIMEOUT_SECONDS must be numeric") from exc
        if not base_url or not model or not embedding_model or timeout <= 0:
            raise ValueError("provider base URL, models, and timeout must be valid")
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            embedding_model=embedding_model,
            timeout_seconds=timeout,
        )

