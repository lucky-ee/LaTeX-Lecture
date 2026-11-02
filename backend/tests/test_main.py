import asyncio
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import main
from main import NoteRequest, app, interpret, repair_latex


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


def mock_llm(**post_behavior):
    """Swap in a fake shared HTTP client; its async post() takes AsyncMock settings."""
    client = Mock()
    client.post = AsyncMock(**post_behavior)
    return patch("main.http_client", client)


def llm_reply(segments):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"segments": segments})}}]
    }
    return response


class InterpretationTests(unittest.IsolatedAsyncioTestCase):
    async def test_observed_fraction_is_renderable_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = await interpret(NoteRequest(text="(x^2)/2"))
        self.assertEqual(result.segments[0].readings, [r"\frac{x^2}{2}"])

    async def test_ambiguous_observed_fraction_has_two_readings(self):
        with patch.dict(os.environ, {}, clear=True):
            result = await interpret(NoteRequest(text=" (1 + x^2) / 2 "))
        self.assertEqual(result.segments[0].readings, [
            r"\frac{1+x^2}{2}", r"1+\frac{x^2}{2}"
        ])

    async def test_complex_proof_requires_openrouter_key(self):
        with patch.dict(os.environ, {}, clear=True):
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
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(return_value=response) as client:
                result = await interpret(NoteRequest(text="for all epsilon greater than zero"))

        self.assertEqual(result.segments[0].readings, [r"\forall \varepsilon > 0"])
        kwargs = client.post.call_args.kwargs
        self.assertEqual(client.post.call_args.args[0], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["json"]["provider"]["require_parameters"])

    async def test_invalid_model_response_returns_safe_gateway_error(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
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
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
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
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
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
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(return_value=reply):
                response = client.post("/api/interpret", json={"text": "Today we study limits."})
        self.assertEqual(response.status_code, 200)
        self.assert_llm_metrics_changed(before, success=1, latency_count=1)

        body = client.get("/metrics").text
        self.assertIn('http_request_duration_seconds_count{handler="/api/interpret"', body)
        self.assertIn('llm_requests_total{outcome="success"}', body)
        self.assertIn('llm_requests_total{outcome="timeout"}', body)
        self.assertIn("llm_request_duration_seconds_count", body)

    async def test_known_notation_does_not_count_as_an_llm_call(self):
        before = llm_metrics()
        with patch.dict(os.environ, {}, clear=True):
            await interpret(NoteRequest(text="(x^2)/2"))
        self.assert_llm_metrics_changed(before)

    async def test_llm_timeout_is_counted_without_latency(self):
        before = llm_metrics()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(side_effect=httpx.ReadTimeout("slow")):
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assert_llm_metrics_changed(before, timeout=1)

    async def test_llm_http_error_is_counted_without_latency(self):
        response = Mock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("POST", "https://openrouter.ai"),
            response=httpx.Response(429),
        )
        before = llm_metrics()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(return_value=response):
                with self.assertRaises(HTTPException) as caught:
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assert_llm_metrics_changed(before, http_error=1)

    async def test_invalid_llm_response_is_counted_with_latency(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        before = llm_metrics()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(return_value=response):
                with self.assertRaises(HTTPException):
                    await interpret(NoteRequest(text="Integral from a to b"))
        # The upstream did answer, so its latency counts even though the content was unusable.
        self.assert_llm_metrics_changed(before, invalid_response=1, latency_count=1)

    async def test_stage_metrics_include_failed_upstream_attempt(self):
        labels = {"stage": "upstream_request", "outcome": "error"}
        before = metric("interpret_stage_duration_seconds_count", **labels)
        parsed = metric("interpret_stage_runs_total", stage="response_parse", outcome="success")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with mock_llm(side_effect=httpx.ReadTimeout("slow")):
                with self.assertRaises(HTTPException):
                    await interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(metric("interpret_stage_duration_seconds_count", **labels) - before, 1)
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

    async def test_local_path_records_only_executed_stages(self):
        stages = ("input_check", "local_match", "upstream_request", "response_parse", "latex_repair")
        before = {stage: metric("interpret_stage_runs_total", stage=stage, outcome="success") for stage in stages}
        await interpret(NoteRequest(text="(x^2)/2"))
        for stage in stages:
            self.assertEqual(
                metric("interpret_stage_runs_total", stage=stage, outcome="success") - before[stage],
                int(stage in ("input_check", "local_match")),
            )

    async def test_slow_llm_calls_run_concurrently(self):
        # Each fake LLM call takes 0.3s. Ten of them one after another would take 3s;
        # running concurrently, they should all finish in roughly the time of one.
        reply = llm_reply([{"kind": "text", "content": "Today we study limits.", "readings": []}])

        async def slow_post(*_args, **_kwargs):
            await asyncio.sleep(0.3)
            return reply

        notes = [NoteRequest(text=f"Today we study limits, part {i}.") for i in range(10)]
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
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


if __name__ == "__main__":
    unittest.main()
