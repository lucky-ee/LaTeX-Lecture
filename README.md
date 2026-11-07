# LaTeX Lecture

**Voice-first mathematical note-taking for university lectures.**

LaTeX Lecture turns dictated mathematical language into readable, KaTeX-rendered notation. It accepts text transcribed by a tool such as [Wispr Flow](https://wisprflow.ai/), identifies mathematical expressions, and presents alternative interpretations when the wording is ambiguous.

For example:

> “For all epsilon greater than zero, there exists delta greater than zero.”
>
> **Rendered notation:** ∀ε > 0, ∃δ > 0

The goal is to preserve what was dictated—not to solve problems, change a mathematical claim, or silently fill in missing assumptions.

> **Project status:** Active prototype. Core note interpretation, a React interface, automated backend tests, and Prometheus instrumentation are implemented. Per-client rate limiting, upstream retries, optional `/metrics` authentication, and configurable CORS are implemented. Authentication, persistent note storage, and full production deployment hardening are not yet implemented.
>
> Independent project; not affiliated with or endorsed by Wispr.

## Features

- **Speech-to-notation workflow:** Accepts already-transcribed text from Wispr Flow or manual entry; this app does not perform speech recognition itself.
- **Math-aware interpretation:** Separates ordinary prose from mathematical expressions and returns LaTeX readings for supported mathematical notation.
- **Ambiguity resolution:** Presents up to three distinct mathematical readings when an expression has multiple plausible meanings.
- **Fast path for known notation:** Recognizes a small set of patterns locally without an LLM call.
- **Graceful failure handling:** Preserves the original transcription in the frontend if AI interpretation is unavailable.
- **Observable backend:** Exposes request and LLM metrics in Prometheus format.

## Tech Stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite | Input, note display, interpretation choices |
| Math rendering | KaTeX | Renders LaTeX into mathematical notation |
| Backend | Python, FastAPI, Pydantic | Validates input and returns structured interpretations |
| Model integration | Llama 3.3 70B via OpenRouter (configurable) | Interprets text not handled by local rules |
| HTTP client | HTTPX (`AsyncClient`) | Reuses connections for nonblocking upstream calls |
| Observability | Prometheus client, FastAPI Instrumentator | Request, latency, and LLM outcome metrics |
| Testing and CI | `unittest`, GitHub Actions | Backend regression checks on PRs and pushes to `main` |

## Architecture

```mermaid
flowchart TD
    A[Wispr Flow transcription or typed text] --> B[React frontend]
    B -->|POST /api/interpret| C[FastAPI backend]
    C --> D{Known mathematical notation?}
    D -->|Yes| E[Local interpretation]
    D -->|No| F[OpenRouter / Llama]
    E --> G[Validated segments and LaTeX readings]
    F --> G
    G -->|JSON| B
    B --> H[KaTeX rendering and reading selection]
    C -.-> M[GET /metrics: Prometheus instrumentation]
```

The backend receives **text, not audio**. For requests that require the model, it sends the transcription to OpenRouter and validates the returned structured interpretation. The frontend renders math locally with KaTeX. If the model fails, the note remains available as its original text.

## Getting Started

### Prerequisites

- Python **3.12**
- Node.js **22.12+** and npm (required by the project's Vite 8 toolchain; Node 20.19+ is also supported by Vite 8)
- An [OpenRouter API key](https://openrouter.ai/) for LLM-backed interpretations

Commands below assume you are in the repository root and use a macOS/Linux shell.

### 1. Start the Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Required: every interpretation request calls the model.
export OPENROUTER_API_KEY="your-openrouter-api-key"

uvicorn main:app --reload --port 8000
```

The API should be available at **http://localhost:8000**.

Check the health endpoint:

```bash
curl http://localhost:8000/api/health
# {"ok":true}
```

### 2. Start the Frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**.

In local development, Vite forwards `/api` requests to the backend running on port 8000.

`npm ci` installs the versions recorded in `frontend/package-lock.json`. Keep this lockfile committed; do not commit `node_modules/`.

### 3. Try an Interpretation

With the backend running and `OPENROUTER_API_KEY` set, submit an ambiguous expression:

```bash
curl -X POST http://localhost:8000/api/interpret \
  -H 'Content-Type: application/json' \
  -d '{"text":"(1 + x^2) / 2"}'
```

Example response:

```json
{
  "segments": [
    {
      "kind": "math",
      "content": "(1 + x^2) / 2",
      "readings": [
        "\\frac{1+x^2}{2}",
        "1+\\frac{x^2}{2}"
      ]
    }
  ]
}
```

Every request is interpreted by the configured OpenRouter model, so this needs `OPENROUTER_API_KEY`. Model output can vary; this shows the expected shape for an ambiguous fraction.

## Configuration

The backend reads configuration directly from environment variables. It does not automatically load `.env` files.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | For model-backed requests | Unset | Credential for OpenRouter; keep it server-side and secret |
| `LLAMA_MODEL` | No | `meta-llama/llama-3.3-70b-instruct` | Model identifier used for interpretation |
| `RATE_LIMIT_PER_MINUTE` | No | `20` | Maximum `POST /api/interpret` requests per client IP per minute; `0` disables the limit |
| `METRICS_TOKEN` | Recommended in production | Unset | When set, `GET /metrics` requires `Authorization: Bearer <token>`; when unset, it is open |
| `CORS_ORIGINS` | Only for a cross-origin frontend | Unset | Comma-separated browser origins allowed to call the API, e.g. `https://app.example.com`; unset means same-origin only |

Configuration is read once when the backend starts, so restart it after changing these variables. If `OPENROUTER_API_KEY` is not set, the backend logs a warning at startup and valid interpretation requests return **503 Service Unavailable**.

**Never commit API keys, `.env` files, or other credentials.** In a deployed environment, use your hosting provider's secret-management mechanism.

## API Reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Returns `{"ok": true}` |
| `POST` | `/api/interpret` | Validates a transcription and returns text/math segments with LaTeX readings |
| `GET` | `/metrics` | Exposes metrics in Prometheus text format |

### POST `/api/interpret`

**Request**

```json
{
  "text": "integral from a to b of x squared dx"
}
```

The `text` field is required, with an input limit of **1–2,000 characters**. Whitespace-only notes are rejected.

**Response shape**

```json
{
  "segments": [
    {
      "kind": "text",
      "content": "Original prose, punctuation, and spacing",
      "readings": []
    },
    {
      "kind": "math",
      "content": "Original mathematical wording",
      "readings": ["\\int_a^b x^2\\,dx"]
    }
  ]
}
```

This shows the schema, not a guaranteed response for any particular model-generated input. `text` segments have no LaTeX readings; `math` segments may contain several alternatives.

| HTTP status | Meaning |
| --- | --- |
| `200` | Interpretation returned |
| `422` | Invalid input, missing field, or blank transcription |
| `429` | Per-client rate limit exceeded; the `Retry-After` header gives the wait in seconds |
| `502` | Upstream model call failed or the model response was unusable |
| `503` | OpenRouter key missing, or OpenRouter itself is rate limiting the backend |

Upstream timeouts, connection errors, and 5xx responses are retried once after a short delay. Upstream 429 and authentication errors are not retried; a 401/403 from OpenRouter is logged as an error so a bad API key is easy to spot.

The frontend retains the user's original note when interpretation fails; HTTP errors are not silently converted into successful API responses.

## Observability

Prometheus-format metrics are available at **`GET /metrics`**.

| Metric | Type | Measures |
| --- | --- | --- |
| `http_requests_total` | Counter | HTTP request count by handler, method, and grouped status |
| `http_request_duration_seconds` | Histogram | Backend request duration |
| `llm_request_duration_seconds` | Histogram | Time spent waiting for a model response, including responses later found unusable |
| `llm_requests_total{outcome="..."}` | Counter | LLM call attempts categorized by `success`, `timeout`, `http_error`, or `invalid_response`; a retried call counts each attempt |
| `rate_limited_requests_total` | Counter | Interpretation requests rejected with 429 by the per-client rate limit |

Open the app at http://localhost:5173 to view the **Processing time** table. It refreshes every two seconds and shows cumulative seconds, average seconds per attempt, attempts, and errors for each stage. Totals include failed attempts and reset when the backend restarts. The same data is available as JSON at `GET /api/metrics/stages`.

Stage metrics are defined in `backend/metrics.py` and exposed at `/metrics`:

- `interpret_stage_runs_total{stage, outcome}` counts completed stage attempts.
- `interpret_stage_duration_seconds{stage, outcome}` measures duration, including failures.
- Stages: `input_check` (whitespace validation), `upstream_request` (request preparation, network wait, HTTP status check), `response_parse` (JSON and schema validation), and `latex_repair` (repair or empty-result fallback).
- Outcomes: `success` and `error`. Skipped stages do not increment.

Average seconds per executed stage over five minutes:

```promql
sum by (stage) (rate(interpret_stage_duration_seconds_sum[5m]))
/
sum by (stage) (rate(interpret_stage_duration_seconds_count[5m]))
```

Estimated p95 per stage:

```promql
histogram_quantile(0.95,
  sum by (stage, le) (rate(interpret_stage_duration_seconds_bucket[5m]))
)
```

These measure backend processing. Existing HTTP metrics cover whole requests, including FastAPI validation and serialization. Desktop transcription, browser network time, and KaTeX rendering need separate client instrumentation. Stage averages describe only requests executing that stage.

The LLM duration histogram does not currently record timeouts or upstream HTTP/connection failures.

```bash
curl http://localhost:8000/metrics
```

**Security:** set `METRICS_TOKEN` in production so `/metrics` requires `Authorization: Bearer <token>` (Prometheus supports this via `authorization` in its scrape config). `GET /api/metrics/stages` stays open because the frontend's **Processing time** panel reads it.

The current instrumentation exposes measurements; it does not itself provide a hosted Prometheus server, dashboard, alerting system, or load-testing infrastructure.

## Testing and Continuous Integration

From the repository root:

```bash
cd backend
source .venv/bin/activate
python -m unittest discover tests -v
```

Backend tests use mocked OpenRouter responses, so the test suite does not require an API key or live provider access.

Tests cover interpretation, rendering-related LaTeX handling, metrics, error outcomes, asynchronous request behavior, and HTTP-client lifecycle.

### Prompt evaluation

Unit tests mock the model, so they cannot tell whether a prompt change makes output better or worse. `backend/evals/prompt_eval.py` sends the cases in `backend/evals/cases.json` to the real model and reports schema failures, how often `repair_latex` was needed, KaTeX render rate, prompt-injection cases the model obeyed, and how much of the input survives in the output. It makes billed API calls and is not run in CI.

```bash
cd backend
python evals/prompt_eval.py --reps 3                    # current prompt
python evals/prompt_eval.py --system-prompt-file old.txt --no-delimiters --label old
```

Run it before and after any change to `prompts.py`, and bump `PROMPT_VERSION`. KaTeX rendering checks validity, not correctness: a reading can render and still be wrong.

The GitHub Actions workflow in `.github/workflows/backend-tests.yml` runs backend tests on:

- Every pull request
- Every push to `main`

The workflow installs dependencies in Python 3.12 and runs the backend test suite.

**Branch protection must be configured separately** to require passing checks before merging.

## Repository Structure

```text
wispr-lecture/
├── backend/
│   ├── main.py                 # FastAPI app and routes
│   ├── llm.py                  # OpenRouter call, error handling, LLM metrics
│   ├── prompts.py              # System prompt and its version
│   ├── schemas.py              # Request/response models
│   ├── settings.py             # Environment configuration
│   ├── latex.py                # Repair of LaTeX mangled by JSON escaping
│   ├── evals/                  # Prompt evaluation against the real model (billed; not run in CI)
│   ├── metrics.py              # Prometheus metrics and stage timing
│   ├── requirements.txt        # Python dependencies
│   └── tests/                  # Backend tests
├── frontend/                   # React + TypeScript + Vite app
│   ├── package.json
│   └── package-lock.json
├── .github/
│   └── workflows/
│       └── backend-tests.yml   # Backend CI
├── .gitignore
└── README.md
```

## Deployment and Security

LaTeX Lecture is currently an actively developed prototype. The following capabilities are required or recommended before exposing the application to public production traffic.

### Access Control and Abuse Prevention

`POST /api/interpret` is rate limited per client IP (`RATE_LIMIT_PER_MINUTE`). The limiter is in memory, so each worker process or replica keeps its own counts; move it to a shared store such as Redis before scaling out. Behind a reverse proxy, run uvicorn with `--proxy-headers` and `--forwarded-allow-ips` so the limit applies to real client IPs rather than the proxy's.

Still to do: authentication if accounts are introduced, and per-user AI usage quotas.

### Data Privacy

Treat lecture transcriptions as potentially sensitive user data. AI-backed requests are sent to OpenRouter for processing.

Production deployment should establish appropriate privacy disclosures, data retention policies, and safeguards against logging sensitive content.

### Secrets and Transport Security

Use HTTPS for communication between clients and the backend.

Store credentials using environment variables or a managed secrets service. Never expose the OpenRouter API key in frontend code.

### Availability and Scalability

The backend uses a shared asynchronous HTTP client to improve concurrency and reuse upstream connections.

Future production improvements include:

- Bounded concurrency for LLM requests
- Shared (multi-process) rate limiting and per-user usage quotas
- Load testing to establish throughput and latency targets
- Horizontal scaling behind a load balancer
- Backpressure when the upstream provider is slow or rate limiting

Asynchronous HTTP processing improves server efficiency but does not eliminate upstream provider rate limits.

### Monitoring

Set `METRICS_TOKEN` to restrict `/metrics`, and configure external collection, dashboards, and alerts.

Use metrics to track request latency, error rates, LLM response times, and upstream failure categories.

### Persistent Storage

The current implementation does not provide persistent lecture note storage.

A database, data retention policy, and backup strategy should be introduced if cross-session saved notes become a supported feature.

### Production Deployment

Serve a production frontend build and run the backend using an appropriate production server configuration or managed hosting platform.

The development server command `uvicorn --reload` is intended for local development only.
