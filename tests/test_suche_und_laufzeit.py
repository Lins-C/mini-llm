# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Kleine Fehler aus drei beobachteten Läufen vom 11.09.2026.

- Websuche: Ein ganzer Auftragssatz als Suchanfrage lieferte kein einziges
  passendes Ergebnis (Pizza-Video, Schulferien, Bank statt Ärzten in Musterstadt).
- Brief: Feldnamen („Name", „Straße") standen als Empfänger im Brief.
- Bericht: Zu einer markierten Seite mit 17.800 Zeichen entstanden zwölf
  Kapitel mit 99.000 Zeichen, jedes Kapitel sah nur die ersten 14.000 Zeichen.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.intelligence import suchbegriffe, web_search
from app.task_skills import (
    normalize_letter_artifact,
    report_outline_prompt,
    report_plan,
    report_section_prompt,
)

MEDIFLOW = (
    "ok ergänze nun  auch die Funkionen und Buttons der Arztsuche. verwende je nach "
    "gerät iOS = apple karten und Android Google maps. mach ein Beispiel verwende "
    "innerhalb Musterstadt NRW die Ärzte dies kannst du im web Suchen und systematisch "
    "Einpflegen, ergänze die html"
)

class SuchbegriffeTests(unittest.TestCase):
    def test_the_observed_request_becomes_keywords(self):
        self.assertEqual(suchbegriffe(MEDIFLOW), "Musterstadt NRW Ärzte")

    def test_lowercase_topics_still_work(self):
        self.assertEqual(suchbegriffe("such mal im netz ärzte in musterstadt"), "ärzte musterstadt")

    def test_nothing_usable_gives_nothing(self):
        self.assertEqual(suchbegriffe("bitte suche"), "")

    def test_the_search_engine_gets_the_keywords_first(self):
        class Suchmaschine:
            anfragen: list[str] = []

            def text(self, anfrage, **_):
                Suchmaschine.anfragen.append(anfrage)
                return []

            def news(self, anfrage, **_):
                return []

        with patch("ddgs.DDGS", Suchmaschine):
            asyncio.run(web_search(MEDIFLOW))
        self.assertEqual(Suchmaschine.anfragen[0], "Musterstadt NRW Ärzte")
        self.assertFalse(any("Einpflegen" in anfrage for anfrage in Suchmaschine.anfragen))


class BriefTests(unittest.TestCase):
    def test_field_names_are_not_values(self):
        brief = normalize_letter_artifact({
            "recipient": {"name": "Name", "department": "Straße",
                          "street": "[Straße und Hausnummer]", "postal_code": "[PLZ]", "city": "[Ort]"},
            "subject": "Dienstplan", "paragraphs": ["Text."],
        })
        self.assertEqual(brief["recipient"]["name"], "[Name des Empfängers]")
        self.assertEqual(brief["recipient"]["department"], "")

    def test_real_values_stay(self):
        brief = normalize_letter_artifact({
            "recipient": {"name": "Erika Musterfrau", "street": "Muster Straße 2",
                          "postal_code": "12345", "city": "Musterstadt"},
            "paragraphs": ["Text."],
        })
        self.assertEqual(brief["recipient"]["name"], "Erika Musterfrau")
        self.assertEqual(brief["recipient"]["street"], "Muster Straße 2")
        self.assertEqual(brief["recipient"]["city"], "Musterstadt")


class BerichtTests(unittest.TestCase):
    def test_a_report_on_a_selection_stays_proportional(self):
        self.assertLessEqual(report_plan("auto", 17_865, auf_auswahl=True)["sections"], 7)
        self.assertIsNone(report_plan("auto", 2_000, auf_auswahl=True))
        # Ohne Markierung und bei ausdrücklich „Lang" bleibt alles wie bisher.
        self.assertEqual(report_plan("auto", 17_865)["sections"], 12)
        self.assertEqual(report_plan("long", 17_865, auf_auswahl=True)["sections"], 12)

    def test_sections_see_as_much_material_as_the_window_allows(self):
        material = "A" * 20_000 + "ENDE"
        plan = {"sections": 3, "words": 500}
        gliederung = report_outline_prompt("T", plan, material, grenze=30_000)
        self.assertIn("ENDE", gliederung[1]["content"])
        abschnitt = report_section_prompt(
            "T", plan, [{"titel": "a", "inhalt": ""}], 0, material, "", grenze=30_000,
        )
        self.assertIn("ENDE", abschnitt[1]["content"])
        # Die alte feste Grenze schnitt genau dieses Ende ab.
        self.assertNotIn("ENDE", report_section_prompt(
            "T", plan, [{"titel": "a", "inhalt": ""}], 0, material, "",
        )[1]["content"])


if __name__ == "__main__":
    unittest.main()
