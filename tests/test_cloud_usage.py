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

    def test_the_new_request_count_format_is_shown_as_requests(self):
        """Oktober 2026: ollama.com/api/usage liefert nur noch Anfragezahlen je Zeitraum."""
        woche = {"range": "7d", "totals": {"request_count": 558}, "buckets": [
            {"request_count": n} for n in (25, 80, 7, 48, 32, 182, 75)], "api_key": "must-never-leak"}
        tag = {"range": "24h", "totals": {"request_count": 110}, "buckets": [{"request_count": 1}]}
        monat = {"range": "30d", "totals": {"request_count": 1200}, "buckets": []}
        result = main.parse_ollama_cloud_anfragen(tag, woche, monat)
        self.assertEqual(result["tag"], 110)
        self.assertEqual(result["woche"], 558)
        self.assertEqual(result["spitze_tag"], 182)
        self.assertEqual(result["wochenschnitt"], 280)
        self.assertNotIn("api_key", str(result))
        with self.assertRaises(ValueError):
            main.parse_ollama_cloud_anfragen({"error": "x"}, woche, monat)

    def test_the_endpoint_switches_to_request_counts_when_limits_are_gone(self):
        import asyncio
        from types import SimpleNamespace

        antworten = {
            None: {"range": "7d", "totals": {"request_count": 40}, "buckets": [{"request_count": 40}]},
            "24h": {"range": "24h", "totals": {"request_count": 12}, "buckets": [{"request_count": 12}]},
            "30d": {"range": "30d", "totals": {"request_count": 90}, "buckets": []},
        }

        class Client:
            async def get(self, url, params=None, headers=None, timeout=None):
                daten = antworten[(params or {}).get("range")]
                return SimpleNamespace(status_code=200, json=lambda: daten, raise_for_status=lambda: None)

        main._cloud_usage_cache.update({"expires_at": 0.0, "payload": None})
        with patch.dict(os.environ, {"OLLAMA_CLOUD_USAGE_API_KEY": "k"}, clear=False):
            result = asyncio.run(main.ollama_cloud_usage(Client()))
        main._cloud_usage_cache.update({"expires_at": 0.0, "payload": None})
        self.assertTrue(result["available"])
        self.assertEqual(result["anfragen"]["tag"], 12)
        self.assertEqual(result["anfragen"]["woche"], 40)

    def test_a_separate_usage_key_wins_over_a_general_ollama_key(self):
        with patch.dict(os.environ, {
            "OLLAMA_CLOUD_USAGE_API_KEY": "usage-only-key",
            "OLLAMA_API_KEY": "normal-key",
        }, clear=False):
            self.assertEqual(main.ollama_cloud_usage_api_key(), "usage-only-key")
