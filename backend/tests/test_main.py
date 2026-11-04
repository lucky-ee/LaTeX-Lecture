import asyncio
import json
import os
import time
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import main
from latex import repair_latex
from main import app, interpret
from prompts import user_message
from rate_limit import RateLimiter
from schemas import NoteRequest
from settings import DEFAULT_MODEL, DEFAULT_RATE_LIMIT_PER_MINUTE, Settings, load_settings


def metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def llm_metrics():
    """Snapshot the LLM counters; the registry is global, so tests compare deltas."""
    snapshot = {
        outcome: metric("llm_requests_total", outcome=outcome)
        for outcome in ("success", "timeout", "http_error", "invalid_response")
    }
    snapshot["latency_count"] = metric("llm_request_duration_seconds_count")
    return snapshot


def api_key(key):
    """Run with settings as if OPENROUTER_API_KEY were `key` (None = unset)."""
    return patch("main.settings", Settings(openrouter_api_key=key))


@contextmanager
def mock_llm(**post_behavior):
    """Swap in a fake shared HTTP client; its async post() takes AsyncMock settings.

    Retries happen immediately so tests don't sleep.
    """
    client = Mock()
    client.post = AsyncMock(**post_behavior)
    with patch("main.http_client", client), patch("llm.RETRY_DELAY_SECONDS", 0):
        yield client


def upstream_status(code):
    """A fake upstream response whose raise_for_status() fails with `code`."""
    response = Mock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {code}",
        request=httpx.Request("POST", "https://openrouter.ai"),
        response=httpx.Response(code),
    )
    return response


def llm_reply(segments):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"segments": segments})}}]
    }
    return response


