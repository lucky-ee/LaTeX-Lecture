import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from main import NoteRequest, interpret


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

    def test_whitespace_only_input_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            interpret(NoteRequest(text="   "))
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
