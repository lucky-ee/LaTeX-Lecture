# wispr-lecture

A voice-first note-taking prototype for university mathematics lectures. Dictate a note (for example with [Wispr Flow](https://wisprflow.ai)) and the app turns spoken math into rendered notation:

> "for all epsilon greater than zero there exists delta greater than zero"
> → ∀ε > 0 ∃δ > 0

When the spoken math is ambiguous (does "1 + x² over 2" mean `(1 + x²)/2` or `1 + x²/2`?), the app shows up to three possible readings and lets you choose.

_Independent prototype, not affiliated with Wispr._

## How it works

```
frontend (React + Vite)  ──POST /api/interpret──▶  backend (FastAPI)  ──▶  Llama 3.3 70B via OpenRouter
        │                                                │
        └── renders math with KaTeX                      └── common patterns like (x^2)/2 are handled
                                                             locally, without calling the LLM
```

- **`frontend/`**: React app. Sends each note to the backend and renders the returned LaTeX with KaTeX. If the backend fails, the original text is kept.
- **`backend/`**: FastAPI app. Splits a note into `text` and `math` segments, each with one or more LaTeX readings. It handles simple notation itself and asks an LLM for everything else.

## Running locally

You need **Python 3.12**, **Node.js 22+**, and an [OpenRouter](https://openrouter.ai) API key.

### 1. Backend (port 8000)

```sh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export OPENROUTER_API_KEY=sk-or-...   # required for anything beyond simple notation
uvicorn main:app --reload --port 8000
```

### 2. Frontend (port 5173)

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server forwards `/api` requests to the backend on port 8000.

### Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | For LLM calls | none | Authenticates with OpenRouter. Without it, simple notation still works and other notes return a 503. |
| `LLAMA_MODEL` | No | `meta-llama/llama-3.3-70b-instruct` | The OpenRouter model to use. |

The backend reads these from the shell environment. It does not load a `.env` file.

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Returns `{"ok": true}`. |
| `POST /api/interpret` | Body: `{"text": "..."}` (1–2000 characters). Returns `{"segments": [{"kind": "text" \| "math", "content": "...", "readings": ["<latex>", ...]}]}`. Returns 502 if the LLM fails or replies with something unusable. |
| `GET /metrics` | Prometheus metrics (see below). |

## Metrics

The backend exposes Prometheus metrics at `/metrics`:

- **`http_request_duration_seconds`**: duration and count of every HTTP request, by endpoint.
- **`llm_request_duration_seconds`**: how long OpenRouter takes to answer, recorded only when it replies.
- **`llm_requests_total{outcome=...}`**: every LLM call, by outcome: `success`, `timeout`, `http_error`, or `invalid_response`.

## Tests

```sh
cd backend
source .venv/bin/activate
python -m unittest discover tests -v
```

The tests mock OpenRouter, so they don't need an API key or network access. GitHub Actions runs them on every pull request and on every push to `main`.

## Contributing

- Branch from an up-to-date `main` using a `type/description` name, e.g. `feat/...`, `fix/...`, `perf/...`, `ci/...`.
- Keep each PR to one change, and include tests for backend changes.
- Never commit `.venv/`, `node_modules/`, `__pycache__/`, or `.env` files. They're in `.gitignore`.
