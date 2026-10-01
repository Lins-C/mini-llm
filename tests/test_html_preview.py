# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die Livevorschau muss ausführbaren Code auch wirklich ausführen.

Der Rahmen läuft ohne eigene Herkunft. Dort wirft jeder Zugriff auf
localStorage einen SecurityError — und weil Modelle solchen Code gern in die
erste Zeile schreiben, stirbt sonst das ganze Skript, bevor ein Knopf verdrahtet
ist. Diese Tests halten die Gegenmaßnahmen fest.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


class HtmlPreviewTests(unittest.TestCase):
    def test_preview_frame_stays_isolated(self):
        rahmen = re.search(r'<iframe id="preview-frame"[^>]*>', INDEX, re.S)
        self.assertIsNotNone(rahmen)
        self.assertIn('sandbox="allow-scripts"', rahmen.group(0))
        self.assertNotIn(
            "allow-same-origin",
            rahmen.group(0),
            "Die Vorschau darf niemals dieselbe Herkunft wie die Sitzung bekommen.",
        )

    def test_prelude_replaces_the_blocked_storage(self):
        self.assertIn("function previewPrelude()", APP_JS)
        self.assertIn("ersatzSpeicher", APP_JS)
        self.assertIn('Object.defineProperty(window, "localStorage"', APP_JS)
        self.assertIn('Object.defineProperty(window, "sessionStorage"', APP_JS)

    def test_prelude_is_only_added_where_scripts_may_run(self):
        self.assertIn('+ (allowScripts ? previewPrelude() : "")', APP_JS)

    def test_errors_and_dialogs_become_visible(self):
        self.assertIn('window.addEventListener("error"', APP_JS)
        self.assertIn('window.addEventListener("unhandledrejection"', APP_JS)
        self.assertIn("window.alert = function", APP_JS)

    def test_reported_line_numbers_match_the_model_output(self):
        # Die Vorrede zählt ihre eigenen Zeilen und rechnet sie wieder heraus.
        self.assertIn("__VERSATZ__", APP_JS)
        self.assertIn("var VERSATZ = __VERSATZ__;", APP_JS)
        self.assertIn('rohbau.match(/\\n/g)', APP_JS)

    def test_written_values_are_kept_but_bounded(self):
        self.assertIn("PREVIEW_STORAGE_KEY", APP_JS)
        self.assertIn("PREVIEW_STORAGE_LIMIT", APP_JS)
        self.assertIn("event.source !== previewFrame.contentWindow", APP_JS)


class HtmlArtifactContractTests(unittest.TestCase):
    def test_the_model_gets_the_rules_that_broke_before(self):
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        for regel in ("try/catch", "pointerdown", "alert()", "touch-action", "x >= Breite"):
            self.assertIn(regel, main, f"Regel fehlt im Vertrag: {regel}")


if __name__ == "__main__":
    unittest.main()
