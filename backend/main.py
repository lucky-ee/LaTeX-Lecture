import logging
import math
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from latex import repair_latex
from llm import LLMError, interpret_with_llm
from local_notation import known_wispr_notation
from metrics import RATE_LIMITED, stage_snapshot, time_stage
from prometheus_fastapi_instrumentator import Instrumentator
from rate_limit import RateLimiter
from schemas import Interpretation, NoteRequest, Segment
from settings import load_settings

logger = logging.getLogger(__name__)

settings = load_settings()
rate_limiter = RateLimiter(settings.rate_limit_per_minute)

# One client for the whole app, so connections to OpenRouter are reused across requests.
# Created at startup and closed at shutdown by `lifespan`.
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global http_client
    if not settings.llm_configured:
        logger.warning("OPENROUTER_API_KEY is not set; only locally recognized notation will work.")
    http_client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
    try:
        yield
    finally:
        await http_client.aclose()
        http_client = None


async def enforce_rate_limit(request: Request) -> None:
    # Behind a reverse proxy, run uvicorn with --proxy-headers (and --forwarded-allow-ips)
    # so request.client is the real client rather than the proxy.
    client = request.client.host if request.client else "unknown"
    retry_after = rate_limiter.check(client)
    if retry_after is not None:
        RATE_LIMITED.inc()
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again shortly.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


async def require_metrics_token(authorization: str | None = Header(default=None)) -> None:
    if settings.metrics_token is None:
        return
    expected = f"Bearer {settings.metrics_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized.", headers={"WWW-Authenticate": "Bearer"})


app = FastAPI(title="Wispr Lecture API", lifespan=lifespan)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
Instrumentator().instrument(app).expose(
    app, include_in_schema=False, dependencies=[Depends(require_metrics_token)]
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/metrics/stages")
def processing_metrics():
    return {"stages": stage_snapshot()}


@app.post("/api/interpret", response_model=Interpretation, dependencies=[Depends(enforce_rate_limit)])
async def interpret(request: NoteRequest):
    with time_stage("input_check"):
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Note cannot be blank.")

    # Flow/Canto performs speech transcription in the user's desktop app.
    # The backend receives only its resulting text, not raw microphone audio.
    with time_stage("local_match"):
        quick_result = known_wispr_notation(text)
    if quick_result is not None:
        return quick_result

    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="AI interpretation is not configured.")
    if http_client is None:
        raise RuntimeError("HTTP client not started; run the app through its lifespan.")

    try:
        result = await interpret_with_llm(http_client, settings, text)
    except LLMError as error:
        if error.status == 429:
            raise HTTPException(status_code=503, detail="AI service is busy. Try again shortly.") from error
        raise HTTPException(status_code=502, detail="AI interpretation failed.") from error

    with time_stage("latex_repair"):
        if not result.segments:
            return Interpretation(segments=[Segment(kind="text", content=text, readings=[])])
        for segment in result.segments:
            segment.readings = [repair_latex(reading) for reading in segment.readings]
        return result
