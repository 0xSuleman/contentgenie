import unittest
from unittest.mock import Mock, patch

from contentgenie.gpt.gpt_utils import _gemini_completion, _safe_error_message


class GeminiClientTests(unittest.TestCase):
    def test_transport_errors_redact_api_keys(self):
        secret = "super-secret-key"
        error = Exception(f"request failed: https://example.test?key={secret}")
        message = _safe_error_message(error, secret)
        self.assertNotIn(secret, message)
        self.assertIn("[REDACTED]", message)

    @patch("contentgenie.gpt.gpt_utils.requests.post")
    def test_structured_grounded_request_and_metadata(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": '{"answer":"verified"}'}]},
                "finishReason": "STOP",
                "groundingMetadata": {
                    "webSearchQueries": ["verified topic"],
                    "groundingChunks": [{"web": {"title": "Source", "uri": "https://example.com/source"}}],
                },
            }],
            "usageMetadata": {"promptTokenCount": 10},
        }
        post.return_value = response

        text, metadata = _gemini_completion(
            "key",
            "model",
            chat_prompt="prompt",
            response_schema={"type": "object"},
            use_google_search=True,
            return_metadata=True,
        )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(payload["tools"], [{"google_search": {}}])
        self.assertEqual(text, '{"answer":"verified"}')
        self.assertEqual(metadata["sources"][0]["url"], "https://example.com/source")


if __name__ == "__main__":
    unittest.main()
