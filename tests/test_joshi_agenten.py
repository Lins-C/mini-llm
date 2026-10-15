# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import asyncio
import json
import shutil
import unittest
from unittest.mock import AsyncMock, patch

from app.joshi import agenten, pipeline, pruefer, projektdateien
from app.joshi.html_werk import Befund
from tests.test_joshi_effizienz import lauf


class AgentenTests(unittest.TestCase):
    def test_json_response_adapter_preserves_code_and_enforces_existing_access_rules(self):
        p = projektdateien.zerlegen('<html><body>Test</body></html>')
        neu = '<html><body>Geändert</body></html>'
        antwort = json.dumps({'dateien': [{'path': 'index.html', 'content': neu}]})
        erlaubt = projektdateien.anwenden(p, antwort, gesehen=['index.html'])
        self.assertEqual(erlaubt.projekt.index, neu)
        verweigert = projektdateien.anwenden(p, antwort, gesehen=[])
        self.assertTrue(verweigert.probleme)
        traversal = json.dumps({'dateien': [{'pfad': '../../.env', 'inhalt': 'nicht schreiben'}]})
        self.assertTrue(projektdateien.anwenden(p, traversal, gesehen=[]).probleme)

    def test_context_worker_brings_referenced_definition_into_small_context(self):
        dateien = {'js/start.js': 'function startup(){ return setupGame(); }',
                   'js/other.js': 'function decoration(){ return 1; }',
                   'js/game.js': 'function setupGame(){ return true; }'}
        r = agenten.KontextWorker.ordnen(dateien, list(dateien))
        self.assertEqual(r[:2], ['js/start.js', 'js/game.js'])

    def test_review_only_accepts_anchors_from_supplied_source(self):
        class Zugang:
            async def strukturiert(self, modell, nachrichten, schema, **kwargs):
                self.modell = modell
                return {'hinweise': [
                    {'ausschnitt': 'const result = input.value;', 'ursache': 'Text statt Zahl', 'reparatur': 'Zahl lesen'},
                    {'ausschnitt': 'const invented = unknown.value;', 'ursache': 'Erfunden', 'reparatur': 'Erfunden'}]}
        z = Zugang()
        text = asyncio.run(agenten.RepairReviewAgent.pruefen(z, 'gewaehltes-modell', auftrag='Rechner',
            quelle='const result = input.value;', fehler='NaN', verbrauch={}))
        self.assertIn('Zahl lesen', text)
        self.assertNotIn('Erfunden', text)
        self.assertEqual(z.modell, 'gewaehltes-modell')

    def test_syntax_worker_parses_without_executing_generated_code(self):
        async def run():
            result = await asyncio.wait_for(agenten.SyntaxWorker.pruefen(
                '<html><script>while(true) {}</script></html>'), timeout=2)
            self.assertEqual(result, [])
        asyncio.run(run())

    def test_syntax_worker_ignores_json_script_content(self):
        self.assertEqual(asyncio.run(agenten.SyntaxWorker.pruefen(
            '<script type="application/ld+json">{"a":1}</script>')), [])

    def test_cancelled_syntax_worker_terminates_its_child(self):
        async def run():
            begonnen = asyncio.Event()
            class Prozess:
                returncode = None
                async def communicate(self, data):
                    begonnen.set()
                    await asyncio.Future()
                def kill(self): self.returncode = -9
                async def wait(self): return self.returncode
            prozess = Prozess()
            with patch.object(agenten.shutil, 'which', return_value='/node'), \
                 patch.object(agenten.asyncio, 'create_subprocess_exec', AsyncMock(return_value=prozess)):
                task = asyncio.create_task(agenten.SyntaxWorker.pruefen('<script>let a=1;</script>'))
                await begonnen.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertEqual(prozess.returncode, -9)
        asyncio.run(run())

    @unittest.skipUnless(shutil.which('node'), 'Node fehlt')
    def test_invalid_javascript_is_stopped_before_browser(self):
        with patch.object(pruefer.renderer, 'rendern', AsyncMock(side_effect=AssertionError('Browser unnötig'))):
            b = asyncio.run(pruefer.pruefen('<html><body>Test</body><script>const x = ;</script></html>'))
        self.assertFalse(b.ok)
        self.assertTrue(any('Syntaxfehler' in f.text for f in b.befunde))

    def test_review_is_bounded_and_never_replaces_browser_verdict(self):
        l = lauf()
        l.status = AsyncMock()
        l.phase = AsyncMock()
        l.abnehmen = AsyncMock()
        l.verbinden = lambda html, assets: (html, [])
        l.umsetzen = AsyncMock(side_effect=[('<html>zweiter Stand</html>', True, 'geändert'),
                                            ('<html>dritter Stand</html>', True, 'geändert')])
        fehler = pruefer.Pruefbericht([Befund('fehler', 'Fehler', 'const bad = 1;')], browser=True)
        gut = pruefer.Pruefbericht([], browser=True)
        with patch.object(pipeline.speicher, 'bild_data_uris', return_value={}), \
             patch.object(pipeline.pruefer, 'pruefen', AsyncMock(side_effect=[fehler, fehler, gut])), \
             patch.object(agenten.RepairReviewAgent, 'pruefen', AsyncMock(return_value='Konkreter Hinweis')) as review:
            html, b = asyncio.run(l.pruefen_und_reparieren('<html>erster Stand</html>', True, [], max_reparaturen=2))
        self.assertEqual(review.await_count, 1)
        self.assertFalse(b.ok)
        self.assertEqual(html, '<html>erster Stand</html>')
        self.assertEqual(l.umsetzen.await_count, 1)
