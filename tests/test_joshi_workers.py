# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import asyncio
import unittest

from app.joshi import abnahme, workers, renderer
from app.joshi.html_werk import laufzeit_dokument


class WorkerTests(unittest.TestCase):
    def test_longer_story_uses_measured_words_not_literal_keywords(self):
        kriterium = {"id": "laenger", "beschreibung": "Der Geschichtentext ist deutlich länger und umfasst mehrere Absätze.",
                     "nachweis": "inhalt", "pflicht": True, "stichworte": ["Absätze", "mehr Text"]}
        for jetzt, erwartet in [(800, "PASS"), (310, "FAIL")]:
            beweise = {"leseinhalt": {"woerter": jetzt, "absaetze": 7},
                       "vorher": {"leseinhalt": {"woerter": 300, "absaetze": 3}}}
            self.assertEqual(abnahme.deterministisch_pruefen({"kriterien": [kriterium]}, beweise)[0].status, erwartet)

    def test_missing_measurement_never_becomes_an_llm_failure(self):
        k = {"id": "laenger", "beschreibung": "Die Geschichte wird länger.", "nachweis": "inhalt"}
        e = abnahme.deterministisch_pruefen({"kriterien": [k]}, {})[0]
        self.assertEqual(e.status, "NOT_PROVEN")
        self.assertEqual(e.urteil, "unbeweisbar")

    def test_countdown_is_not_reading_duration(self):
        k = {"id": "zeit", "beschreibung": "Eine Geschichte lässt sich in höchstens 40 Minuten Lese- und Aktionszeit durchlaufen.",
             "nachweis": "ablauf", "pflicht": True}
        scenario = {"kriterium": "zeit", "schritte": [{"art": "text_enthaelt", "wert": "40:00"}]}
        self.assertFalse(workers.szenario_pruefen(scenario, k, {}))
        e = abnahme.deterministisch_pruefen({"kriterien": [k]}, {
            "szenarien": [{"kriterium": "zeit", "ergebnis": "bestanden"}]})[0]
        self.assertEqual(e.status, "NOT_PROVEN")
        self.assertEqual(e.urteil, "unbeweisbar")
        class KeinAufruf:
            async def strukturiert(self, *args, **kwargs):
                raise AssertionError("Keinen Modellaufruf für unbeweisbaren Countdown")
        self.assertEqual(asyncio.run(abnahme.szenarien_erzeugen(
            KeinAufruf(), "m", kriterien=[k], gliederung={}, verbrauch={})), [])

    def test_story_width_is_measured_and_not_inferred_from_colors(self):
        k = {"beschreibung": "Die Geschichte wird in einem großen, breiten Bereich dargestellt.", "nachweis": "gestaltung"}
        self.assertEqual(workers.layoutpruefung(k, {"leseinhalt": {"breite": 34}})[0], "fehlt")
        self.assertEqual(workers.layoutpruefung(k, {"leseinhalt": {"breite": 80}})[0], "erfuellt")

    def test_measured_content_is_preserved_in_baseline_evidence(self):
        b = abnahme.beweise_sammeln({"leseinhalt": {"woerter": 800}}, {},
                                  {"leseinhalt": {"woerter": 300}})
        self.assertEqual(b["leseinhalt"]["woerter"], 800)
        self.assertEqual(b["vorher"]["leseinhalt"]["woerter"], 300)

    def test_repair_worker_only_targets_open_requirements(self):
        text = workers.reparaturauftrag({"ergebnisse": [
            {"id": "done", "pflicht": True, "status": "PASS", "beschreibung": "DONE"},
            {"id": "todo", "pflicht": True, "status": "FAIL", "beschreibung": "TODO", "begruendung": "310 Wörter"}]}, {})
        self.assertIn("310 Wörter", text)
        self.assertNotIn("DONE", text)

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit fehlt")
    def test_browser_measures_story_after_opening_it(self):
        paragraph = "Ein Kind entdeckt den Wald und trifft dort Freunde. " * 15
        html = ('<!doctype html><html><body><button onclick="document.getElementById(\'story\').hidden=false">Buch öffnen</button>'
                '<article id="story" hidden>' + ''.join('<p>' + paragraph + '</p>' for _ in range(4))
                + '</article></body></html>')
        m = asyncio.run(renderer.rendern(laufzeit_dokument(html, modus="pruefung"),
                                         probe=renderer.pruefskript(), breite=1280, hoehe=900))
        self.assertTrue(m.ok)
        self.assertIsNone(m.probe["vorher"]["leseinhalt"])
        lesen = m.probe["interaktion"]["leseinhalt"]
        self.assertEqual(lesen["absaetze"], 4)
        self.assertGreater(lesen["woerter"], 400)
        self.assertEqual(lesen["nach"], "Buch öffnen")

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit fehlt")
    def test_fade_in_does_not_hide_story_from_offscreen_worker(self):
        html = ('<!doctype html><html><head><style>@keyframes fade{from{opacity:0}to{opacity:1}}'
                '#story{animation:fade .6s both}</style></head><body><article id="story">'
                + '<p>' + 'Die Tiere wandern gemeinsam durch den Wald. ' * 40 + '</p></article></body></html>')
        m = asyncio.run(renderer.rendern(laufzeit_dokument(html, modus="pruefung"),
                                         probe=renderer.inhaltsskript(), breite=1280, hoehe=900))
        self.assertTrue(m.ok)
        self.assertGreater(m.probe["leseinhalt"]["woerter"], 200)
