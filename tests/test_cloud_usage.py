# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die Cloud-Nutzung darf keine Schlüssel oder Rohantworten an die UI geben."""
import os
import unittest
from unittest.mock import patch

from app import main


class CloudUsageTests(unittest.TestCase):
    def test_fractional_limits_are_converted_to_percent_and_models_are_reduced(self):
        result = main.parse_ollama_cloud_usage({
            "limits": {
                "session": {
                    "usage": 0.125,
                    "models": [{"name": "gemma4:13b", "request_count": 1}],
                },
                "weekly": {
                    "usage": 0.185,
                    "models": [
                        {"name": "kimi-k3", "request_count": "80"},
                        {"name": "glm-5.3-flash", "request_count": 61},
                    ],
                },
            },
            "api_key": "must-never-leak",
        })
        self.assertEqual(result["session"]["percent"], 12.5)
        self.assertEqual(result["weekly"]["percent"], 18.5)
        self.assertEqual(result["weekly"]["models"][0], {"name": "kimi-k3", "requests": 80})
        self.assertNotIn("api_key", str(result))

    def test_missing_limits_are_rejected_instead_of_inventing_usage(self):
        with self.assertRaises(ValueError):
            main.parse_ollama_cloud_usage({"activity": {}})

    def test_a_separate_usage_key_wins_over_a_general_ollama_key(self):
        with patch.dict(os.environ, {
            "OLLAMA_CLOUD_USAGE_API_KEY": "usage-only-key",
            "OLLAMA_API_KEY": "normal-key",
        }, clear=False):
            self.assertEqual(main.ollama_cloud_usage_api_key(), "usage-only-key")
