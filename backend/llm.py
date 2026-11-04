"""OpenRouter call that turns transcribed text into an Interpretation."""

import logging
import time

import httpx
from metrics import LLM_LATENCY, LLM_REQUESTS, time_stage
from prompts import PROMPT_VERSION, SYSTEM_PROMPT
from pydantic import ValidationError
from schemas import Interpretation
from settings import Settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(Exception):
    """The upstream call failed; `outcome` is the llm_requests_total label it was counted under."""

    def __init__(self, outcome: str):
        super().__init__(outcome)
        self.outcome = outcome


def _failed(outcome: str, error: Exception) -> LLMError:
    LLM_REQUESTS.labels(outcome=outcome).inc()
    status = getattr(getattr(error, "response", None), "status_code", None)
    logger.warning(
        "LLM interpretation failed: outcome=%s error=%s status=%s prompt=%s",
        outcome, type(error).__name__, status, PROMPT_VERSION,
    )
    return LLMError(outcome)


def _request_body(settings: Settings, text: str) -> dict:
    return {
        "model": settings.llama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 2500,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "interpretation",
                "strict": True,
                "schema": Interpretation.model_json_schema(),
            },
        },
        "provider": {"require_parameters": True},
    }


async def interpret_with_llm(client: httpx.AsyncClient, settings: Settings, text: str) -> Interpretation:
    """Ask the model to interpret `text`. Raises LLMError on any upstream or parsing failure."""
    llm_started = time.perf_counter()
    try:
        with time_stage("upstream_request"):
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json=_request_body(settings, text),
            )
            response.raise_for_status()
    except httpx.TimeoutException as error:
        raise _failed("timeout", error) from error
    except httpx.HTTPError as error:
        raise _failed("http_error", error) from error
    LLM_LATENCY.observe(time.perf_counter() - llm_started)

    try:
        with time_stage("response_parse"):
            content = response.json()["choices"][0]["message"]["content"]
            result = Interpretation.model_validate_json(content)
    except (ValidationError, ValueError, KeyError, IndexError, TypeError) as error:
        raise _failed("invalid_response", error) from error
    LLM_REQUESTS.labels(outcome="success").inc()
    return result
