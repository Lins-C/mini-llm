# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Der Tokenzähler unterscheidet Ausgabe-Tempo von Kontextverbrauch."""
import unittest
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TokenSpeedUiTests(unittest.TestCase):
    def test_the_sidebar_has_an_accessible_speed_indicator(self):
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="task-tokens-speed"', markup)
        self.assertIn('aria-live="polite"', markup)

    def test_speed_uses_visible_output_not_prompt_tokens(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function taskTokenRate(counter = taskTokens)", javascript)
        self.assertIn("counter.endgueltig || counter.geschaetzt", javascript)
        self.assertIn("void eingabe;", javascript)
        self.assertIn("const ausgabeTokens", javascript)
        self.assertIn("Ø ${wert} Tok/s", javascript)
        self.assertIn("taskTokens.gestartetAt", javascript)

    def test_live_speed_refresh_is_cleaned_up(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("window.setInterval(renderTaskTokens, 500)", javascript)
        self.assertIn("function stopTaskTokenTimer()", javascript)
        self.assertIn("stopTaskTokenTimer();", javascript)

    def test_cloud_usage_has_two_accessible_circles_and_a_manual_refresh(self):
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="cloud-usage-session-ring"', markup)
        self.assertIn('id="cloud-usage-weekly-ring"', markup)
        self.assertIn('id="cloud-usage-refresh"', markup)
        self.assertIn("function refreshCloudUsage()", javascript)
        self.assertIn('fetch("/api/cloud-usage"', javascript)

    def test_joshi_feeds_the_same_counter(self):
        """Ein JOSHI-Lauf zählt in derselben Anzeige – nicht in einer zweiten."""
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        joshi_js = (ROOT / "static" / "joshi.js").read_text(encoding="utf-8")
        self.assertIn("function joshiTokenstand(", app_js)
        self.assertIn("joshiTokenstand }", app_js)
        self.assertIn('counter.quelle === "joshi"', app_js)
        self.assertIn("joshiTokens.gemeldeteSekunden", app_js)
        self.assertIn("output_tokens_actual", app_js)
        self.assertIn("output_tokens_estimated", app_js)
        self.assertIn("output_tokens_incomplete", app_js)
        self.assertIn("usage_status", app_js)
        self.assertIn('"≈ "', app_js)
        self.assertIn("window.miniLLM?.joshiTokenstand?.(", joshi_js)
        self.assertIn("ereignis.modellsekunden", joshi_js)
        self.assertIn("live.tokens = { ...ereignis", joshi_js)

    def test_the_joshi_sidebar_mirrors_the_counter(self):
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        joshi_js = (ROOT / "static" / "joshi.js").read_text(encoding="utf-8")
        self.assertIn('id="joshi-nebenanzeigen"', markup)
        self.assertIn('const SPIEGEL = ["#task-tokens", "#cloud-usage", "#system-metrics"]', joshi_js)
        self.assertIn("new MutationObserver(", joshi_js)

    @unittest.skipUnless(shutil.which("node"), "Node für die JavaScript-Verhaltenstests erforderlich")
    def test_parallel_counters_and_finished_rates(self):
        ergebnis = subprocess.run(["node", str(ROOT / "tests/token_counter.cjs")],
                                  capture_output=True, text=True, timeout=15)
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stdout + ergebnis.stderr)


if __name__ == "__main__":
    unittest.main()
