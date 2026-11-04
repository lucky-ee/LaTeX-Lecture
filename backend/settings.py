"""Backend configuration, read from environment variables once at import time."""

import os
from dataclasses import dataclass

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_RATE_LIMIT_PER_MINUTE = 20


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None = None
    llama_model: str = DEFAULT_MODEL
    llm_timeout_seconds: float = 40.0
    # Requests per client IP per minute to /api/interpret; 0 disables the limit.
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    # When set, GET /metrics requires "Authorization: Bearer <token>".
    metrics_token: str | None = None
    # Browser origins allowed to call the API cross-origin; empty = same-origin only.
    cors_origins: tuple[str, ...] = ()

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key)


def _non_negative_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"{name} must be 0 or greater, got {value}")
    return value


def load_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "")
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        llama_model=os.getenv("LLAMA_MODEL") or DEFAULT_MODEL,
        rate_limit_per_minute=_non_negative_int("RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE),
        metrics_token=os.getenv("METRICS_TOKEN") or None,
        cors_origins=tuple(origin.strip().rstrip("/") for origin in origins.split(",") if origin.strip()),
    )
