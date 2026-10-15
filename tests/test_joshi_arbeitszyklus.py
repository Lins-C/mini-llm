# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import asyncio
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.joshi import abnahme, aenderung, pruefer, renderer, projektdateien, pipeline
from tests.test_joshi_effizienz import lauf


class ArbeitszyklusTests(unittest.TestCase):
    def test_read_tool_only_accepts_known_product_files(self):
        p = projektdateien.zerlegen('<!doctype html><html><body>Test</body></html>')
        self.assertEqual(projektdateien.leseanfrage('=== LESEN: index.html ===', p), ['index.html'])
        with self.assertRaises(projektdateien.ProjektFehler):
            projektdateien.leseanfrage('=== LESEN: ../../.env ===', p)
        self.assertEqual(projektdateien.leseanfrage('Erklärung und === LESEN: index.html ===', p), [])

    def test_builder_reads_missing_file_then_applies_verified_patch(self):
        class Zugang:
            def fenster(self, modell): return 8192
        l = lauf(Zugang())
        l.produkt['titel'] = 'Test'
        html = ('<!doctype html><html><head><style>\n' + '.a{color:red}\n' * 100
                + '</style></head><body>Test</body></html>')
        p = projektdateien.zerlegen(html)
        name = next(iter(p.dateien))
        alt = p.dateien[name]
        l.generieren = AsyncMock(side_effect=[(f'=== LESEN: {name} ===', 'stop'),
            (f'=== DATEI: {name} ===\n{alt.replace("red", "blue")}\n=== ENDE ===', 'stop')])
        with tempfile.TemporaryDirectory() as td, patch.object(pipeline.database, 'DATA_DIR', Path(td)):
            neu, komplett, _ = asyncio.run(l._projektdateien_umsetzen(html, 'Farbe ändern', 'Test', gestuft=False))
        self.assertTrue(komplett)
        self.assertIn('blue', neu)
        self.assertEqual(l.generieren.await_count, 2)
        self.assertIn(alt, '\n'.join(m['content'] for m in l.generieren.await_args_list[1].args[0]))

    def test_retry_plan_discards_already_done_and_empty_steps(self):
        vertrag = {"kriterien": [{"id": "offen", "beschreibung": "Breite verbessern"}]}
        plan = aenderung.stufenplan_normalisieren({"stufen": [
            {"titel": "Erledigt", "auftrag": "Nicht erneut bauen", "kriterien": ["schon_fertig"]},
            {"titel": "Leer", "auftrag": "Teuer nachdenken", "kriterien": []},
            {"titel": "Breite", "auftrag": "Breite verbessern", "kriterien": ["offen"]}]}, vertrag)
        self.assertEqual(len(plan["stufen"]), 1)
        self.assertEqual(plan["stufen"][0]["kriterien"], ["offen"])

    def test_missing_plan_criteria_are_never_lost(self):
        vertrag = {"kriterien": [{"id": "a", "beschreibung": "A"}, {"id": "b", "beschreibung": "B"}]}
        plan = aenderung.stufenplan_normalisieren({"stufen": [
            {"titel": "A", "auftrag": "A bauen", "kriterien": ["a"]}]}, vertrag)
        self.assertEqual({k for s in plan["stufen"] for k in s["kriterien"]}, {"a", "b"})

    def test_bad_scenario_cannot_become_model_failure_or_code_repair(self):
        class KeinModell:
            async def strukturiert(self, *a, **kw):
                raise AssertionError("Defekter Test ist kein Modellurteil")
        vertrag = {"kriterien": [{"id": "wahl", "beschreibung": "Symbole beeinflussen die Geschichte.",
                                  "nachweis": "ablauf", "pflicht": True}]}
        beweis = {"szenarien": [{"kriterium": "wahl", "ergebnis": "nicht_beweisbar",
                                 "grund": "Ziel Mia im Schneeland nicht gefunden"}]}
        b = asyncio.run(abnahme.pruefen(KeinModell(), "m", vertrag, beweis, verbrauch={}))
        self.assertEqual(b.ergebnisse[0].status, "NOT_PROVEN")
        self.assertFalse(b.modell_gefragt)
        self.assertFalse(pruefer.Pruefbericht(b.befunde(), browser=True).reparaturbedarf())

    def test_changed_text_needs_a_before_measurement(self):
        roh = {"szenarien": [{"kriterium": "wahl", "schritte": [
            {"art": "klicken", "ziel": "Weiter"}, {"art": "text_geaendert", "ziel": "geschichte"}]}]}
        self.assertEqual(abnahme.szenarien_normalisieren(roh, ["wahl"]), [])

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit fehlt")
    def test_dynamic_story_uses_real_before_and_after_not_random_title(self):
        html = ('<!doctype html><html><body><div id="geschichte">Zufälliger Anfang</div>'
                '<div id="auswahl"><button onclick="document.getElementById(\'geschichte\').textContent=\'Du wählst den Wald\'">🌿 Wald</button></div>'
                '</body></html>')
        s = {"id": "wahl", "kriterium": "wahl", "schritte": [
            {"art": "merken", "ziel": "geschichte"}, {"art": "klicken_in", "ziel": "auswahl"},
            {"art": "text_geaendert", "ziel": "geschichte"},
            {"art": "text_enthaelt", "ziel": "geschichte", "wert": "Wald"}, {"art": "keine_fehler"}]}
        _, result = asyncio.run(pruefer.szenarien_ausfuehren(html, szenarien=[s]))
        self.assertEqual(result[0]["ergebnis"], "bestanden", result)
        kaputt = html.replace("Du wählst den Wald", "Zufälliger Anfang")
        _, result = asyncio.run(pruefer.szenarien_ausfuehren(kaputt, szenarien=[s]))
        self.assertEqual(result[0]["ergebnis"], "gescheitert", result)
