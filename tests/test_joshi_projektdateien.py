# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Verlustfreie Projektdateien für große JOSHI-Anwendungen."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.joshi import projektdateien


def grosse_html() -> str:
    css = "\n".join(f".karte-{n} {{ color: #{n:03x}; padding: {n}px; }}" for n in range(120))
    js = "\n".join(f"function berechnen{n}() {{ return {n}; }}" for n in range(240))
    return ("<!DOCTYPE html><html><head><style>\n" + css + "\n</style></head><body><main>Werkzeug</main>"
            "<script>\n" + js + "\n</script></body></html>")


class ProjektdateienTests(unittest.TestCase):
    def test_split_and_recompose_are_byte_for_byte_identical(self):
        html = grosse_html()
        projekt = projektdateien.zerlegen(html, ziel=1200)
        self.assertGreaterEqual(len(projekt.dateien), 2)
        self.assertEqual(projekt.zusammensetzen(), html)
        self.assertEqual(projekt.fehler(), [])

    def test_file_patch_is_applied_only_to_a_seen_file(self):
        html = grosse_html()
        projekt = projektdateien.zerlegen(html, ziel=1200)
        name, inhalt = next(iter(projekt.dateien.items()))
        alt = next(line for line in inhalt.splitlines() if line.strip())
        neu = alt.replace("padding: 0px", "padding: 1px")
        text = f"=== ÄNDERN: {name} ===\n<<<<<<< SUCHEN\n{alt}\n=======\n{neu}\n>>>>>>> ERSETZEN\n=== ENDE ==="
        nicht_gesehen = projektdateien.anwenden(projekt, text, gesehen=[], aufgabe="ändern")
        self.assertTrue(any("ohne dass das Modell sie gesehen hat" in e for e in nicht_gesehen.probleme))

        angewendet = projektdateien.anwenden(projekt, text, gesehen=[name], aufgabe="ändern")
        self.assertEqual(angewendet.probleme, [])
        self.assertIn(name, angewendet.geaendert)
        self.assertIn(neu, angewendet.projekt.dateien[name])
        self.assertEqual(len(angewendet.projekt.zusammensetzen()), len(html) - len(alt) + len(neu))

    def test_new_file_is_inserted_as_a_valid_inline_script(self):
        html = grosse_html()
        projekt = projektdateien.zerlegen(html, ziel=1200)
        antwort = projektdateien.anwenden(
            projekt,
            "=== DATEI: js/neu.js ===\nfunction neu() { return true; }\n=== ENDE ===",
            gesehen=[], aufgabe="neue Funktion ergänzen",
        )
        self.assertEqual(antwort.probleme, [])
        self.assertIn("js/neu.js", antwort.neu)
        self.assertIn("function neu()", antwort.projekt.zusammensetzen())

    def test_path_traversal_in_response_and_manifest_is_rejected(self):
        projekt = projektdateien.zerlegen(grosse_html(), ziel=1200)
        antwort = projektdateien.anwenden(
            projekt, "=== DATEI: js/../../outside.js ===\nalert(1)\n=== ENDE ===",
            gesehen=[], aufgabe="ergänzen",
        )
        self.assertTrue(any("kein erlaubter Projektpfad" in e for e in antwort.probleme))

        with tempfile.TemporaryDirectory() as temporaer:
            ziel = Path(temporaer) / "auftrag"
            ziel.mkdir()
            (ziel / "manifest.json").write_text(json.dumps({"dateien": ["js/../../outside.js"]}), encoding="utf-8")
            self.assertIsNone(projektdateien.laden(ziel, grosse_html()))

    def test_job_directory_is_scoped_to_product_and_valid_job_id(self):
        root = projektdateien.auftrag_ordner(Path("/tmp/data"), {"id": "abc-123", "titel": "Gold App"}, "job_123")
        self.assertEqual(root.parts[-3:], ("gold-app-abc-123", "auftraege", "job_123"))
        with self.assertRaises(projektdateien.ProjektFehler):
            projektdateien.auftrag_ordner(Path("/tmp/data"), {"id": "abc", "titel": "Test"}, "../outside")

    def test_saved_project_is_reused_only_if_it_recomposes_to_active_html(self):
        html = grosse_html()
        projekt = projektdateien.zerlegen(html, ziel=1200)
        with tempfile.TemporaryDirectory() as temporaer:
            ziel = Path(temporaer) / "job"
            projektdateien.schreiben(ziel, projekt, auftrag="job-1")
            self.assertEqual(projektdateien.laden(ziel, html), projekt)
            self.assertIsNone(projektdateien.laden(ziel, html + " "))


if __name__ == "__main__":
    unittest.main()