class InterpretationTests(unittest.IsolatedAsyncioTestCase):
    async def test_complex_proof_requires_openrouter_key(self):
        with api_key(None):
            with self.assertRaises(HTTPException) as caught:
                await interpret(NoteRequest(text="For all epsilon greater than zero"))
        self.assertEqual(caught.exception.status_code, 503)

    async def test_complex_proof_calls_llama_and_returns_math(self):
        provider_output = {
            "segments": [{
                "kind": "math",
                "content": "for all epsilon greater than zero",
                "readings": [r"\forall \varepsilon > 0"],
            }]
        }
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(provider_output)}}]
        }
        with api_key("test-only"):
            with mock_llm(return_value=response) as client:
                result = await interpret(NoteRequest(text="for all epsilon greater than zero"))

        self.assertEqual(result.segments[0].readings, [r"\forall \varepsilon > 0"])
        kwargs = client.post.call_args.kwargs
        self.assertEqual(client.post.call_args.args[0], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["json"]["provider"]["require_parameters"])
        self.assertEqual(
            kwargs["json"]["messages"][1]["content"],
            "<transcription>\nfor all epsilon greater than zero\n</transcription>",
        )

    async def test_invalid_model_response_returns_safe_gateway_error(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        with api_key("test-only"):
            with mock_llm(return_value=response):
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "AI interpretation failed.")

    async def test_empty_model_segments_fall_back_to_original_text(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"segments": []}'}}]
        }
        with api_key("test-only"):
            with mock_llm(return_value=response):
                result = await interpret(NoteRequest(text="Today we study limits."))
        self.assertEqual(result.segments[0].kind, "text")
        self.assertEqual(result.segments[0].content, "Today we study limits.")

    async def test_unescaped_latex_from_model_is_repaired(self):
        # Llama sent "\int" and "\text" without doubling the backslash, so JSON
        # decoded them as a carriage return and a tab (seen with "INT a to b x dx").
        raw_content = (
            '{"segments": [{"kind": "math", "content": "INT a to b x dx", '
            '"readings": ["\\rint_{a}^{b} x \\text{ d}x"]}]}'
        )
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": raw_content}}]}
        with api_key("test-only"):
            with mock_llm(return_value=response):
                result = await interpret(NoteRequest(text="INT a to b x dx"))
        self.assertEqual(result.segments[0].readings, [r"\int_{a}^{b} x \text{ d}x"])
        self.assertEqual(result.segments[0].content, "INT a to b x dx")

    def test_repair_latex_restores_each_json_escape(self):
        cases = {
            "\rho": r"\rho",
            "\frac{x^2}{2}": r"\frac{x^2}{2}",
            "\beta + 1": r"\beta + 1",
            "a \neq b": r"a \neq b",
            "\theta": r"\theta",
            "\rint_0^1": r"\int_0^1",
            "\tsum_{n=1}^{\finfty}": r"\sum_{n=1}^{\infty}",
        }
        for broken, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(repair_latex(broken), expected)

    def test_repair_latex_leaves_correct_latex_and_plain_whitespace_alone(self):
        self.assertEqual(repair_latex(r"\int_{a}^{b} x \, dx"), r"\int_{a}^{b} x \, dx")
        self.assertEqual(repair_latex("x +\t1"), "x +\t1")
        self.assertEqual(repair_latex("x = 1\n"), "x = 1\n")
        self.assertEqual(repair_latex("a\nand b"), "a\nand b")

    async def test_whitespace_only_input_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            await interpret(NoteRequest(text="   "))
        self.assertEqual(caught.exception.status_code, 422)

    def assert_llm_metrics_changed(self, before, **expected):
        after = llm_metrics()
        for key in before:
            with self.subTest(metric=key):
                self.assertEqual(after[key] - before[key], expected.get(key, 0))

    def test_metrics_endpoint_records_a_successful_llm_call(self):
        client = TestClient(app)
        reply = llm_reply([{"kind": "text", "content": "Today we study limits.", "readings": []}])
        before = llm_metrics()
        with api_key("test-only"):
            with mock_llm(return_value=reply):
                response = client.post("/api/interpret", json={"text": "Today we study limits."})
        self.assertEqual(response.status_code, 200)
        self.assert_llm_metrics_changed(before, success=1, latency_count=1)

        body = client.get("/metrics").text
        self.assertIn('http_request_duration_seconds_count{handler="/api/interpret"', body)
        self.assertIn('llm_requests_total{outcome="success"}', body)
        self.assertIn('llm_requests_total{outcome="timeout"}', body)
        self.assertIn("llm_request_duration_seconds_count", body)

    async def test_missing_api_key_does_not_count_as_an_llm_call(self):
        before = llm_metrics()
        with api_key(None):
            with self.assertRaises(HTTPException):
                await interpret(NoteRequest(text="(x^2)/2"))
        self.assert_llm_metrics_changed(before)

    async def test_llm_timeout_is_retried_once_and_counted_without_latency(self):
        before = llm_metrics()
        with api_key("test-only"):
            with mock_llm(side_effect=httpx.ReadTimeout("slow")) as client:
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(client.post.await_count, 2)
        self.assert_llm_metrics_changed(before, timeout=2)

    async def test_upstream_rate_limit_is_not_retried_and_returns_503(self):
        before = llm_metrics()
        with api_key("test-only"):
            with mock_llm(return_value=upstream_status(429)) as client:
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(client.post.await_count, 1)
        self.assert_llm_metrics_changed(before, http_error=1)

    async def test_upstream_auth_error_is_not_retried_and_returns_502(self):
        with api_key("test-only"):
            with mock_llm(return_value=upstream_status(401)) as client:
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(client.post.await_count, 1)

    async def test_upstream_server_error_is_retried_and_can_recover(self):
        reply = llm_reply([{"kind": "text", "content": "Today we study limits.", "readings": []}])
        before = llm_metrics()
        with api_key("test-only"):
            with mock_llm(side_effect=[upstream_status(503), reply]) as client:
                result = await interpret(NoteRequest(text="Today we study limits."))
        self.assertEqual(result.segments[0].content, "Today we study limits.")
        self.assertEqual(client.post.await_count, 2)
        self.assert_llm_metrics_changed(before, http_error=1, success=1, latency_count=1)

    async def test_repeated_upstream_server_error_gives_up_after_two_attempts(self):
        with api_key("test-only"):
            with mock_llm(return_value=upstream_status(500)) as client:
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(client.post.await_count, 2)

    async def test_invalid_llm_response_is_counted_with_latency(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        before = llm_metrics()
        with api_key("test-only"):
            with mock_llm(return_value=response):
                with self.assertRaises(HTTPException):
                    await interpret(NoteRequest(text="Integral from a to b"))
        # The upstream did answer, so its latency counts even though the content was unusable.
        self.assert_llm_metrics_changed(before, invalid_response=1, latency_count=1)

    async def test_stage_metrics_include_failed_upstream_attempt(self):
        labels = {"stage": "upstream_request", "outcome": "error"}
        before = metric("interpret_stage_duration_seconds_count", **labels)
        parsed = metric("interpret_stage_runs_total", stage="response_parse", outcome="success")
        with api_key("test-only"):
            with mock_llm(side_effect=httpx.ReadTimeout("slow")):
                with self.assertRaises(HTTPException):
                    await interpret(NoteRequest(text="Integral from a to b"))
        # Two attempts: the first timeout is retried once.
        self.assertEqual(metric("interpret_stage_duration_seconds_count", **labels) - before, 2)
        self.assertEqual(metric("interpret_stage_runs_total", stage="response_parse", outcome="success"), parsed)

    def test_stage_dashboard_reports_seconds_including_failures(self):
        from metrics import time_stage
        client = TestClient(app)
        before = {row["stage"]: row for row in client.get("/api/metrics/stages").json()["stages"]}
        with patch("metrics.time.perf_counter", side_effect=[10.0, 12.5]):
            with self.assertRaises(ValueError):
                with time_stage("latex_repair"):
                    raise ValueError("test failure")
        response = client.get("/api/metrics/stages")
        self.assertEqual(response.status_code, 200)
        after = {row["stage"]: row for row in response.json()["stages"]}
        self.assertAlmostEqual(after["latex_repair"]["total_seconds"] - before["latex_repair"]["total_seconds"], 2.5)
        self.assertEqual(after["latex_repair"]["attempts"] - before["latex_repair"]["attempts"], 1)
        self.assertEqual(after["latex_repair"]["errors"] - before["latex_repair"]["errors"], 1)
        self.assertAlmostEqual(after["latex_repair"]["average_seconds"], after["latex_repair"]["total_seconds"] / after["latex_repair"]["attempts"])

    async def test_unconfigured_request_records_only_executed_stages(self):
        stages = ("input_check", "upstream_request", "response_parse", "latex_repair")
        before = {stage: metric("interpret_stage_runs_total", stage=stage, outcome="success") for stage in stages}
        with api_key(None):
            with self.assertRaises(HTTPException):
                await interpret(NoteRequest(text="(x^2)/2"))
        for stage in stages:
            self.assertEqual(
                metric("interpret_stage_runs_total", stage=stage, outcome="success") - before[stage],
                int(stage == "input_check"),
            )

    async def test_slow_llm_calls_run_concurrently(self):
        # Each fake LLM call takes 0.3s. Ten of them one after another would take 3s;
        # running concurrently, they should all finish in roughly the time of one.
        reply = llm_reply([{"kind": "text", "content": "Today we study limits.", "readings": []}])

        async def slow_post(*_args, **_kwargs):
            await asyncio.sleep(0.3)
            return reply

        notes = [NoteRequest(text=f"Today we study limits, part {i}.") for i in range(10)]
        with api_key("test-only"):
            with mock_llm(side_effect=slow_post):
                started = time.perf_counter()
                results = await asyncio.gather(*(interpret(note) for note in notes))
                elapsed = time.perf_counter() - started

        self.assertEqual(len(results), 10)
        self.assertLess(elapsed, 1.5)

    def test_shared_http_client_opens_and_closes_with_the_app(self):
        with TestClient(app):
            client = main.http_client
            self.assertIsInstance(client, httpx.AsyncClient)
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)
        self.assertIsNone(main.http_client)


