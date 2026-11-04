"""Backend configuration, read from environment variables once at import time."""

import os
from dataclasses import dataclass

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None = None
    llama_model: str = DEFAULT_MODEL
    llm_timeout_seconds: float = 40.0

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key)


def load_settings() -> Settings:
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        llama_model=os.getenv("LLAMA_MODEL") or DEFAULT_MODEL,
    )
