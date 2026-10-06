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
                                 fortsetzung_anfuegen, html_aus_antwort, laufzeit_dokument, statische_befunde)

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

    def test_charset_comes_first(self):
        """Fund 06.10.2026: Laufzeit vor <meta charset> → geöffnete Datei als Windows-1252."""
        html = export_dokument(HOLODECK, zustand={}, meta={"joshi": 1}).encode("utf-8")
        self.assertIn(b'<meta charset="utf-8">', html[:1024])

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


class FortsetzungTests(unittest.TestCase):
    """Echter Fall 04.10.2026: Zaun mitten im Regex, Erklärtext, Fortsetzung mit halber Zeile."""
    TEIL1 = ("<!DOCTYPE html><html><body><script>\nfunction extractJSON(text){\n"
             "    var t = String(text).replace(/\n```\n### Holodeck-Interaktion\n\nDas Holodeck verbindet …\n---\n"
             "**Optimierungshinweis:** Du kannst …")
    TEIL2 = ("var t = String(text).replace(/```json/gi, '').replace(/```/g, '').trim();\n"
             "    return t;\n}\n</script></body></html>")

    def test_explanation_is_dropped_and_the_half_line_is_replaced(self):
        text = fortsetzung_anfuegen(self.TEIL1, self.TEIL2)
        auszug = html_aus_antwort(text)
        self.assertTrue(auszug.vollstaendig)
        self.assertNotIn("Holodeck-Interaktion", auszug.html)
        self.assertNotIn("Optimierungshinweis", auszug.html)
        self.assertEqual(auszug.html.count("var t = "), 1)
        self.assertIn("replace(/```json/gi, '')", auszug.html)

    def test_backticks_inside_code_survive_an_unfinished_answer(self):
        auszug = html_aus_antwort("```html\n<!DOCTYPE html><html><body><script>var r = /```json/gi;\n")
        self.assertIn("/```json/gi", auszug.html)
        self.assertFalse(auszug.html.startswith("```"))

    def test_normal_continuation_is_unchanged(self):
        self.assertEqual(fortsetzung_anfuegen("<html><body><p>Hal", "lo</p></body></html>"),
                         "<html><body><p>Hallo</p></body></html>")


class EndpunktTests(unittest.TestCase):
    """Fehler 04.10.2026: leeres Verbrauchsfeld → KeyError 'prompt_tokens' bei jeder Anfrage."""

    def test_answer_comes_back_and_usage_is_booked(self):
        from types import SimpleNamespace
        from unittest import mock
        from app.joshi import api

        class Zugang:
            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                verbrauch["prompt_tokens"] += 5          # wie die echte Modellschicht
                verbrauch["completion_tokens"] += 2
                yield {"text": "Hallo "}
                yield {"text": "Kadett."}

        anbindung = SimpleNamespace(nutzer=lambda r: {"id": "u1"}, zugang=Zugang())
        with mock.patch.object(api, "_anbindung", anbindung), \
                mock.patch.object(api, "_produkt_oder_404", return_value={"id": "p1"}):
            antwort = asyncio.run(api.ki_aus_anwendung(None, "p1", {
                "modell": "testmodell", "nachrichten": [{"role": "user", "content": "Hi"}]}))
        self.assertEqual(antwort, {"ok": True, "text": "Hallo Kadett.", "modell": "testmodell"})


class PaketTests(unittest.TestCase):
    """Teilen: Mit KI-Funktion kommt ein ZIP mit Startdatei, sonst wie bisher."""

    def paket(self, html):
        import io
        import zipfile
        from app.joshi import export

        daten = export.paket_zip({"id": "p1", "titel": "Holodeck", "zustand": {}}, {"nummer": 1, "html": html}, {})
        archiv = zipfile.ZipFile(io.BytesIO(daten))
        return {i.filename: i for i in archiv.infolist()}, archiv

    def test_ki_app_gets_start_files_and_readme(self):
        eintraege, archiv = self.paket(HOLODECK)
        self.assertEqual(set(eintraege), {"holodeck/index.html", "holodeck/LIESMICH.txt", "holodeck/start.py",
                                          "holodeck/Starten (Mac).command", "holodeck/Starten (Windows).bat"})
        self.assertEqual(eintraege["holodeck/Starten (Mac).command"].external_attr >> 16, 0o100755)
        index = archiv.read("holodeck/index.html").decode()
        self.assertIn(KI_VERBINDUNG, index)
        self.assertIn("127.0.0.1", archiv.read("holodeck/start.py").decode())
        self.assertIn("ollama pull", archiv.read("holodeck/LIESMICH.txt").decode())

    def test_plain_app_has_no_start_files(self):
        eintraege, _ = self.paket("<html><body><p>Rechner</p></body></html>")
        self.assertEqual(set(eintraege), {"holodeck/index.html", "holodeck/LIESMICH.txt"})

    def test_email_attaches_the_zip_for_ki_apps(self):
        from email import message_from_bytes
        from app.joshi import export

        daten, _ = export.email({"id": "p1", "titel": "Holodeck", "zustand": {}}, {"nummer": 1, "html": HOLODECK},
                                {}, None)
        namen = [t.get_filename() for t in message_from_bytes(daten).walk() if t.get_filename()]
        self.assertEqual(namen, ["holodeck.zip"])


class AttrappenTests(unittest.TestCase):
    """Fall 06.10.2026: Holodeck mit „Modell wählen: Kompakt“ und API-Schlüssel-Feld ohne Wirkung."""

    def test_own_ki_settings_are_an_error(self):
        for markup in ('<label for="m">Modell wählen</label><select id="m"></select>',
                       '<label>Provider wählen</label>', '<input id="k" placeholder="API-Schlüssel">'):
            befunde = statische_befunde(HOLODECK.replace('<p id="a">', markup + '<p id="a">'))
            self.assertIn("fehler", {b.art for b in befunde}, markup)

    def test_no_false_alarm_without_ki_or_without_settings(self):
        self.assertNotIn("fehler", {b.art for b in statische_befunde(HOLODECK)})
        ohne_ki = '<html><body><label for="p">Provider</label><input id="p"></body></html>'
        self.assertNotIn("fehler", {b.art for b in statische_befunde(ohne_ki)})


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
