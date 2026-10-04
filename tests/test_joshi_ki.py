# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""KI-Sprachmodell in JOSHI-Anwendungen: JOSHI.ki(), Umleitung, Richtlinie, Prüfung.

Anlass (03.10.2026): Ein Holodeck mit Ollama- und OpenAI-Anbindung lief im Export
gegen connect-src 'none'. Jetzt laufen KI-Aufrufe über JOSHI — mit Rückfrage beim
Nutzer, ohne API-Schlüssel im Frontend, und der Export gibt nur localhost:11434 frei.
"""
import asyncio
import re
import unittest

from fastapi import HTTPException

from app.joshi import renderer
from app.joshi.api import ki_nachrichten
from app.joshi.html_werk import (KI_VERBINDUNG, SICHERHEITSRICHTLINIE, braucht_ki, export_dokument,
                                 laufzeit_dokument, statische_befunde)

HOLODECK = """<!DOCTYPE html><html><head><title>Holodeck</title></head><body>
<p id="a">…</p><p id="b">…</p><p id="c">…</p><p id="d">…</p>
<script>
(async () => {
  const g = await fetch("http://localhost:11434/api/generate", {method: "POST",
    body: JSON.stringify({model: "llama3", prompt: "Hallo", stream: false})}).then(r => r.json());
  document.getElementById("a").textContent = g.response;
  const c = await fetch("http://localhost:11434/api/chat", {method: "POST",
    body: JSON.stringify({model: "llama3", messages: [{role: "user", content: "Hi"}]})}).then(r => r.json());
  document.getElementById("b").textContent = c.message.content;
  const o = await fetch("https://api.example.com/v1/chat/completions", {method: "POST",
    headers: {Authorization: "Bearer geheim"},
    body: JSON.stringify({model: "gpt", messages: [{role: "user", content: "Hi"}]})}).then(r => r.json());
  document.getElementById("c").textContent = o.choices[0].message.content;
  const k = await window.JOSHI.ki({system: "Antworte als JSON", messages: [{role: "user", content: "Figuren"}], format: "json"});
  document.getElementById("d").textContent = k.ok + ":" + k.text;
})();
</script></body></html>"""


class RichtlinieTests(unittest.TestCase):
    def test_export_opens_only_local_ollama_and_only_when_needed(self):
        def richtlinie(html):
            return re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
        mit = richtlinie(export_dokument(HOLODECK, zustand={}, meta={"joshi": 1}))
        self.assertIn(KI_VERBINDUNG, mit)
        self.assertNotIn("connect-src 'none'", mit)
        ohne = richtlinie(export_dokument("<html><body><p>Rechner</p></body></html>", zustand={}, meta={"joshi": 1}))
        self.assertIn("connect-src 'none'", ohne)
        self.assertNotIn("11434", ohne)

    def test_preview_and_check_stay_without_network(self):
        for modus in ("vorschau", "pruefung"):
            self.assertIn("connect-src 'none'", laufzeit_dokument(HOLODECK, modus=modus))

    def test_detection(self):
        self.assertTrue(braucht_ki("await JOSHI.ki({prompt: 'x'})"))
        self.assertTrue(braucht_ki("fetch(base + '/api/chat')"))
        self.assertFalse(braucht_ki("fetch('daten.json')"))
        self.assertIn("connect-src 'none'", SICHERHEITSRICHTLINIE)

    def test_static_check_accepts_model_calls_but_not_other_network(self):
        arten = {b.art for b in statische_befunde(HOLODECK) if "Netzwerk" in b.text or "KI" in b.text}
        self.assertEqual(arten, {"info"})
        fremd = HOLODECK.replace("</script>", "fetch('https://tracker.example.com/x');</script>")
        self.assertIn("warnung", {b.art for b in statische_befunde(fremd) if "Netzwerk" in b.text})


class AnfrageTests(unittest.TestCase):
    def test_messages_are_reduced_to_roles_and_text(self):
        aus = ki_nachrichten([{"role": "system", "content": "S"}, {"role": "tool", "content": "x"},
                              {"role": "user", "content": "Hallo", "extra": 1}])
        self.assertEqual(aus, [{"role": "system", "content": "S"}, {"role": "user", "content": "Hallo"}])

    def test_invalid_requests_are_refused(self):
        for roh in ([], "text", [{"role": "system", "content": "nur System"}],
                    [{"role": "user", "content": "x" * 200_000}]):
            with self.assertRaises(HTTPException):
                ki_nachrichten(roh)


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class PruefungImBrowserTests(unittest.TestCase):
    def test_model_calls_get_test_answers_without_network_or_errors(self):
        messung = asyncio.run(renderer.rendern(
            laufzeit_dokument(HOLODECK, modus="pruefung"), warten=1.0,
            probe="return JSON.stringify({w: ['a','b','c','d'].map(i => document.getElementById(i).textContent)"
                  ".concat([JSON.stringify(window.__joshi.fehler)])});"))
        werte = (messung.probe or {}).get("w")
        self.assertTrue(messung.geladen, messung)
        self.assertIn("Testantwort", werte[0])
        self.assertIn("Testantwort", werte[1])
        self.assertIn("Testantwort", werte[2])
        self.assertEqual(werte[3], "true:{}")
        self.assertEqual(werte[4], "[]")


if __name__ == "__main__":
    unittest.main()
