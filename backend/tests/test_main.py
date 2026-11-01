import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import NoteRequest, app, interpret, repair_latex


class InterpretationTests(unittest.TestCase):
    def test_observed_fraction_is_renderable_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = interpret(NoteRequest(text="(x^2)/2"))
        self.assertEqual(result.segments[0].readings, [r"\frac{x^2}{2}"])

    def test_ambiguous_observed_fraction_has_two_readings(self):
        with patch.dict(os.environ, {}, clear=True):
            result = interpret(NoteRequest(text=" (1 + x^2) / 2 "))
        self.assertEqual(result.segments[0].readings, [
            r"\frac{1+x^2}{2}", r"1+\frac{x^2}{2}"
        ])

    def test_complex_proof_requires_openrouter_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                interpret(NoteRequest(text="For all epsilon greater than zero"))
        self.assertEqual(caught.exception.status_code, 503)

    def test_complex_proof_calls_llama_and_returns_math(self):
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
            with patch("main.httpx.post", return_value=response) as request_mock:
                result = interpret(NoteRequest(text="for all epsilon greater than zero"))

        self.assertEqual(result.segments[0].readings, [r"\forall \varepsilon > 0"])
        kwargs = request_mock.call_args.kwargs
        self.assertEqual(request_mock.call_args.args[0], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["json"]["provider"]["require_parameters"])

    def test_invalid_model_response_returns_safe_gateway_error(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with patch("main.httpx.post", return_value=response):
                with self.assertRaises(HTTPException) as caught:
                    interpret(NoteRequest(text="Integral from a to b"))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, "AI interpretation failed.")

    def test_empty_model_segments_fall_back_to_original_text(self):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"segments": []}'}}]
        }
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with patch("main.httpx.post", return_value=response):
                result = interpret(NoteRequest(text="Today we study limits."))
        self.assertEqual(result.segments[0].kind, "text")
        self.assertEqual(result.segments[0].content, "Today we study limits.")

    def test_unescaped_latex_from_model_is_repaired(self):
        # Llama sent "\int" and "\text" without doubling the backslash, so JSON
        # decoded them as a carriage return and a tab (seen with "INT a to b x dx").
        raw_content = (
            '{"segments": [{"kind": "math", "content": "INT a to b x dx", '
            '"readings": ["\\rint_{a}^{b} x \\text{ d}x"]}]}'
        )
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": raw_content}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}, clear=True):
            with patch("main.httpx.post", return_value=response):
                result = interpret(NoteRequest(text="INT a to b x dx"))
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

    def test_whitespace_only_input_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            interpret(NoteRequest(text="   "))
        self.assertEqual(caught.exception.status_code, 422)

    def test_metrics_endpoint_exposes_request_and_llm_latency(self):
        client = TestClient(app)
        client.post("/api/interpret", json={"text": "(x^2)/2"})
        body = client.get("/metrics").text
        self.assertIn('http_request_duration_seconds_count{handler="/api/interpret"', body)
        self.assertIn("llm_request_duration_seconds_bucket", body)


if __name__ == "__main__":
    unittest.main()
