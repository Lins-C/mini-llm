# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from app.joshi import pipeline, projektdateien, pruefer, workers
from app.joshi.jobs import Auftrag


def lauf(zugang=None):
    l = pipeline.Lauf(Auftrag("job", "produkt", "user"), user_id="user", produkt={"id": "produkt"},
                      art="aendern", eingabe=pipeline.Eingabe(text="ändern"), modell="test", zugang=zugang)
    l.tokenstand = AsyncMock()
    l.technik = AsyncMock()
    l.melde = AsyncMock()
    return l


class EffizienzTests(unittest.TestCase):
    def test_simple_ai_button_uses_measured_style(self):
        k = {"beschreibung": "Der KI-Knopf ist schlicht gestaltet."}
        b = {"name": "KI: An", "verlauf": False, "schatten": False, "kinder": 0}
        self.assertEqual(workers.knopfpruefung(k, {"gestaltung": {"bedienelemente": [b]}})[0], "erfuellt")
        b["schatten"] = True
        self.assertEqual(workers.knopfpruefung(k, {"gestaltung": {"bedienelemente": [b]}})[0], "fehlt")

    def test_global_call_budget_blocks_nested_retries(self):
        l = lauf()
        l.grenzen = replace(l.grenzen, auftrag_generierungen=1)
        l._generieren = AsyncMock(return_value=("fertig", "stop"))

        async def run():
            self.assertEqual(await l.generieren([], "Test"), ("fertig", "stop"))
            with self.assertRaises(pipeline.Grenzfall) as e:
                await l.generieren([], "Test")
            self.assertEqual(e.exception.art, "budget")
        asyncio.run(run())
        self.assertEqual(l._generieren.await_count, 1)

    def test_reasoning_counts_towards_job_budget_and_stream_closes(self):
        class Modell:
            closed = False
            async def strom(self, *args, **kwargs):
                try:
                    yield {"denken": 3000}
                    yield {"text": "nicht mehr anfordern"}
                finally:
                    self.closed = True
        m = Modell()
        l = lauf(m)
        l.grenzen = replace(l.grenzen, auftrag_ausgabetokens=100)
        with self.assertRaises(pipeline.Grenzfall) as e:
            asyncio.run(l.generieren([], "Test"))
        self.assertEqual(e.exception.art, "budget")
        self.assertTrue(m.closed)
        self.assertEqual(l.abgebrochen_zeichen, 3000)

    def test_planning_deadline_cancels_provider(self):
        l = lauf()
        l.grenzen = replace(l.grenzen, struktur_sekunden=0.01)
        beendet = []
        async def provider():
            try:
                await asyncio.sleep(10)
            finally:
                beendet.append(True)
        with self.assertRaisesRegex(RuntimeError, "Zeitbudget"):
            asyncio.run(l.gemessen(provider()))
        self.assertEqual(beendet, [True])

    def test_staged_job_does_not_restart_as_full_rewrite(self):
        l = lauf()
        l.gestuft = True
        l.ganzdatei_kandidat = AsyncMock()
        b = pruefer.Pruefbericht([], browser=True)
        self.assertEqual(asyncio.run(l.zweite_strategie("html", b, {})), ("html", b))
        l.ganzdatei_kandidat.assert_not_awaited()

    def test_project_context_keeps_entrypoint_and_caps_files_without_modifying_source(self):
        html = ('<!doctype html><html><head><style>' + '.a{color:red}\n' * 100 + '</style></head><body>'
                '<script>' + '\n'.join(f'function a{i}(){{return {i};}}' for i in range(100))
                + '</script></body></html>')
        p = projektdateien.zerlegen(html, ziel=500)
        auswahl = projektdateien.auswahl_begrenzen(p, list(reversed(p.alle())), 2000, max_dateien=3)
        self.assertEqual(auswahl[0], "index.html")
        self.assertLessEqual(len(auswahl), 3)
        self.assertLessEqual(sum(len(p.alle()[n]) for n in auswahl), 2000)
        self.assertEqual(p.zusammensetzen(), html)
