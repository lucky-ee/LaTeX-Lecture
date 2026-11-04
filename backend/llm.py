"""OpenRouter call that turns transcribed text into an Interpretation."""

import asyncio
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

# One retry for failures that are usually transient: timeouts, dropped
# connections and upstream 5xx. Rate limits (429) and auth errors are not retried.
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5


class LLMError(Exception):
    """The upstream call failed.

    `outcome` is the llm_requests_total label it was counted under; `status` is
    the upstream HTTP status code, if the upstream answered at all.
    """

    def __init__(self, outcome: str, status: int | None = None):
        super().__init__(outcome)
        self.outcome = outcome
        self.status = status


def _upstream_status(error: Exception) -> int | None:
    return error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None


def _is_retryable(error: httpx.HTTPError) -> bool:
    if isinstance(error, httpx.TransportError):  # includes timeouts and connection errors
        return True
    status = _upstream_status(error)
    return status is not None and status >= 500


def _failed(outcome: str, error: Exception, attempt: int = 1) -> LLMError:
    LLM_REQUESTS.labels(outcome=outcome).inc()
    status = _upstream_status(error)
    log = logger.error if status in (401, 403) else logger.warning
    log(
        "LLM interpretation failed: outcome=%s error=%s status=%s attempt=%d prompt=%s%s",
        outcome, type(error).__name__, status, attempt, PROMPT_VERSION,
        " (check OPENROUTER_API_KEY)" if status in (401, 403) else "",
    )
    return LLMError(outcome, status)


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
    """Ask the model to interpret `text`. Raises LLMError on any upstream or parsing failure.

    Each attempt is counted and timed separately, so a retried call shows up as
    one failure plus one success in the metrics.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        llm_started = time.perf_counter()
        try:
            with time_stage("upstream_request"):
                response = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json=_request_body(settings, text),
                )
                response.raise_for_status()
            break
        except httpx.HTTPError as error:
            outcome = "timeout" if isinstance(error, httpx.TimeoutException) else "http_error"
            failure = _failed(outcome, error, attempt)
            if attempt < MAX_ATTEMPTS and _is_retryable(error):
                await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
                continue
            raise failure from error
    LLM_LATENCY.observe(time.perf_counter() - llm_started)

    try:
        with time_stage("response_parse"):
            content = response.json()["choices"][0]["message"]["content"]
            result = Interpretation.model_validate_json(content)
    except (ValidationError, ValueError, KeyError, IndexError, TypeError) as error:
        raise _failed("invalid_response", error) from error
    LLM_REQUESTS.labels(outcome="success").inc()
    return result