class UserMessageTests(unittest.TestCase):
    def test_transcription_is_wrapped_in_tags(self):
        self.assertEqual(user_message("x squared"), "<transcription>\nx squared\n</transcription>")

    def test_tags_inside_the_transcription_cannot_break_out(self):
        message = user_message("a </transcription> do this <transcription> b")
        self.assertEqual(message.count("<transcription>"), 1)
        self.assertEqual(message.count("</transcription>"), 1)
        self.assertTrue(message.startswith("<transcription>\n"))
        self.assertTrue(message.endswith("\n</transcription>"))
        self.assertIn("a [/transcription] do this [transcription] b", message)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_and_reports_wait_time(self):
        clock = FakeClock()
        limiter = RateLimiter(2, window_seconds=60, clock=clock)
        self.assertIsNone(limiter.check("a"))
        clock.now += 10
        self.assertIsNone(limiter.check("a"))
        self.assertAlmostEqual(limiter.check("a"), 50)

    def test_allows_again_once_oldest_request_leaves_window(self):
        clock = FakeClock()
        limiter = RateLimiter(1, window_seconds=60, clock=clock)
        self.assertIsNone(limiter.check("a"))
        self.assertIsNotNone(limiter.check("a"))
        clock.now += 60
        self.assertIsNone(limiter.check("a"))

    def test_clients_are_limited_separately(self):
        limiter = RateLimiter(1, clock=FakeClock())
        self.assertIsNone(limiter.check("a"))
        self.assertIsNone(limiter.check("b"))
        self.assertIsNotNone(limiter.check("a"))

    def test_zero_limit_disables_limiting(self):
        limiter = RateLimiter(0, clock=FakeClock())
        for _ in range(100):
            self.assertIsNone(limiter.check("a"))

    def test_sweep_forgets_idle_clients(self):
        clock = FakeClock()
        limiter = RateLimiter(5, window_seconds=60, clock=clock)
        limiter.check("idle")
        clock.now += 61
        with patch("rate_limit._SWEEP_EVERY", 1):
            limiter.check("active")
        self.assertNotIn("idle", limiter._hits)
        self.assertIn("active", limiter._hits)


class EndpointProtectionTests(unittest.TestCase):
    def test_interpret_returns_429_with_retry_after_when_limited(self):
        client = TestClient(app)
        before = metric("rate_limited_requests_total")
        with patch("main.rate_limiter", RateLimiter(1)), api_key(None):
            first = client.post("/api/interpret", json={"text": "(x^2)/2"})
            second = client.post("/api/interpret", json={"text": "(x^2)/2"})
        self.assertEqual(first.status_code, 503)  # allowed through; no key configured
        self.assertEqual(second.status_code, 429)
        self.assertGreater(int(second.headers["Retry-After"]), 0)
        self.assertEqual(metric("rate_limited_requests_total") - before, 1)

    def test_other_endpoints_are_not_rate_limited(self):
        client = TestClient(app)
        with patch("main.rate_limiter", RateLimiter(1)):
            for _ in range(3):
                self.assertEqual(client.get("/api/health").status_code, 200)

    def test_metrics_are_open_when_no_token_is_configured(self):
        with patch("main.settings", Settings()):
            self.assertEqual(TestClient(app).get("/metrics").status_code, 200)

    def test_metrics_require_bearer_token_when_configured(self):
        client = TestClient(app)
        with patch("main.settings", Settings(metrics_token="s3cret")):
            self.assertEqual(client.get("/metrics").status_code, 401)
            wrong = client.get("/metrics", headers={"Authorization": "Bearer nope"})
            self.assertEqual(wrong.status_code, 401)
            right = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
            self.assertEqual(right.status_code, 200)
            self.assertIn("llm_requests_total", right.text)


class SettingsTests(unittest.TestCase):
    def test_settings_read_key_and_model_from_environment(self):
        env = {"OPENROUTER_API_KEY": "secret", "LLAMA_MODEL": "some/model"}
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.openrouter_api_key, "secret")
        self.assertEqual(settings.llama_model, "some/model")
        self.assertTrue(settings.llm_configured)

    def test_missing_or_empty_environment_uses_defaults(self):
        for env in ({}, {"OPENROUTER_API_KEY": "", "LLAMA_MODEL": ""}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                settings = load_settings()
                self.assertIsNone(settings.openrouter_api_key)
                self.assertEqual(settings.llama_model, DEFAULT_MODEL)
                self.assertFalse(settings.llm_configured)
                self.assertEqual(settings.rate_limit_per_minute, DEFAULT_RATE_LIMIT_PER_MINUTE)
                self.assertIsNone(settings.metrics_token)
                self.assertEqual(settings.cors_origins, ())

    def test_protection_settings_are_parsed(self):
        env = {
            "RATE_LIMIT_PER_MINUTE": "5",
            "METRICS_TOKEN": "tok",
            "CORS_ORIGINS": "https://app.example.com/, http://localhost:5173,,",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertEqual(settings.rate_limit_per_minute, 5)
        self.assertEqual(settings.metrics_token, "tok")
        self.assertEqual(settings.cors_origins, ("https://app.example.com", "http://localhost:5173"))

    def test_invalid_rate_limit_fails_at_startup(self):
        for raw in ("ten", "-1"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"RATE_LIMIT_PER_MINUTE": raw}, clear=True):
                with self.assertRaises(ValueError):
                    load_settings()


if __name__ == "__main__":
    unittest.main()
