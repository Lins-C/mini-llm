# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""JOSHI: HTML-Werkstatt, Prüfer, Pipeline, Speicher, API und Verdrahtung.

Die Pipeline läuft hier mit einem gespielten Modellzugang und — wo nicht
ausdrücklich der echte WebKit-Renderer gemeint ist — mit einem gespielten
Prüfer. Die Renderer-Tests am Ende laufen nur, wenn der Renderer auf diesem
Rechner übersetzt vorliegt (sonst übersprungen).
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

WURZEL = Path(__file__).resolve().parents[1]

from app.joshi import abnahme, bruecke, export, html_werk, pipeline, pruefer, renderer, speicher  # noqa: E402
from app.joshi.html_werk import Befund  # noqa: E402
from app.joshi.jobs import Auftrag, Auftragsverwaltung  # noqa: E402

BMI = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>BMI</title></head>
<body><h1>BMI-Rechner</h1>
<label for="gewicht">Gewicht (kg)</label><input id="gewicht" type="number" value="70">
<label for="groesse">Größe (cm)</label><input id="groesse" type="number" value="175">
<button type="button" id="rechnen">Berechnen</button><button type="button" id="reset">Zurücksetzen</button>
<p id="ergebnis"></p>
<script>
function rechne(){var g=parseFloat(document.getElementById('gewicht').value),h=parseFloat(document.getElementById('groesse').value)/100;
document.getElementById('ergebnis').textContent=(g>0&&h>0)?'BMI: '+(g/(h*h)).toFixed(1):'Bitte Werte eingeben';}
document.getElementById('rechnen').onclick=rechne;
document.getElementById('reset').onclick=function(){document.getElementById('gewicht').value='';document.getElementById('groesse').value='';document.getElementById('ergebnis').textContent='';};
rechne();
</script></body></html>"""


# ---------------------------------------------------------------- HTML-Werkstatt
class HtmlAusAntwortTests(unittest.TestCase):
    def test_fences_and_prose_are_removed(self):
        auszug = html_werk.html_aus_antwort("Hier ist die Datei:\n```html\n" + BMI + "\n```\nViel Spaß!")
        self.assertTrue(auszug.vollstaendig)
        self.assertTrue(auszug.html.startswith("<!DOCTYPE html>"))
        self.assertTrue(auszug.html.endswith("</html>"))

    def test_a_truncated_file_is_reported(self):
        auszug = html_werk.html_aus_antwort(BMI[:400])
        self.assertFalse(auszug.vollstaendig)
        self.assertTrue(auszug.html)

    def test_a_fragment_gets_a_skeleton(self):
        auszug = html_werk.html_aus_antwort("<div><h1>Hallo</h1></div>", "Test")
        self.assertIn("<!DOCTYPE html>", auszug.html)
        self.assertIn('name="viewport"', auszug.html)
        self.assertIn("<title>Test</title>", auszug.html)
        self.assertTrue(auszug.vollstaendig)

    def test_plain_text_is_no_html(self):
        self.assertEqual(html_werk.html_aus_antwort("Ich kann das nicht.").html, "")


class AenderungsblockTests(unittest.TestCase):
    def test_exact_blocks_apply(self):
        text = "<<<<<<< SUCHEN\n<h1>BMI-Rechner</h1>\n=======\n<h1>BMI-Rechner</h1><p>Neu</p>\n>>>>>>> ERSETZEN"
        neu, fehl = html_werk.bloecke_anwenden(BMI, html_werk.aenderungsbloecke(text))
        self.assertEqual(fehl, [])
        self.assertIn("<p>Neu</p>", neu)

    def test_whitespace_differences_are_tolerated(self):
        text = "<<<<<<< SEARCH\n<button   type=\"button\"\n id=\"reset\">Zurücksetzen</button>\n=======\n<button type=\"button\" id=\"reset\">Neu starten</button>\n>>>>>>> REPLACE"
        neu, fehl = html_werk.bloecke_anwenden(BMI, html_werk.aenderungsbloecke(text))
        self.assertEqual(fehl, [])
        self.assertIn("Neu starten", neu)

    def test_a_missing_block_is_reported_not_guessed(self):
        text = "<<<<<<< SUCHEN\n<footer>gibt es nicht</footer>\n=======\n<footer>x</footer>\n>>>>>>> ERSETZEN"
        neu, fehl = html_werk.bloecke_anwenden(BMI, html_werk.aenderungsbloecke(text))
        self.assertEqual(neu, BMI)
        self.assertEqual(len(fehl), 1)


class LaufzeitHuelleTests(unittest.TestCase):
    def test_policy_and_runtime_come_before_the_app(self):
        dokument = html_werk.laufzeit_dokument(BMI, modus="vorschau", zustand={"felder": {"#gewicht": "82"}})
        kopf = dokument.index("<head>")
        self.assertLess(kopf, dokument.index("Content-Security-Policy"))
        self.assertLess(dokument.index("window.__JOSHI__"), dokument.index("<title>"))
        self.assertIn("connect-src 'none'", dokument)
        self.assertIn('"#gewicht": "82"', dokument)

    def test_state_cannot_break_out_of_the_script(self):
        dokument = html_werk.laufzeit_dokument(BMI, modus="vorschau", zustand={"x": "</script><img src=x>"})
        self.assertNotIn("</script><img", dokument)

    def test_assets_are_embedded(self):
        dokument = html_werk.laufzeit_dokument('<html><head></head><body><img src="joshi:bild-1"></body></html>',
                                               modus="export", assets={"bild-1": "data:image/png;base64,AAA"})
        self.assertIn('src="data:image/png;base64,AAA"', dokument)

    def test_export_carries_metadata_and_state(self):
        dokument = html_werk.export_dokument(BMI, zustand={"felder": {"#gewicht": "90"}},
                                             meta={"joshi": 1, "titel": "BMI", "produkt": "p1"})
        self.assertIn('id="joshi-daten"', dokument)
        self.assertIn('"modus": "export"', dokument)
        self.assertIn('"#gewicht": "90"', dokument)

    def test_error_lines_are_mapped_back_to_the_models_file(self):
        versatz = html_werk.LAUFZEIT_JS.count("\n")
        einfuege = BMI[:BMI.index("<head>") + 6].count("\n") + 1
        self.assertEqual(html_werk.originalzeile(BMI, einfuege + versatz + 5), einfuege + 5)
        self.assertEqual(html_werk.originalzeile(BMI, 1), 1)


class StatischeBefundeTests(unittest.TestCase):
    def test_external_scripts_are_errors(self):
        befunde = html_werk.statische_befunde(BMI.replace("<title>", '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script><title>'))
        self.assertTrue(any(b.art == "fehler" and "Internet" in b.text for b in befunde))

    def test_a_clean_file_has_no_errors(self):
        self.assertFalse([b for b in html_werk.statische_befunde(BMI) if b.art == "fehler"])


# ---------------------------------------------------------------------- Prüfer
class PrueferRegelnTests(unittest.TestCase):
    def test_static_only_never_counts_as_ready(self):
        self.assertFalse(pruefer.Pruefbericht([], browser=False).ok)

    def test_only_missing_actions_are_gaps(self):
        handlungen, uebrige = pruefer.fehlende_bedienelemente(
            ["Berechnen", "Zurücksetzen", "Ergebnis: BMI-Wert [Anzeige, z. B. '22,3']", "Gewicht (kg)"],
            {"knoepfe": ["Berechnen"], "felder": [{"label": "Gewicht (kg)"}], "markdown": "BMI 22"},
        )
        self.assertEqual(handlungen, ["Zurücksetzen"])
        self.assertEqual(uebrige, ["Ergebnis"])

    def messung(self, **probe: Any) -> renderer.Messung:
        daten = {"vorher": {"textLaenge": 120, "anzahl": {}, "knoepfe": ["Berechnen"], "felder": []},
                 "interaktion": {"felder": 2, "knoepfe": 2, "reaktionEingabe": False, "reaktionKlick": True,
                                 "kaputteWerte": [], "fehlerJeKnopf": []},
                 "fehler": [], "fehlerBeimLaden": 0}
        for schluessel, wert in probe.items():
            if isinstance(wert, dict) and isinstance(daten.get(schluessel), dict):
                daten[schluessel] = {**daten[schluessel], **wert}
            else:
                daten[schluessel] = wert
        return renderer.Messung(ok=True, geladen=True, probe=daten)

    def test_a_working_app_has_no_findings(self):
        befunde, _, _ = pruefer._befunde_aus_messung(BMI, self.messung(), None, [])
        self.assertEqual(befunde, [])

    def test_script_errors_name_the_button(self):
        messung = self.messung(fehler=[{"text": "TypeError: x is null", "zeile": 0, "quelle": "skript"}],
                               interaktion={"fehlerJeKnopf": [{"knopf": "Berechnen", "fehler": ["TypeError: x is null"]}]})
        befunde, _, _ = pruefer._befunde_aus_messung(BMI, messung, None, [])
        self.assertEqual(befunde[0].art, "fehler")
        self.assertIn("„Berechnen“", befunde[0].text)

    def test_nan_is_an_error(self):
        messung = self.messung(interaktion={"kaputteWerte": [{"wert": "NaN", "wann": "nach Klick auf „Berechnen“"}]})
        befunde, _, _ = pruefer._befunde_aus_messung(BMI, messung, None, [])
        self.assertTrue(any("NaN" in b.text and b.art == "fehler" for b in befunde))

    def test_no_reaction_at_all_is_an_error(self):
        messung = self.messung(interaktion={"reaktionKlick": False})
        befunde, _, _ = pruefer._befunde_aus_messung(BMI, messung, None, [])
        self.assertTrue(any(b.art == "fehler" and "reagiert" in b.text for b in befunde))

    def test_console_errors_only_warn(self):
        messung = self.messung(fehler=[{"text": "console.error: egal", "quelle": "konsole"}])
        befunde, _, _ = pruefer._befunde_aus_messung(BMI, messung, None, [])
        self.assertEqual([b.art for b in befunde], ["warnung"])

    def test_a_hanging_page_is_an_error(self):
        befunde, _, _ = pruefer._befunde_aus_messung(
            BMI, renderer.Messung(ok=False, fehler="Zeitüberschreitung nach 25 s"), None, [])
        self.assertIn("Endlosschleife", befunde[0].text)


# ---------------------------------------------------------------- Pipeline
class GespielterZugang:
    """Antwortet nach Drehbuch; zählt, was gefragt wurde.

    Strukturierte Aufrufe werden am Schema unterschieden: Verständnis,
    Abnahmevertrag und Abnahmeurteil — genau wie in der echten Modellschicht.
    """

    def __init__(self, antworten: list[str], verstaendnis: Any = None, fenster: int = 131072,
                 faehigkeiten: set[str] | None = None, vertrag: Any = None, urteile: Any = None) -> None:
        self.antworten = list(antworten)
        self.verstaendnis = verstaendnis if verstaendnis is not None else {
            "titel": "BMI-Rechner", "zweck": "BMI berechnen", "art": "rechner",
            "funktionen": ["Gewicht", "Größe", "Berechnen"], "bedienelemente": ["Berechnen"], "gestaltung": "hell"}
        # Ohne eigenen Vertrag gibt es keine Abnahmekriterien; dann prüft JOSHI
        # nur technisch — so bleiben die Tests hier bei ihrem Thema.
        self.vertrag = vertrag if vertrag is not None else {"zusammenfassung": "Änderung", "kriterien": []}
        self.urteile = urteile
        self._fenster = fenster
        self._faehigkeiten = faehigkeiten or {"completion"}
        self.anfragen: list[list[dict[str, Any]]] = []
        self.abnahmefragen: list[list[dict[str, Any]]] = []

    async def strukturiert(self, modell, nachrichten, schema, *, temperatur, verbrauch):
        eigenschaften = (schema or {}).get("properties", {})
        if "kriterien" in eigenschaften:
            self.anfragen.append(nachrichten)
            return self.vertrag
        if "ergebnisse" in eigenschaften:
            self.abnahmefragen.append(nachrichten)
            return self.urteile if self.urteile is not None else {"ergebnisse": []}
        self.anfragen.append(nachrichten)
        return self.verstaendnis

    async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
        self.anfragen.append(nachrichten)
        text = self.antworten.pop(0)
        for stelle in range(0, len(text), 400):
            yield {"text": text[stelle:stelle + 400]}
        yield {"ende": "stop"}

    async def faehigkeiten(self, modell):
        return self._faehigkeiten

    def fenster(self, modell):
        return self._fenster


def bericht(fehler: int = 0, luecken: int = 0, browser: bool = True) -> pruefer.Pruefbericht:
    befunde = [Befund("fehler", f"Fehler {n}", "technisch") for n in range(fehler)]
    befunde += [Befund("luecke", f"Lücke {n}") for n in range(luecken)]
    return pruefer.Pruefbericht(befunde, browser=browser, interaktion={"gefuellt": 2, "geklickt": 2})


class SpeicherTestfall(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        from app import database

        datenordner = Path(self.ordner.name) / "data"
        datenordner.mkdir()
        self.datenbank_umgebungen = [
            patch.object(database, "DATA_DIR", datenordner),
            patch.object(database, "DB_PATH", datenordner / "mini-llm.sqlite3"),
            patch.object(speicher, "DATA_DIR", datenordner),
            patch.object(speicher, "ORDNER", datenordner / "joshi"),
        ]
        for umgebung in self.datenbank_umgebungen:
            umgebung.start()
        from app.database import create_user, init_db

        init_db()
        speicher.tabellen_anlegen()
        nutzer = create_user("Test", f"t{os.urandom(4).hex()}@example.com", "geheim123")
        self.user = nutzer["id"]

    def tearDown(self):
        for umgebung in reversed(self.datenbank_umgebungen):
            umgebung.stop()
        self.ordner.cleanup()


def fuehre_lauf(user: str, art: str, zugang: GespielterZugang, eingabe: pipeline.Eingabe,
                berichte: list[pruefer.Pruefbericht] | None, produkt: dict[str, Any] | None = None
                ) -> tuple[Auftrag, dict[str, Any], list[dict[str, Any]], list[str]]:
    """Ein vollständiger JOSHI-Lauf im Test.

    Mit `berichte` wird die Prüfung gespielt, mit `berichte=None` prüft der
    echte WebKit-Prüfer.
    """
    produkt = produkt or speicher.produkt_anlegen(user, "Neu", eingabe.text, {"titel_auto": True})
    job = speicher.job_anlegen(user, produkt["id"], art, {"text": eingabe.text}, "testmodell")
    reihe = list(berichte or [])
    htmls: list[str] = []

    async def gespielte_pruefung(html, **_):
        htmls.append(html)
        return reihe.pop(0) if len(reihe) > 1 else reihe[0]

    async def ausfuehren():
        auftrag = Auftrag(job["id"], produkt["id"], user)
        lauf = pipeline.Lauf(auftrag, user_id=user, produkt=produkt, art=art, eingabe=eingabe,
                             modell="testmodell", zugang=zugang)
        if berichte is None:
            await lauf.ausfuehren()
        else:
            with patch.object(pipeline.pruefer, "pruefen", gespielte_pruefung):
                await lauf.ausfuehren()
        return auftrag

    auftrag = asyncio.run(ausfuehren())
    return auftrag, speicher.produkt(user, produkt["id"]), [json.loads(z) for z in auftrag.ereignisse], htmls


class PipelineTests(SpeicherTestfall):
    def lauf(self, art: str, zugang: GespielterZugang, eingabe: pipeline.Eingabe, berichte: list[pruefer.Pruefbericht],
             produkt: dict[str, Any] | None = None) -> tuple[Auftrag, dict[str, Any], list[dict[str, Any]]]:
        auftrag, produkt, ereignisse, htmls = fuehre_lauf(self.user, art, zugang, eingabe, berichte, produkt)
        self.htmls = htmls
        return auftrag, produkt, ereignisse

    def test_a_build_becomes_version_one_only_after_the_check(self):
        zugang = GespielterZugang(["```html\n" + BMI + "\n```"], verstaendnis="```json\n" + json.dumps({
            "titel": "BMI-Rechner", "zweck": "z", "art": "rechner", "funktionen": ["a", "b"],
            "bedienelemente": ["Berechnen"], "gestaltung": "g"}) + "\n```")
        auftrag, produkt, ereignisse = self.lauf("bauen", zugang, pipeline.Eingabe(text="BMI-Rechner bitte"), [bericht()])
        self.assertEqual(produkt["version"], 1)
        self.assertEqual(produkt["status"], "ready")
        self.assertEqual(produkt["titel"], "BMI-Rechner")
        arten = [e["type"] for e in ereignisse]
        self.assertLess(arten.index("verstaendnis"), arten.index("fertig"))
        schritte = [(e["schritt"], e["zustand"]) for e in ereignisse if e["type"] == "schritt"]
        self.assertIn(("pruefen", "fertig"), schritte)
        self.assertEqual(ereignisse[-1], {"type": "status", "status": "ready", "text": ereignisse[-1]["text"]})
        self.assertEqual(speicher.version(produkt["id"], 1)["html"], self.htmls[-1])

    def test_a_repair_that_makes_things_worse_is_discarded(self):
        kaputt = BMI.replace("rechne();", "rechne(); undefinierteFunktion();")
        schlimmer = "<<<<<<< SUCHEN\n<h1>BMI-Rechner</h1>\n=======\n<h1>BMI</h1>\n>>>>>>> ERSETZEN"
        zugang = GespielterZugang([kaputt, schlimmer, schlimmer])
        _, produkt, ereignisse = self.lauf(
            "bauen", zugang, pipeline.Eingabe(text="BMI"), [bericht(fehler=1), bericht(fehler=2), bericht(fehler=2)])
        version = speicher.version(produkt["id"], 1)
        self.assertIn("<h1>BMI-Rechner</h1>", version["html"])
        self.assertEqual(produkt["status"], "needs_attention")
        self.assertTrue(any("verschlechtert" in e.get("text", "") for e in ereignisse if e["type"] == "technik"))

    def test_static_fallback_is_saved_as_needs_attention(self):
        zugang = GespielterZugang(["```html\n" + BMI + "\n```"])
        auftrag, produkt, _ = self.lauf(
            "bauen", zugang, pipeline.Eingabe(text="BMI"), [bericht(browser=False)])
        self.assertEqual(produkt["status"], "needs_attention")
        job = speicher.job(self.user, auftrag.job_id)
        self.assertEqual(job["status"], "needs_attention")
        self.assertIsNotNone(job["beendet"])

    def test_small_files_are_rewritten_large_files_patched(self):
        erst = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(erst["id"], BMI, "Erstfassung", pruefung={"ok": True})
        speicher.produkt_aendern(self.user, erst["id"], version=1, status="ready")
        produkt = speicher.produkt(self.user, erst["id"])
        neu = BMI.replace("<h1>BMI-Rechner</h1>", "<h1>BMI-Rechner</h1><p>Erklärung</p>")
        zugang = GespielterZugang([neu])
        _, produkt, _ = self.lauf("aendern", zugang, pipeline.Eingabe(text="Füge eine Erklärung hinzu"), [bericht()], produkt)
        self.assertEqual(produkt["version"], 2)
        self.assertIn("<p>Erklärung</p>", speicher.version(produkt["id"], 2)["html"])
        aenderungsauftrag = [n[-1]["content"] for n in zugang.anfragen if "Aktuelle Datei:" in n[-1]["content"]][0]
        self.assertIn("vollständige geänderte HTML-Datei", aenderungsauftrag)

    def test_blocks_that_do_not_fit_are_retried_then_rewritten(self):
        gross = BMI.replace("<p id=\"ergebnis\"></p>", "<p id=\"ergebnis\"></p>" + "<!-- Füllung -->\n" * 600)
        erst = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(erst["id"], gross, "Erstfassung", pruefung={"ok": True})
        speicher.produkt_aendern(self.user, erst["id"], version=1, status="ready")
        produkt = speicher.produkt(self.user, erst["id"])
        falsch = "<<<<<<< SUCHEN\n<h2>gibt es nicht</h2>\n=======\n<h2>x</h2>\n>>>>>>> ERSETZEN"
        voll = gross.replace("Berechnen</button>", "Jetzt berechnen</button>")
        zugang = GespielterZugang([falsch, falsch, voll])
        _, produkt, ereignisse = self.lauf("aendern", zugang, pipeline.Eingabe(text="Knopf umbenennen"), [bericht()], produkt)
        self.assertEqual(produkt["version"], 2)
        self.assertIn("Jetzt berechnen", speicher.version(produkt["id"], 2)["html"])
        self.assertTrue(any("vollständig neu" in e.get("text", "") for e in ereignisse if e["type"] == "technik"))

    def test_a_failed_change_keeps_the_working_version(self):
        erst = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(erst["id"], BMI, "Erstfassung", pruefung={"ok": True})
        speicher.produkt_aendern(self.user, erst["id"], version=1, status="ready")
        produkt = speicher.produkt(self.user, erst["id"])
        zugang = GespielterZugang([BMI.replace("rechne();", "kaputt();")] * 3)
        _, produkt, ereignisse = self.lauf("aendern", zugang, pipeline.Eingabe(text="x"), [bericht(fehler=1)], produkt)
        self.assertEqual(produkt["version"], 1)
        self.assertEqual(produkt["status"], "ready")
        self.assertIn("Version 1 bleibt aktiv", [e for e in ereignisse if e["type"] == "fehler"][0]["text"])

    def test_a_too_small_window_is_said_plainly(self):
        gross = BMI + "<!-- x -->" * 4000
        erst = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(erst["id"], gross, "Erstfassung", pruefung={"ok": True})
        speicher.produkt_aendern(self.user, erst["id"], version=1, status="ready")
        produkt = speicher.produkt(self.user, erst["id"])
        zugang = GespielterZugang([], fenster=8192)
        _, _, ereignisse = self.lauf("aendern", zugang, pipeline.Eingabe(text="x"), [bericht()], produkt)
        fehler = [e for e in ereignisse if e["type"] == "fehler"][0]["text"]
        self.assertIn("Kontextfenster", fehler)
        self.assertIn("Cloud-Modell", fehler)

    def test_a_model_without_vision_is_told_honestly(self):
        bild = {"name": "bild-1", "datei": "logo.png", "mime": "image/png", "b64": "AAAA"}
        zugang = GespielterZugang([BMI])
        _, _, ereignisse = self.lauf("bauen", zugang, pipeline.Eingabe(text="Mit Logo", bilder=[bild]), [bericht()])
        self.assertTrue(any("keine Bilder sehen" in e.get("text", "") for e in ereignisse if e["type"] == "hinweis"))
        self.assertNotIn("images", zugang.anfragen[-1][-1])

    def test_a_vision_model_gets_the_image(self):
        bild = {"name": "bild-1", "datei": "logo.png", "mime": "image/png", "b64": "AAAA"}
        zugang = GespielterZugang([BMI], faehigkeiten={"completion", "vision"})
        self.lauf("bauen", zugang, pipeline.Eingabe(text="Mit Logo", bilder=[bild]), [bericht()])
        bauauftrag = [n[-1] for n in zugang.anfragen if "images" in n[-1]][-1]
        self.assertEqual(bauauftrag["images"], ["AAAA"])
        self.assertIn('src="joshi:bild-1"', bauauftrag["content"])


class JsonAusAntwortTests(unittest.TestCase):
    def test_fenced_json_is_read(self):
        self.assertEqual(pipeline.json_aus_antwort('```json\n{"titel": "A"}\n```'), {"titel": "A"})

    def test_prose_around_json_is_read(self):
        self.assertEqual(pipeline.json_aus_antwort('Klar: {"titel": "B"} fertig'), {"titel": "B"})

    def test_garbage_is_empty(self):
        self.assertEqual(pipeline.json_aus_antwort("nichts"), {})


# ---------------------------------------------------------------- Speicher
class SpeicherTests(SpeicherTestfall):
    def test_versions_are_stored_compressed(self):
        produkt = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(produkt["id"], BMI * 10, "Erstfassung")
        eintrag = speicher.versionen(produkt["id"])[0]
        self.assertLess(eintrag["gespeichert_bytes"], len(BMI * 10) / 3)
        self.assertEqual(speicher.version(produkt["id"], 1)["html"], BMI * 10)

    def test_products_belong_to_their_user(self):
        from app.database import create_user

        produkt = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        andere = create_user("Andere", f"a{os.urandom(4).hex()}@example.com", "geheim123")
        self.assertIsNone(speicher.produkt(andere["id"], produkt["id"]))
        self.assertFalse(speicher.produkt_loeschen(andere["id"], produkt["id"]))

    def test_the_same_image_is_stored_once(self):
        produkt = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        erstes = speicher.bild_speichern(produkt["id"], b"\x89PNG-daten", "image/png", "a.png")
        zweites = speicher.bild_speichern(produkt["id"], b"\x89PNG-daten", "image/png", "b.png")
        self.assertEqual(erstes["name"], zweites["name"])
        self.assertTrue(speicher.bild_data_uris(produkt["id"])["bild-1"].startswith("data:image/png;base64,"))

    def test_a_restart_ends_running_jobs_honestly(self):
        produkt = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        job = speicher.job_anlegen(self.user, produkt["id"], "bauen", {}, "m")
        speicher.job_aendern(job["id"], status="building")
        speicher.produkt_aendern(self.user, produkt["id"], status="building")
        speicher.nach_neustart_aufraeumen()
        self.assertEqual(speicher.job(self.user, job["id"])["status"], "failed")
        self.assertIn("neu gestartet", speicher.job(self.user, job["id"])["fehler"])
        self.assertEqual(speicher.produkt(self.user, produkt["id"])["status"], "failed")

    def test_restart_preserves_needs_attention_for_last_version(self):
        produkt = speicher.produkt_anlegen(self.user, "BMI", "BMI", {})
        speicher.version_anlegen(produkt["id"], BMI, "Erstfassung", pruefung={"ok": False})
        speicher.produkt_aendern(self.user, produkt["id"], version=1, status="building")
        speicher.nach_neustart_aufraeumen()
        self.assertEqual(speicher.produkt(self.user, produkt["id"])["status"], "needs_attention")


# ---------------------------------------------------------------- Brücke
class BrueckeTests(unittest.TestCase):
    def test_the_chat_handoff_never_carries_html(self):
        produkt = {"titel": "BMI", "version": 2, "auftrag": "BMI bitte", "verstaendnis": {"zweck": "BMI", "funktionen": ["a"]}}
        gliederung = {"felder": [{"label": "Gewicht (kg)", "wert": "82"}], "knoepfe": ["Berechnen"],
                      "markdown": "# BMI\n\n**Gewicht (kg):** 82"}
        text = bruecke.uebergabe(produkt, [{"nummer": 1, "aenderung": "Erstfassung"}], gliederung)
        self.assertIn("Gewicht (kg): 82", text)
        self.assertNotIn("<html", text.lower())
        self.assertLessEqual(len(text), bruecke.MAX_UEBERGABE)

    def test_a_chat_answer_with_a_full_app_is_imported(self):
        self.assertTrue(bruecke.html_im_chat("Hier:\n```html\n" + BMI + "\n```"))
        self.assertEqual(bruecke.html_im_chat("Ein Konzept ohne Code."), "")


# ---------------------------------------------------------------- Verdrahtung
class ArchitekturTests(unittest.TestCase):
    def test_joshi_has_no_own_ollama_connection_and_no_model_names(self):
        for datei in (WURZEL / "app/joshi").rglob("*.py"):
            text = datei.read_text(encoding="utf-8")
            # Einzige Ausnahme: die Export-Richtlinie nennt das lokale Ollama als
            # erlaubtes Ziel — JOSHI selbst verbindet sich nie damit.
            text = text.replace('KI_VERBINDUNG = "connect-src http://localhost:11434 http://127.0.0.1:11434"', "")
            text = re.sub(r"_KI_NUTZUNG = re\.compile\(.*\)\n", "", text)
            text = re.sub(r"_KI_ADRESSEN = re\.compile\(.*\)\n", "", text)
            self.assertNotIn("11434", text, datei)
            self.assertNotIn("OLLAMA_URL", text, datei)
            self.assertNotIn("/api/chat", text, datei)
            self.assertIsNone(re.search(r"\b(?:glm|granite|ministral|gpt-oss|kimi|deepseek|gemma|llama|qwen)", text, re.I), datei)

    def test_main_passes_the_central_model_layer(self):
        quelle = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("zugang=MiniLLMModellzugang()", quelle)
        self.assertIn("app.include_router(joshi_api.router)", quelle)
        self.assertNotIn("from app.coding", quelle)
        self.assertNotIn("/api/coding", quelle)

    def test_the_old_harness_is_gone_from_the_ui(self):
        html = (WURZEL / "static/index.html").read_text(encoding="utf-8")
        self.assertNotIn("coding-view", html)
        self.assertNotIn("Schritte", html)
        self.assertIn('id="joshi-view"', html)
        self.assertIn("← Zurück zum Chat".replace("← ", ""), html)
        self.assertFalse((WURZEL / "static/coding.js").exists())
        self.assertFalse((WURZEL / "app/coding.py").exists())

    def test_the_app_runs_sandboxed_without_own_origin(self):
        html = (WURZEL / "static/index.html").read_text(encoding="utf-8")
        rahmen = re.search(r'<iframe id="joshi-frame"[^>]*>', html, re.S).group(0)
        self.assertIn('sandbox="allow-scripts"', rahmen)
        self.assertNotIn("allow-same-origin", rahmen)

    def test_the_chat_bridge_is_wired(self):
        app_js = (WURZEL / "static/app.js").read_text(encoding="utf-8")
        joshi_js = (WURZEL / "static/joshi.js").read_text(encoding="utf-8")
        self.assertIn("Mit JOSHI umsetzen", app_js)
        self.assertIn("window.joshi.ausChat(", app_js)
        self.assertIn("window.miniLLM = { chatMitKontext: chatWithContext,", app_js)
        self.assertIn("window.miniLLM.chatMitKontext(", joshi_js)
        self.assertIn("produkt_id:", app_js)

    def test_messages_from_the_app_are_checked_for_their_source(self):
        joshi_js = (WURZEL / "static/joshi.js").read_text(encoding="utf-8")
        self.assertIn("if (ereignis.source !== knoten.rahmen.contentWindow) return;", joshi_js)

    def test_webkit_navigation_does_not_allow_preload_redirects(self):
        swift = (WURZEL / "app/joshi/renderer/joshi_render.swift").read_text(encoding="utf-8")
        self.assertNotIn("if !geladen || url.hasPrefix", swift)
        self.assertIn('url?.host == "produkt.joshi.invalid"', swift)

    def test_the_model_manager_survived(self):
        html = (WURZEL / "static/index.html").read_text(encoding="utf-8")
        modelle = (WURZEL / "static/modelle.js").read_text(encoding="utf-8")
        for kennung in re.findall(r'\$\$\("#([\w-]+)"\)', modelle):
            self.assertIn(f'id="{kennung}"', html, kennung)
        self.assertIn("data-open-models", html)


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class EchterRendererTests(unittest.TestCase):
    """Die Bedienprobe in echtem WebKit — so, wie JOSHI jedes Produkt prüft."""

    def pruefe(self, html: str, erwartet: list[str] | None = None) -> pruefer.Pruefbericht:
        return asyncio.run(pruefer.pruefen(html, erwartet=erwartet or []))

    def test_a_working_calculator_passes(self):
        ergebnis = self.pruefe(BMI, ["Berechnen", "Zurücksetzen"])
        self.assertTrue(ergebnis.ok, ergebnis.befunde)
        self.assertTrue(ergebnis.interaktion["reaktionKlick"])

    def test_a_script_error_is_found_with_its_line(self):
        ergebnis = self.pruefe(BMI.replace("document.getElementById('rechnen').onclick", "document.getElementById('x').onclick"))
        self.assertFalse(ergebnis.ok)
        technik = " ".join(b.technik for b in ergebnis.befunde)
        self.assertIn("TypeError", technik)
        self.assertRegex(technik, r"Zeile \d+")

    def test_nan_after_input_is_found(self):
        ergebnis = self.pruefe(BMI.replace("(g>0&&h>0)?'BMI: '", "'BMI: '").replace(":'Bitte Werte eingeben'", "")
                               .replace("parseFloat(document.getElementById('gewicht').value)", "undefined*1"))
        self.assertTrue(any("NaN" in b.text for b in ergebnis.befunde), ergebnis.befunde)

    def test_highlighting_a_choice_counts_as_reaction(self):
        knoepfe = "".join(f'<button type="button" class="w">{n}</button>' for n in range(1, 6))
        html = ("<!DOCTYPE html><html><head><title>Skala</title><style>.an{color:red}</style></head><body>"
                f"<h1>Wie zufrieden?</h1>{knoepfe}<script>document.querySelectorAll('.w').forEach(b=>b.onclick="
                "()=>{document.querySelectorAll('.w').forEach(x=>x.classList.remove('an'));b.classList.add('an');});"
                "</script></body></html>")
        ergebnis = self.pruefe(html)
        self.assertTrue(ergebnis.ok, ergebnis.befunde)

    def test_a_download_button_does_not_end_the_probe(self):
        html = BMI.replace("rechne();\n</script>", "rechne();\n"
                           "document.getElementById('csv').onclick=function(){var a=document.createElement('a');"
                           "a.href=URL.createObjectURL(new Blob(['x']));a.download='x.csv';document.body.appendChild(a);a.click();};"
                           "</script>").replace('<p id="ergebnis"></p>', '<p id="ergebnis"></p><button type="button" id="csv">Als CSV exportieren</button>')
        ergebnis = self.pruefe(html)
        self.assertTrue(ergebnis.interaktion, ergebnis.befunde)
        self.assertGreaterEqual(ergebnis.interaktion["geklickt"], 3)
        self.assertFalse(any("Bedienprobe konnte nicht" in b.text for b in ergebnis.befunde))

    def test_a_page_hidden_by_css_is_rejected(self):
        versteckt = BMI.replace("<title>BMI</title>", "<title>BMI</title><style>body *{display:none}</style>")
        ergebnis = self.pruefe(versteckt)
        self.assertFalse(ergebnis.ok)
        self.assertTrue(any("leer" in b.text for b in ergebnis.befunde), ergebnis.befunde)

    def test_a_full_page_image_is_not_cut_at_the_viewport(self):
        hoch = BMI.replace("<p id=\"ergebnis\"></p>", "<p id=\"ergebnis\"></p><div style=\"height:2400px\">lang</div>")
        messung = asyncio.run(renderer.rendern(html_werk.laufzeit_dokument(hoch, modus="pruefung"), bild=True, skala=1))
        self.assertGreater(messung.seitenhoehe, 2400)
        self.assertGreater(messung.roh["bild"]["hoehe"], 2400)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- Abnahme
KONFIGURATOR = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>KI-Schulung Angebotskonfigurator</title>
<style>body{font-family:system-ui;margin:24px}label{display:block;margin-top:8px}</style></head>
<body><h1>KI-Schulung Angebotskonfigurator</h1>
<label for="teilnehmer">Teilnehmer</label><input id="teilnehmer" type="number" value="10">
<label for="tage">Schulungstage</label><input id="tage" type="number" value="2">
<label for="satz">Tagessatz (€)</label><input id="satz" type="number" value="1800">
<label for="modul">Modul</label><select id="modul"><option>Grundlagen</option><option>Automatisierung</option></select>
<label for="inhouse"><input id="inhouse" type="checkbox"> Inhouse-Schulung</label>
<button type="button" id="rechnen">Berechnen</button>
<button type="button" id="reset">Zurücksetzen</button>
<button type="button" id="drucken">Angebot drucken</button>
<h2>Zusammenfassung</h2><p id="summe">–</p>
<script>
function rechne(){
  var t=parseFloat(document.getElementById('teilnehmer').value)||0;
  var d=parseFloat(document.getElementById('tage').value)||0;
  var s=parseFloat(document.getElementById('satz').value)||0;
  var preis=d*s*(document.getElementById('inhouse').checked?1:1.1);
  document.getElementById('summe').textContent='Angebotssumme: '+preis.toFixed(2)+' € für '+t+' Teilnehmer';
}
document.getElementById('rechnen').onclick=rechne;
document.getElementById('reset').onclick=function(){document.getElementById('teilnehmer').value='';document.getElementById('summe').textContent='–';};
document.querySelectorAll('input,select').forEach(function(e){e.addEventListener('input',rechne);});
rechne();
</script></body></html>"""

KANDIDAT_LEER = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>KI-Schulung Angebotskonfigurator</title></head>
<body></body></html>"""

KANDIDAT_OHNE_MASKE = KONFIGURATOR.replace(
    "document.getElementById('drucken').onclick",
    "document.getElementById('drucken').onclickAlt",
).replace(
    "<h2>Zusammenfassung</h2>",
    "<p id='hinweis'></p><h2>Zusammenfassung</h2>",
).replace(
    "rechne();\n</script>",
    "document.getElementById('drucken').onclick=function(){document.getElementById('hinweis')"
    ".textContent='Druckansicht wird vorbereitet';};\nrechne();\n</script>",
)

KANDIDAT_VOLLSTAENDIG = KONFIGURATOR.replace(
    "<h2>Zusammenfassung</h2>",
    """<div id="maske" style="display:none">
<h2>Angebotsdaten</h2>
<label for="absender">Absender (Name, Firma)</label><input id="absender" value="Beispiel-GmbH">
<label for="absender_adresse">Absender Adresse</label><input id="absender_adresse">
<label for="empfaenger">Empfänger (Kunde)</label><input id="empfaenger">
<label for="empfaenger_adresse">Empfänger Adresse</label><input id="empfaenger_adresse">
<button type="button" id="vorschau">Angebot erzeugen</button>
<button type="button" id="pdf">Als PDF speichern</button>
<button type="button" id="word">Als Word speichern</button>
<div id="angebot"></div></div><h2>Zusammenfassung</h2>""",
).replace(
    "rechne();\n</script>",
    """document.getElementById('drucken').onclick=function(){document.getElementById('maske').style.display='block';};
document.getElementById('vorschau').onclick=function(){
  document.getElementById('angebot').textContent='Angebot von '+document.getElementById('absender').value
    +' an '+document.getElementById('empfaenger').value+': '+document.getElementById('summe').textContent;};
document.getElementById('pdf').onclick=async function(){
  var a=await window.JOSHI.export({type:'pdf',target:'#angebot',filename:'angebot.pdf',title:'Angebot'});
  document.getElementById('angebot').textContent=a.ok?'PDF wurde erstellt':'PDF konnte nicht erstellt werden';};
document.getElementById('word').onclick=async function(){
  var a=await window.JOSHI.export({type:'docx',target:'#angebot',filename:'angebot.docx',title:'Angebot'});
  document.getElementById('angebot').textContent=a.ok?'Word-Datei wurde erstellt':'Word konnte nicht erstellt werden';};
rechne();
</script>""",
)

DRUCK_VERTRAG = {
    "zusammenfassung": "Druckfunktion um Angebotsdialog und Dokumentausgabe erweitern",
    "rueckbau": False,
    "kriterien": [
        {"id": "maske", "beschreibung": "Ein Klick auf „Angebot drucken“ öffnet eine Eingabemaske",
         "stichworte": ["Angebotsdaten"], "interaktion": True, "pflicht": True},
        {"id": "absender", "beschreibung": "Es gibt Eingabefelder für Absenderdaten",
         "stichworte": ["Absender"], "interaktion": True, "pflicht": True},
        {"id": "empfaenger", "beschreibung": "Es gibt Eingabefelder für Empfängerdaten",
         "stichworte": ["Empfänger"], "interaktion": True, "pflicht": True},
        {"id": "pdf", "beschreibung": "Das Angebot kann als PDF ausgegeben werden",
         "stichworte": ["PDF"], "interaktion": True, "pflicht": True},
        {"id": "word", "beschreibung": "Das Angebot kann als Word-Datei ausgegeben werden",
         "stichworte": ["Word"], "interaktion": True, "pflicht": True},
    ],
}


def gliederung_aus(felder: int, knoepfe: int, text: int, elemente: int = 0) -> dict[str, Any]:
    return {
        "felder": [{"label": f"Feld {n}", "typ": "text"} for n in range(felder)],
        "knoepfe": [f"Knopf {n}" for n in range(knoepfe)],
        "ueberschriften": ["Titel"] if text else [],
        "textLaenge": text,
        "anzahl": {"tabellen": 0, "diagramme": 0, "bilder": 0},
        "sichtbar": {"elemente": elemente or (felder + knoepfe + (2 if text else 0)),
                     "interaktiv": felder + knoepfe, "flaecheProzent": min(90, text // 10)},
        "markdown": "Inhalt " * (text // 8),
    }


class LeerUndRegressionTests(unittest.TestCase):
    """Geladen ist nicht gezeigt — und eine Änderung darf nichts wegreißen."""

    def test_an_empty_body_is_an_error(self):
        befunde = pruefer.leerbefunde(gliederung_aus(0, 0, 0))
        self.assertEqual([b.art for b in befunde], ["fehler"])
        self.assertIn("leer", befunde[0].text)

    def test_everything_hidden_counts_as_empty(self):
        versteckt = {"felder": [], "knoepfe": [], "textLaenge": 0, "anzahl": {},
                     "sichtbar": {"elemente": 0, "interaktiv": 0, "flaecheProzent": 0}}
        self.assertTrue(pruefer.leerbefunde(versteckt))

    def test_a_small_but_real_app_is_fine(self):
        self.assertEqual(pruefer.leerbefunde(gliederung_aus(1, 1, 120)), [])

    def test_losing_almost_everything_is_a_regression(self):
        vorher = gliederung_aus(11, 7, 900)
        nachher = gliederung_aus(0, 1, 40)
        befunde = pruefer.regressionsbefunde(vorher, nachher)
        self.assertEqual(befunde[0].art, "fehler")
        self.assertIn("vorher 900 Zeichen", befunde[0].technik)

    def test_a_requested_removal_is_allowed(self):
        vorher = gliederung_aus(11, 7, 900)
        nachher = gliederung_aus(2, 2, 200)
        self.assertTrue(pruefer.regressionsbefunde(vorher, nachher))
        self.assertEqual(pruefer.regressionsbefunde(vorher, nachher, rueckbau=True), [])

    def test_a_normal_change_is_no_regression(self):
        vorher = gliederung_aus(11, 7, 900)
        nachher = gliederung_aus(15, 9, 1100)
        self.assertEqual(pruefer.regressionsbefunde(vorher, nachher), [])

    def test_acceptance_findings_block_ready(self):
        bericht = pruefer.Pruefbericht([Befund("abnahme", "fehlt")], browser=True)
        self.assertFalse(bericht.ok)
        self.assertEqual(len(bericht.reparaturbedarf()), 1)


class AbnahmeTests(unittest.TestCase):
    """Der Auftrag gilt erst als umgesetzt, wenn die Messung ihn belegt."""

    def beweise(self, *, knoepfe=(), felder=(), klicks=(), text="") -> dict[str, Any]:
        return abnahme.beweise_sammeln(
            {"knoepfe": list(knoepfe), "felder": [{"label": f, "typ": "text"} for f in felder],
             "ueberschriften": ["Angebotskonfigurator"], "markdown": text, "anzahl": {}},
            {"klicks": list(klicks)},
        )

    def test_evidence_confirms_a_criterion(self):
        beweise = self.beweise(knoepfe=["Angebot drucken"], felder=["Absender (Name)", "Empfänger"],
                               klicks=[{"knopf": "Angebot drucken", "neueFelder": 2, "neueTexte": ["Angebotsdaten"]}])
        ergebnisse = {e.id: e.urteil for e in abnahme.deterministisch_pruefen(DRUCK_VERTRAG, beweise)}
        self.assertEqual(ergebnisse["absender"], "erfuellt")
        self.assertEqual(ergebnisse["empfaenger"], "erfuellt")
        self.assertEqual(ergebnisse["pdf"], "unklar")

    def test_an_interaction_criterion_needs_a_reacting_click(self):
        ohne_klick = self.beweise(knoepfe=["Angebot drucken"], felder=["Absender"], klicks=[])
        ergebnisse = {e.id: e.urteil for e in abnahme.deterministisch_pruefen(DRUCK_VERTRAG, ohne_klick)}
        self.assertEqual(ergebnisse["absender"], "unklar")

    def test_a_missing_requirement_fails_strictly(self):
        zugang = GespielterZugang([])
        beweise = self.beweise(knoepfe=["Berechnen"], felder=["Teilnehmer"], text="Angebotssumme")
        bericht = asyncio.run(abnahme.pruefen(zugang, "m", DRUCK_VERTRAG, beweise,
                                              verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(len(bericht.offen), 5)
        befund = bericht.befunde()[0]
        self.assertEqual(befund.art, "abnahme")
        self.assertIn("noch nicht umgesetzt", befund.text)

    def test_the_model_may_confirm_from_the_evidence(self):
        zugang = GespielterZugang([], urteile={"ergebnisse": [
            {"id": k["id"], "urteil": "erfuellt", "begruendung": "sichtbar"} for k in DRUCK_VERTRAG["kriterien"]]})
        beweise = self.beweise(knoepfe=["Angebot drucken"], felder=["Absender"], text="PDF Word Angebotsdaten Empfänger",
                               klicks=[{"knopf": "Angebot drucken", "neueFelder": 4, "neueTexte": ["Angebotsdaten"]}])
        bericht = asyncio.run(abnahme.pruefen(zugang, "m", DRUCK_VERTRAG, beweise,
                                              verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(bericht.offen, [])

    def test_the_review_never_sees_the_html_file(self):
        zugang = GespielterZugang([])
        beweise = self.beweise(knoepfe=["Berechnen"], felder=["Teilnehmer"])
        asyncio.run(abnahme.pruefen(zugang, "m", DRUCK_VERTRAG, beweise,
                                    verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        gesendet = zugang.abnahmefragen[0][-1]["content"]
        self.assertNotIn("<script", gesendet)
        self.assertNotIn("<!DOCTYPE", gesendet)
        self.assertLess(len(gesendet), 6000)

    def test_without_measurable_evidence_there_is_no_verdict(self):
        self.assertFalse(abnahme.beweisbar(abnahme.beweise_sammeln({}, {})))
        self.assertTrue(abnahme.beweisbar(abnahme.beweise_sammeln({"knoepfe": ["Drucken"]}, {})))

    def test_a_build_only_hints_but_never_blocks(self):
        vertrag = abnahme.vertrag_aus_verstaendnis(
            {"zweck": "Angebote rechnen", "funktionen": ["Teilnehmerzahl eingeben", "Summe berechnen"]}, "Auftrag")
        self.assertTrue(all(k["pflicht"] is False for k in vertrag["kriterien"]))
        bericht = asyncio.run(abnahme.pruefen(GespielterZugang([]), "m", vertrag,
                                              self.beweise(knoepfe=["Nichts"]), streng=False,
                                              verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(bericht.befunde(), [])

    def test_a_contract_falls_back_to_the_wish_itself(self):
        vertrag = asyncio.run(abnahme.vertrag_erzeugen(
            GespielterZugang([], vertrag={"kriterien": []}), "m",
            wunsch="Füge einen Knopf für den PDF-Export hinzu", bestand="",
            verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(len(vertrag["kriterien"]), 1)
        self.assertIn("export", " ".join(vertrag["kriterien"][0]["stichworte"]).lower())


class KandidatTests(SpeicherTestfall):
    """Transaktionale Versionierung: Ein Kandidat wird erst aktiv, wenn er besteht."""

    def produkt_mit_version(self, html: str = KONFIGURATOR, ok: bool = True) -> dict[str, Any]:
        produkt = speicher.produkt_anlegen(self.user, "Angebotskonfigurator", "Konfigurator bauen", {})
        speicher.version_festschreiben(produkt["id"], html, "Erstfassung", pruefung={
            "ok": ok, "browser": True, "kurz": "Lädt fehlerfrei.",
            "gliederung": gliederung_aus(5, 3, 700)},
            aktivieren=True, status="ready" if ok else "needs_attention")
        speicher.zustand_speichern(self.user, produkt["id"], {"v": 1, "felder": {"#teilnehmer": "12"}, "speicher": {}})
        return speicher.produkt(self.user, produkt["id"])

    def test_a_failed_change_keeps_version_state_and_history(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KANDIDAT_LEER] * 3, vertrag=DRUCK_VERTRAG)
        auftrag, nachher, ereignisse, _ = fuehre_lauf(
            self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
            [bericht(fehler=1)], produkt)
        self.assertEqual(nachher["version"], 1)                      # aktive Version unverändert
        self.assertEqual(nachher["status"], "ready")
        self.assertEqual(nachher["zustand"]["felder"], {"#teilnehmer": "12"})   # Zustand bleibt
        versionen = speicher.versionen(produkt["id"])
        self.assertEqual([v["nummer"] for v in versionen], [1, 2])   # Kandidat bleibt nachlesbar
        self.assertEqual(speicher.version(produkt["id"], 1)["html"], KONFIGURATOR)
        job = speicher.job(self.user, auftrag.job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("letzte funktionierende Version", job["ergebnis"]["text"])
        self.assertEqual(job["ergebnis"]["kandidat"], 2)

    def teilbericht(self, fehler: int = 0) -> pruefer.Pruefbericht:
        """Läuft, ein Pflichtpunkt nachgewiesen, einer offen."""
        befunde = [Befund("fehler", f"Fehler {n}", "technisch") for n in range(fehler)]
        befunde.append(Befund("abnahme", "Die gewünschte Änderung ist noch nicht umgesetzt: Druckknopf"))
        b = pruefer.Pruefbericht(befunde, browser=True, interaktion={"gefuellt": 1, "geklickt": 1})
        b.abnahme = {"zaehlung": {"PASS": 1, "FAIL": 1, "NOT_PROVEN": 0}, "ergebnisse": [
            {"id": "maske", "beschreibung": "Eine Druckmaske erscheint", "status": "PASS", "pflicht": True},
            {"id": "knopf", "beschreibung": "Ein Druckknopf druckt", "status": "FAIL", "pflicht": True}]}
        return b

    def test_a_working_partial_change_becomes_the_active_version(self):
        # 29.09.2026: „JOSHI soll bei einer Änderung zumindest eine funktionierende Version schaffen.“
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KONFIGURATOR.replace("</body>", "<p>Druckmaske</p></body>")] * 3,
                                  vertrag=DRUCK_VERTRAG)
        with patch.object(pipeline.Lauf, "abnehmen", new=lambda *a, **k: asyncio.sleep(0)):
            auftrag, nachher, ereignisse, _ = fuehre_lauf(
                self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
                [self.teilbericht()] * 3, produkt)
        self.assertEqual(nachher["version"], 2)
        self.assertEqual(nachher["status"], "needs_attention")
        job = speicher.job(self.user, auftrag.job_id)
        self.assertIn("teilweise umgesetzt: 1 von 2", job["ergebnis"]["text"])
        self.assertIn("Offen: Ein Druckknopf druckt", job["ergebnis"]["warnungen"])
        linie = speicher.offene_aenderung(produkt["id"])
        self.assertIsNotNone(linie)                                   # „versuch es erneut“ holt den Rest nach

    def test_a_partial_change_with_errors_is_still_rejected(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KONFIGURATOR] * 3, vertrag=DRUCK_VERTRAG)
        with patch.object(pipeline.Lauf, "abnehmen", new=lambda *a, **k: asyncio.sleep(0)):
            _, nachher, _, _ = fuehre_lauf(self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
                                           [self.teilbericht(fehler=1)] * 3, produkt)
        self.assertEqual(nachher["version"], 1)

    def test_two_failed_repairs_keep_the_old_version(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KANDIDAT_LEER] * 3, vertrag=DRUCK_VERTRAG)
        _, nachher, ereignisse, htmls = fuehre_lauf(
            self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
            [bericht(fehler=1)], produkt)
        # Erstversuch plus eine Reparatur: Die Reparatur änderte nichts an den
        # Befunden, also rät JOSHI nicht ein zweites Mal (Stillstandsregel).
        self.assertEqual(len(htmls), 2)
        self.assertTrue(any("ohne messbare Wirkung" in e.get("text", "") for e in ereignisse if e["type"] == "technik"))
        self.assertEqual(nachher["version"], 1)
        self.assertTrue(any("noch nicht vollständig umsetzen" in e.get("text", "")
                            for e in ereignisse if e["type"] == "fehler"))

    def test_changing_findings_still_get_both_repairs(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KANDIDAT_LEER] * 3, vertrag=DRUCK_VERTRAG)
        berichte = [pruefer.Pruefbericht([Befund("fehler", f"Fehler {n}", f"Zeile {n}")], browser=True,
                                         interaktion={"gefuellt": 1, "geklickt": 1}) for n in range(3)]
        _, nachher, _, htmls = fuehre_lauf(self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
                                           [*berichte, berichte[-1]], produkt)
        self.assertEqual(len(htmls), 1 + pipeline.MAX_REPARATUREN)
        self.assertEqual(nachher["version"], 1)

    def test_export_and_runtime_still_use_the_good_version(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KANDIDAT_LEER] * 3, vertrag=DRUCK_VERTRAG)
        fuehre_lauf(self.user, "aendern", zugang, pipeline.Eingabe(text="Druckmaske ergänzen"),
                    [bericht(fehler=1)], produkt)
        aktiv = speicher.produkt(self.user, produkt["id"])
        version = speicher.version(produkt["id"], aktiv["version"])
        portabel = export.portables_html(aktiv, version, {}).decode()
        self.assertIn("Angebotskonfigurator", portabel)
        self.assertIn("Berechnen", portabel)
        self.assertIn('"#teilnehmer": "12"', portabel)               # Zustand der guten Version

    def test_a_passing_change_becomes_active_in_one_step(self):
        produkt = self.produkt_mit_version()
        zugang = GespielterZugang([KANDIDAT_VOLLSTAENDIG], vertrag={"zusammenfassung": "x", "kriterien": []})
        _, nachher, _, _ = fuehre_lauf(self.user, "aendern", zugang, pipeline.Eingabe(text="Maske ergänzen"),
                                       [bericht()], produkt)
        self.assertEqual(nachher["version"], 2)
        self.assertEqual(nachher["status"], "ready")
        self.assertTrue(speicher.versionen(produkt["id"])[1]["ok"])

    def test_a_first_build_stays_visible_even_with_findings(self):
        zugang = GespielterZugang([BMI] * (1 + pipeline.MAX_REPARATUREN))
        _, produkt, _, _ = fuehre_lauf(self.user, "bauen", zugang, pipeline.Eingabe(text="BMI"), [bericht(fehler=1)])
        self.assertEqual(produkt["version"], 1)
        self.assertEqual(produkt["status"], "needs_attention")


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class AbnahmeKetteTests(SpeicherTestfall):
    """Der reale Fall aus dem Torture-Test — mit echter WebKit-Prüfung.

    Ein funktionierender Angebotskonfigurator, dann der Wunsch nach Druckmaske,
    Absender, Empfänger, PDF und Word. Drei Kandidaten nacheinander:
    leer, lauffähig aber unvollständig, vollständig.
    """

    def aufsetzen(self) -> dict[str, Any]:
        zugang = GespielterZugang([KONFIGURATOR])
        _, produkt, _, _ = fuehre_lauf(self.user, "bauen", zugang,
                                       pipeline.Eingabe(text="Angebotskonfigurator für KI-Schulungen"), None)
        self.assertEqual(produkt["status"], "ready", "Ausgangsprodukt muss geprüft bereit sein")
        speicher.zustand_speichern(self.user, produkt["id"], {"v": 1, "felder": {"#tage": "3"}, "speicher": {}})
        return speicher.produkt(self.user, produkt["id"])

    def aendern(self, produkt: dict[str, Any], kandidaten: list[str]):
        zugang = GespielterZugang(kandidaten, vertrag=DRUCK_VERTRAG)
        return fuehre_lauf(self.user, "aendern", zugang, pipeline.Eingabe(
            text="Angebot drucken löst noch nichts aus. Beim Klick soll eine Maske erscheinen, in der Absender- "
                 "und Empfängerdaten eingegeben werden. Daraus soll ein sauberes Angebot entstehen, das als PDF "
                 "und Word ausgegeben werden kann."), None, produkt)

    def test_the_three_candidates_behave_as_required(self):
        produkt = self.aufsetzen()
        basis = speicher.version(produkt["id"], 1)
        self.assertTrue(basis["pruefung"]["gliederung"]["felder"], "Baseline braucht Messwerte")

        # Kandidat 1: lädt, ist aber leer → abgelehnt, alte Version bleibt aktiv.
        _, nachher, ereignisse, _ = self.aendern(produkt, [KANDIDAT_LEER] * 3)
        self.assertEqual(nachher["version"], 1)
        self.assertEqual(nachher["status"], "ready")
        kandidat = speicher.version(produkt["id"], 2)
        self.assertTrue(kandidat["pruefung"]["abgelehnt"])
        self.assertTrue(any("leer" in b["text"] or "entfernt" in b["text"]
                            for b in kandidat["pruefung"]["befunde"]), kandidat["pruefung"]["befunde"])

        # Kandidat 2: technisch in Ordnung, Auftrag aber nicht umgesetzt → abgelehnt.
        produkt = speicher.produkt(self.user, produkt["id"])
        _, nachher, ereignisse, _ = self.aendern(produkt, [KANDIDAT_OHNE_MASKE] * 3)
        self.assertEqual(nachher["version"], 1, "unvollständige Umsetzung darf nicht aktiv werden")
        abgelehnt = speicher.version(produkt["id"], speicher.versionen(produkt["id"])[-1]["nummer"])
        befunde = abgelehnt["pruefung"]["befunde"]
        self.assertFalse([b for b in befunde if b["art"] == "fehler"], f"technisch sollte es laufen: {befunde}")
        self.assertTrue([b for b in befunde if b["art"] == "abnahme"], f"Abnahme muss greifen: {befunde}")
        offen = [e["id"] for e in abgelehnt["pruefung"]["abnahme"]["ergebnisse"] if e["urteil"] == "fehlt"]
        self.assertIn("absender", offen)
        self.assertIn("word", offen)

        # Kandidat 3: erfüllt den Auftrag → erst jetzt aktiv und bereit.
        produkt = speicher.produkt(self.user, produkt["id"])
        auftrag, nachher, _, _ = self.aendern(produkt, [KANDIDAT_VOLLSTAENDIG])
        self.assertEqual(nachher["status"], "ready")
        self.assertGreater(nachher["version"], 1)
        aktiv = speicher.version(produkt["id"], nachher["version"])
        self.assertIn("Angebotsdaten", aktiv["html"])
        urteile = {e["id"]: e["urteil"] for e in aktiv["pruefung"]["abnahme"]["ergebnisse"]}
        self.assertEqual(set(urteile.values()), {"erfuellt"}, urteile)
        self.assertEqual(speicher.job(self.user, auftrag.job_id)["status"], "ready")
        self.assertEqual(speicher.produkt(self.user, produkt["id"])["zustand"]["felder"], {"#tage": "3"})

    def test_an_empty_candidate_is_never_promoted(self):
        produkt = self.aufsetzen()
        _, nachher, _, _ = self.aendern(produkt, [KANDIDAT_LEER] * 3)
        aktiv = speicher.version(produkt["id"], nachher["version"])
        self.assertIn("Angebotskonfigurator", aktiv["html"])
        self.assertIn("Berechnen", aktiv["html"])


class VertragRobustheitTests(unittest.TestCase):
    """Modelle halten sich nicht immer ans Schema."""

    def test_keywords_given_as_one_string_are_split(self):
        vertrag = abnahme.vertrag_normalisieren({"zusammenfassung": "x", "kriterien": [
            {"id": "druck", "beschreibung": "Maske erscheint", "stichworte": "Angebot drucken, Absender"}]}, "x")
        self.assertEqual(vertrag["kriterien"][0]["stichworte"], ["Angebot drucken", "Absender"])

    def test_single_letters_are_dropped(self):
        self.assertEqual(abnahme.stichwortliste(["A", "n", "Absender"]), ["Absender"])

    def test_a_garbled_answer_yields_no_criteria(self):
        self.assertEqual(abnahme.vertrag_normalisieren("kein JSON", "Auftrag")["kriterien"], [])


class MehrstufigeAbnahmeTests(unittest.TestCase):
    """Ein Eingeben-Speichern-Anzeigen-Wunsch braucht seine eigene Bedienfolge."""

    def vertrag(self):
        return {"zusammenfassung": "Eigene Übung eintragen", "kriterien": [{
            "id": "eigene_uebung_eintragen",
            "beschreibung": "Über den Knopf „Übung hinzufügen“ kann der Nutzer eine eigene Übung mit Namen "
                            "eintragen und speichern; sie erscheint danach in der Übungsliste.",
            "stichworte": ["Übung hinzufügen", "Eigene Übung", "Name", "Übungsliste"],
            "nachweis": "bedienung", "aktion": "speichern", "pflicht": True,
        }]}

    def gliederung(self):
        return {"knoepfe": ["Als PDF sichern", "Übung hinzufügen"],
                "felder": [{"id": "eigene-name", "label": "Eigene Übung", "typ": "text"}],
                "ueberschriften": ["Übungsliste"], "markdown": "Eigene Übung hinzufügen"}

    def test_unrelated_save_probe_cannot_pass_a_frozen_multistep_contract(self):
        vertrag = self.vertrag()
        self.assertEqual([k["id"] for k in abnahme.szenario_kriterien(vertrag)], ["eigene_uebung_eintragen"])
        self.assertNotIn("speichern", abnahme.benoetigte_proben(vertrag))
        beweise = abnahme.beweise_sammeln(
            self.gliederung(), {"klicks": [{"knopf": "Als PDF sichern", "effekte": ["export_requested"]}]},
            aktionen=[{"aktion": "speichern", "knopf": "Als PDF sichern", "ergebnis": "bestanden",
                       "belege": ["export_requested"]}])
        ergebnis = abnahme.deterministisch_pruefen(vertrag, beweise)[0]
        self.assertEqual(ergebnis.status, "NOT_PROVEN")
        zugang = GespielterZugang([], urteile={"ergebnisse": [{
            "id": "eigene_uebung_eintragen", "urteil": "erfuellt", "beleg": "klick:Als PDF sichern"}]})
        bericht = asyncio.run(abnahme.pruefen(
            zugang, "m", vertrag, beweise,
            verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(bericht.ergebnisse[0].status, "NOT_PROVEN")
        self.assertEqual(zugang.abnahmefragen, [], "kein Modellurteil darf die fehlende Browserfolge ersetzen")

        beweise = abnahme.beweise_sammeln(
            self.gliederung(), {}, szenarien=[{"id": "s_eigene_uebung_eintragen",
                                            "kriterium": "eigene_uebung_eintragen", "ergebnis": "bestanden"}])
        ergebnis = abnahme.deterministisch_pruefen(vertrag, beweise)[0]
        self.assertEqual(ergebnis.status, "PASS")
        self.assertEqual(ergebnis.beleg, "szenario:s_eigene_uebung_eintragen")

    def test_derived_scenario_uses_measured_field_button_and_reload(self):
        zugang = GespielterZugang([])
        szenarien = asyncio.run(abnahme.szenarien_erzeugen(
            zugang, "m", kriterien=abnahme.szenario_kriterien(self.vertrag()),
            gliederung=self.gliederung(),
            verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(len(szenarien), 1)
        self.assertEqual(zugang.anfragen, [], "eindeutige Browserziele brauchen keinen Modellaufruf")
        schritte = szenarien[0]["schritte"]
        self.assertEqual([s["art"] for s in schritte], ["text_fehlt", "eingeben", "klicken", "text_enthaelt",
                                                     "neu_laden", "text_enthaelt", "keine_fehler"])
        self.assertEqual(schritte[1]["ziel"], "eigene-name")
        self.assertEqual(schritte[2]["ziel"], "Übung hinzufügen")
        self.assertEqual(schritte[1]["wert"], schritte[3]["wert"])
        self.assertEqual(schritte[1]["wert"], schritte[5]["wert"])
        self.assertFalse(abnahme.szenarien_normalisieren(
            {"szenarien": [{"kriterium": "eigene_uebung_eintragen", "schritte": [
                {"art": "eingeben", "ziel": "eigene-name", "wert": "Testname"},
                {"art": "klicken", "ziel": "Übung hinzufügen"}, {"art": "text_enthaelt", "wert": "Testname"}]}]},
            ["eigene_uebung_eintragen"], mehrschritt_ids={"eigene_uebung_eintragen"}))

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer nicht verfügbar")
    def test_derived_scenario_proves_real_persisted_list_entry(self):
        html = """<!DOCTYPE html><html><head><title>Übungsliste</title></head><body>
        <h1>Übungsliste</h1><label for="eigene-name">Eigene Übung</label><input id="eigene-name">
        <button id="btn-eigene">Übung hinzufügen</button><ul id="liste"></ul>
        <script>
        const key='uebungen-test';
        function zeigen(){document.getElementById('liste').innerHTML=JSON.parse(localStorage.getItem(key)||'[]')
          .map(x=>'<li>'+x+'</li>').join('');}
        document.getElementById('btn-eigene').onclick=()=>{let x=document.getElementById('eigene-name').value.trim();
          if(x){let a=JSON.parse(localStorage.getItem(key)||'[]');a.push(x);localStorage.setItem(key,JSON.stringify(a));zeigen();}};
        zeigen();
        </script></body></html>"""
        zugang = GespielterZugang([])
        szenario = asyncio.run(abnahme.szenarien_erzeugen(
            zugang, "m", kriterien=abnahme.szenario_kriterien(self.vertrag()),
            gliederung=self.gliederung(),
            verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))[0]
        _, ergebnisse = asyncio.run(pruefer.szenarien_ausfuehren(html, szenarien=[szenario]))
        self.assertEqual(ergebnisse[0]["ergebnis"], "bestanden", ergebnisse)


# ------------------------------------------------- Host Capability Bridge
ANGEBOT_MIT_EXPORT = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>Angebot</title></head><body>
<h1>Angebotskonfigurator</h1>
<label for="tage">Schulungstage</label><input id="tage" type="number" value="2">
<button type="button" id="drucken">Angebot drucken / als PDF speichern</button>
<button type="button" id="word">Als Word-Datei (.docx) herunterladen</button>
<section id="angebot"><h2>Angebot A-2026-014</h2>
<p><b>Absender:</b> Beispiel-GmbH</p><p><b>Empfänger:</b> Kunde AG</p>
<table><tr><th>Pos.</th><th>Leistung</th><th>Betrag</th></tr>
<tr><td>1</td><td>KI-Schulung</td><td>3.600,00 €</td></tr></table>
<p>Netto 3.600,00 € · MwSt. 684,00 € · Gesamt 4.284,00 €</p></section>
<p id="hinweis"></p>
<script>
async function hole(typ, name) {
  const antwort = await window.JOSHI.export({ type: typ, target: "#angebot", filename: name, title: "Angebot" });
  document.getElementById('hinweis').textContent = antwort.ok
    ? (typ === 'pdf' ? 'PDF' : 'Word-Datei') + ' wurde erstellt' : 'Export fehlgeschlagen';
}
document.getElementById('drucken').onclick = () => hole('pdf', 'angebot.pdf');
document.getElementById('word').onclick = () => hole('docx', 'angebot.docx');
</script></body></html>"""


class FakeRequest:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}


class ExportBrueckeTests(SpeicherTestfall):
    """Die Anwendung beschreibt den Export, JOSHI führt ihn aus — und prüft ihn."""

    def setUp(self):
        super().setUp()
        from app.joshi import api

        self.api = api
        api.einrichten(api.Anbindung(
            nutzer=lambda request: {"id": self.user},
            zugang=GespielterZugang([]),
            anhaenge=None, lese_upload=None, kontexte=None,
        ))
        self.produkt = speicher.produkt_anlegen(self.user, "Angebot", "Angebotskonfigurator", {})
        speicher.version_festschreiben(self.produkt["id"], ANGEBOT_MIT_EXPORT, "Erstfassung",
                                       pruefung={"ok": True, "browser": True}, aktivieren=True, status="ready")
        self.produkt = speicher.produkt(self.user, self.produkt["id"])

    def anfrage(self, format_: str = "pdf", **felder: Any):
        daten = {"version": self.produkt["version"], "ziel": "#angebot", "dateiname": "angebot",
                 "titel": "Angebot", "html": "<section id='angebot'><h2>Angebot</h2><p>Gesamt 4.284,00 €</p></section>",
                 "css": "h2{font-size:20px}", **felder}
        return asyncio.run(self.api.export_aus_anwendung(FakeRequest(), self.produkt["id"], format_, daten))

    def fehler(self, format_: str = "pdf", produkt_id: str | None = None, **felder: Any) -> tuple[int, str]:
        from fastapi import HTTPException

        try:
            self.anfrage(format_, **felder) if produkt_id is None else asyncio.run(
                self.api.export_aus_anwendung(FakeRequest(), produkt_id, format_,
                                              {"version": 1, "html": "<p>x</p>"}))
        except HTTPException as ausnahme:
            return ausnahme.status_code, str(ausnahme.detail)
        return 200, ""

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer nicht übersetzt")
    def test_a_valid_pdf_request_returns_a_pdf(self):
        antwort = self.anfrage("pdf")
        self.assertEqual(antwort.media_type, "application/pdf")
        self.assertTrue(antwort.body.startswith(b"%PDF"))
        self.assertIn('filename="angebot.pdf"', antwort.headers["content-disposition"])

    @unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer nicht übersetzt")
    def test_a_valid_docx_request_returns_a_real_docx(self):
        antwort = self.anfrage("docx", dateiname="angebot.docx")
        self.assertTrue(export.ist_gueltig(antwort.body, "docx"))
        from docx import Document

        text = " ".join(p.text for p in Document(io.BytesIO(antwort.body)).paragraphs)
        self.assertIn("4.284,00", text)

    def test_an_unknown_capability_is_refused(self):
        for format_ in ("eml", "html", "zip", "../pdf"):
            status, _ = self.fehler(format_)
            self.assertIn(status, {403, 404}, format_)

    def test_a_foreign_product_is_refused(self):
        from app.database import create_user

        fremd = create_user("Fremd", f"f{os.urandom(4).hex()}@example.com", "geheim123")
        fremdes = speicher.produkt_anlegen(fremd["id"], "Fremd", "x", {})
        status, meldung = self.fehler(produkt_id=fremdes["id"])
        self.assertEqual(status, 404)
        self.assertIn("nicht", meldung)

    def test_an_inactive_version_is_refused(self):
        status, meldung = self.fehler(version=self.produkt["version"] + 1)
        self.assertEqual(status, 409)
        self.assertIn("aktive Version", meldung)

    def test_an_empty_section_is_refused(self):
        status, meldung = self.fehler(html="   ")
        self.assertEqual(status, 422)

    def test_an_oversized_section_is_refused(self):
        status, _ = self.fehler(html="<p>x</p>" * 200000)
        self.assertEqual(status, 413)

    def test_filenames_are_sanitised(self):
        for wunsch, erwartet in (("../../etc/passwd", "passwd.pdf"), ("angebot ki-schulung.pdf", "angebot-ki-schulung.pdf"),
                                 ("bericht\x00.pdf", "bericht.pdf"), ("", "angebot.pdf")):
            self.assertEqual(self.api._dateiname(wunsch, "pdf", {"titel": "Angebot"}), erwartet)

    def test_scripts_in_the_section_are_dropped(self):
        dokument = html_werk.abschnitt_dokument(
            "<div onclick='boese()'>Hallo<script>fetch('https://example.com')</script></div>", "", "T")
        self.assertNotIn("<script", dokument.lower())
        self.assertNotIn("onclick", dokument)
        self.assertIn("connect-src 'none'", dokument)

    def test_acceptance_needs_a_real_file_not_just_a_button(self):
        vertrag = {"zusammenfassung": "Export", "kriterien": [
            {"id": "pdf", "beschreibung": "Angebot als PDF ausgeben", "stichworte": ["PDF"],
             "interaktion": False, "pflicht": True},
            {"id": "word", "beschreibung": "Angebot als Word herunterladen", "stichworte": ["Word"],
             "interaktion": False, "pflicht": True}]}
        nur_knopf = abnahme.beweise_sammeln(
            {"knoepfe": ["Als PDF speichern", "Als Word-Datei herunterladen"], "felder": [], "markdown": "Angebot"},
            {}, None, [])
        urteile = {e.id: e.urteil for e in abnahme.deterministisch_pruefen(vertrag, nur_knopf)}
        self.assertEqual(urteile, {"pdf": "unklar", "word": "unklar"})

        mit_datei = abnahme.beweise_sammeln(
            {"knoepfe": ["Als PDF speichern", "Als Word-Datei herunterladen"], "felder": [], "markdown": "Angebot"},
            {}, None, [{"typ": "pdf", "ok": True, "bytes": 9000}, {"typ": "docx", "ok": True, "bytes": 30000}])
        ergebnisse = abnahme.deterministisch_pruefen(vertrag, mit_datei)
        self.assertEqual({e.id: e.urteil for e in ergebnisse}, {"pdf": "erfuellt", "word": "erfuellt"})
        self.assertIn("Datei erzeugt", ergebnisse[0].begruendung)

    def test_a_failed_export_is_no_evidence(self):
        vertrag = {"kriterien": [{"id": "pdf", "beschreibung": "PDF ausgeben", "stichworte": ["PDF"], "pflicht": True}]}
        beweise = abnahme.beweise_sammeln({"knoepfe": ["PDF"], "markdown": "x"}, {}, None,
                                          [{"typ": "pdf", "ok": False, "grund": "leer"}])
        self.assertEqual(abnahme.deterministisch_pruefen(vertrag, beweise)[0].urteil, "unklar")

    def test_apps_without_the_api_still_work(self):
        self.assertNotIn("JOSHI.export", KONFIGURATOR)
        bericht = pruefer.Pruefbericht([], browser=True, gliederung=gliederung_aus(5, 3, 700))
        self.assertTrue(bericht.ok)
        self.assertEqual(bericht.exporte, [])


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class ExportBrueckeEchtTests(unittest.TestCase):
    """Die Bridge im echten WebKit — von der Anwendung bis zur fertigen Datei."""

    def test_the_probe_triggers_real_documents(self):
        bericht = asyncio.run(pruefer.pruefen(ANGEBOT_MIT_EXPORT))
        self.assertTrue(bericht.ok, bericht.befunde)
        arten = {e["typ"]: e for e in bericht.exporte}
        self.assertEqual(set(arten), {"pdf", "docx"})
        self.assertTrue(all(e["ok"] and e["bytes"] > 1000 for e in arten.values()), bericht.exporte)
        rueckmeldung = " ".join([*(k.get("neuerText", "") for k in bericht.interaktion.get("klicks", [])),
                                 *(t for k in bericht.interaktion.get("klicks", []) for t in k.get("neueTexte", []))])
        self.assertIn("wurde erstellt", rueckmeldung, bericht.interaktion.get("klicks"))

    def test_the_app_only_sees_a_tiny_api(self):
        probe = "return JSON.stringify({schluessel: Object.keys(window.JOSHI).sort(), typ: typeof window.JOSHI.export});"
        messung = asyncio.run(renderer.rendern(
            html_werk.laufzeit_dokument(ANGEBOT_MIT_EXPORT, modus="pruefung"), probe=probe))
        self.assertEqual(messung.probe["schluessel"], ["export", "formate", "ki", "version"])
        self.assertEqual(messung.probe["typ"], "function")

    def test_an_unknown_target_fails_cleanly(self):
        probe = ("const a = await window.JOSHI.export({type:'pdf', target:'#gibtesnicht'});"
                 "const b = await window.JOSHI.export({type:'exe', target:'#angebot'});"
                 "return JSON.stringify({a, b});")
        messung = asyncio.run(renderer.rendern(
            html_werk.laufzeit_dokument(ANGEBOT_MIT_EXPORT, modus="pruefung"), probe=probe))
        self.assertFalse(messung.probe["a"]["ok"])
        self.assertIn("nicht gefunden", messung.probe["a"]["error"])
        self.assertFalse(messung.probe["b"]["ok"])
        self.assertEqual(messung.probe.get("fehler"), None)

    def test_the_exported_file_keeps_working_offline(self):
        dokument = html_werk.export_dokument(ANGEBOT_MIT_EXPORT, zustand={}, meta={"joshi": 1, "titel": "Angebot"})
        probe = ("const a = await window.JOSHI.export({type:'docx', target:'#angebot'});"
                 "return JSON.stringify({ok: a.ok, fehler: a.error || ''});")
        messung = asyncio.run(renderer.rendern(dokument, probe=probe))
        self.assertFalse(messung.probe["ok"])
        self.assertIn("nur in JOSHI", messung.probe["fehler"])

    def test_a_cancelled_export_leaves_nothing_behind(self):
        import glob
        import subprocess

        async def abbrechen():
            aufgabe = asyncio.create_task(export.aus_abschnitt(
                format_="pdf", html="<p>" + "Inhalt " * 20000 + "</p>", titel="Gross"))
            await asyncio.sleep(0.8)
            aufgabe.cancel()
            try:
                await aufgabe
            except asyncio.CancelledError:
                return True
            return False

        self.assertTrue(asyncio.run(abbrechen()))
        prozesse = subprocess.run(["pgrep", "-f", "joshi-render"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(prozesse, "")
        self.assertEqual(glob.glob(os.path.join(os.environ.get("TMPDIR", "/tmp"), "joshi-*")), [])

    def test_an_old_app_with_window_print_still_gets_a_pdf(self):
        alt = KONFIGURATOR.replace(
            "document.getElementById('rechnen').onclick=rechne;",
            "document.getElementById('rechnen').onclick=rechne;"
            "document.getElementById('drucken').onclick=function(){window.print();};")
        bericht = asyncio.run(pruefer.pruefen(alt))
        self.assertTrue(bericht.ok, bericht.befunde)
        self.assertEqual([e["typ"] for e in bericht.exporte], ["pdf"])
        self.assertTrue(bericht.exporte[0]["ok"])

    def test_the_normal_product_export_still_works(self):
        produkt = {"titel": "Angebot", "verstaendnis": {}, "zustand": {}, "id": "p1"}
        version = {"nummer": 1, "html": ANGEBOT_MIT_EXPORT}
        daten = asyncio.run(export.pdf(produkt, version, {}))
        self.assertTrue(export.ist_gueltig(daten, "pdf"))
        self.assertTrue(export.ist_gueltig(export.portables_html(produkt, version, {}), "html"))


class ZaehlenderZugang(GespielterZugang):
    """Wie die echte Modellschicht: Jeder Aufruf bucht seine Tokens in den Verbrauch."""

    def __init__(self, *args: Any, tokens: int = 120, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tokens = tokens

    def _buchen(self, verbrauch: dict[str, int]) -> None:
        verbrauch["prompt_tokens"] += 200
        verbrauch["completion_tokens"] += self.tokens
        verbrauch["calls"] += 1
        # Genau wie die zentrale Modellschicht: Diese Testquelle liefert
        # Providerwerte, nicht nur eine plausible Schätzung.
        verbrauch["provider_input_usage_reported"] = True
        verbrauch["provider_output_usage_reported"] = True
        verbrauch["provider_input_usage_calls"] = verbrauch.get("provider_input_usage_calls", 0) + 1
        verbrauch["provider_output_usage_calls"] = verbrauch.get("provider_output_usage_calls", 0) + 1

    async def strukturiert(self, modell, nachrichten, schema, *, temperatur, verbrauch):
        ergebnis = await super().strukturiert(modell, nachrichten, schema,
                                              temperatur=temperatur, verbrauch=verbrauch)
        self._buchen(verbrauch)
        return ergebnis

    async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
        async for stueck in super().strom(modell, nachrichten, temperatur=temperatur, verbrauch=verbrauch):
            # Ollama liefert eval_count mit dem letzten Stück – vor dem Ende.
            if "ende" in stueck:
                self._buchen(verbrauch)
            yield stueck


class TokenzaehlerTests(SpeicherTestfall):
    """Der Zähler in der Seitenspalte zeigt auch JOSHIs eigene Erzeugung."""

    def lauf(self, zugang: GespielterZugang) -> list[dict[str, Any]]:
        _, _, ereignisse, _ = fuehre_lauf(self.user, "bauen", zugang,
                                          pipeline.Eingabe(text="BMI-Rechner bitte"), [bericht()])
        return ereignisse

    def test_a_run_reports_its_tokens_and_model_seconds(self):
        ereignisse = self.lauf(ZaehlenderZugang(["```html\n" + BMI + "\n```"]))
        staende = [e for e in ereignisse if e["type"] == "tokens"]
        self.assertTrue(staende, "Ein Lauf muss seinen Tokenstand melden")
        letzter = staende[-1]
        # Verstehen (1 Aufruf) + Bauen (1 Aufruf) à 120 Tokens.
        self.assertEqual(letzter["tokens"], 240)
        self.assertEqual(letzter["tokens_actual"], 240)
        self.assertEqual(letzter["output_tokens_actual"], 240)
        self.assertEqual(letzter["output_tokens_estimated"], 0)
        self.assertEqual(letzter["output_tokens_incomplete"], 0)
        self.assertEqual(letzter["usage_status"], "actual")
        self.assertEqual(letzter["aufrufe"], 2)
        self.assertFalse(letzter["laufend"])
        self.assertGreaterEqual(letzter["modellsekunden"], 0)
        werte = [e["tokens"] for e in staende]
        self.assertEqual(werte, sorted(werte), "Der Stand darf nie zurückspringen")

    def test_the_last_count_arrives_before_the_finish(self):
        ereignisse = self.lauf(ZaehlenderZugang(["```html\n" + BMI + "\n```"]))
        arten = [e["type"] for e in ereignisse]
        self.assertIn("fertig", arten)
        self.assertLess(max(i for i, a in enumerate(arten) if a == "tokens"), arten.index("fertig"))

    def test_only_generated_output_counts(self):
        """Prompt-Tokens gehören nicht zum Tempo, Modellzeit nicht zum Rendern."""
        auftrag = Auftrag("j", "p", self.user)
        lauf = pipeline.Lauf(auftrag, user_id=self.user, produkt={"id": "p", "titel": "T"}, art="bauen",
                             eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=GespielterZugang([]))
        lauf.verbrauch.update({"prompt_tokens": 9000, "completion_tokens": 400, "calls": 2})
        lauf.modellsekunden = 4.0
        werte = lauf.tokenwerte()
        self.assertEqual(werte["tokens"], 400)
        self.assertEqual(werte["modellsekunden"], 4.0)
        # Der laufende Strom wird geschätzt (3 Zeichen je Token) …
        laufend = lauf.tokenwerte(zeichen=300, seit=1.0, laufend=True)
        self.assertEqual(laufend["tokens"], 500)
        self.assertEqual(laufend["modellsekunden"], 5.0)
        self.assertTrue(laufend["laufend"])

    def test_the_estimate_is_dropped_once_the_model_reported_its_count(self):
        """Nach dem letzten Stück zählt nur noch die echte Zahl – nie beides."""
        quelle = (WURZEL / "app" / "joshi" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("zeichen=0 if gezaehlt else zeichen + denken", quelle)

    def test_real_generation_duration_and_count_survive_reload(self):
        class MitDauer(ZaehlenderZugang):
            def _buchen(self, verbrauch):
                super()._buchen(verbrauch)
                verbrauch["eval_duration_ns"] += 2_000_000_000
                verbrauch["timed_calls"] += 1

        auftrag, _, ereignisse, _ = fuehre_lauf(
            self.user, "bauen", MitDauer([BMI]), pipeline.Eingabe(text="BMI"), [bericht()])
        stand = speicher.job(self.user, auftrag.job_id)["verbrauch"]["tokenstand"]
        self.assertEqual(stand["tokens"], 240)
        self.assertEqual(stand["tokens_actual"], 240)
        self.assertEqual(stand["output_tokens_actual"], 240)
        self.assertEqual(stand["output_tokens_estimated"], 0)
        self.assertEqual(stand["output_tokens_incomplete"], 0)
        self.assertEqual(stand["usage_status"], "actual")
        self.assertEqual(stand["eingabetokens"], 400)
        self.assertEqual(stand["modellsekunden"], 4.0)
        self.assertFalse(stand["rate_geschaetzt"])
        self.assertFalse(stand["geschaetzt"])
        self.assertFalse(stand["laufend"])
        self.assertEqual(stand, auftrag.tokens)

    def test_cancel_preserves_partial_output_as_estimated(self):
        class Abbruch(ZaehlenderZugang):
            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                yield {"text": "x" * 300}
                raise asyncio.CancelledError()

        produkt = speicher.produkt_anlegen(self.user, "Test", "Test")
        job = speicher.job_anlegen(self.user, produkt["id"], "bauen", {}, "m")
        auftrag = Auftrag(job["id"], produkt["id"], self.user)
        lauf = pipeline.Lauf(auftrag, user_id=self.user, produkt=produkt, art="bauen",
                             eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=Abbruch([]))
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(lauf.generieren([], "Test"))
        stand = speicher.job(self.user, job["id"])["verbrauch"]["tokenstand"]
        self.assertEqual(stand["tokens"], 100)
        self.assertEqual(stand["tokens_actual"], 0)
        self.assertEqual(stand["output_tokens_estimated"], 0)
        self.assertEqual(stand["output_tokens_incomplete"], 100)
        self.assertEqual(stand["usage_status"], "incomplete")
        self.assertTrue(stand["geschaetzt"])
        self.assertFalse(stand["laufend"])

    def test_clean_stream_without_provider_output_usage_stays_an_estimate(self):
        """Ein reguläres `done` ohne eval_count ist kein echter Nullwert."""
        class OhneProviderUsage(GespielterZugang):
            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                self.anfragen.append(nachrichten)
                yield {"text": "x" * 300}
                # Die zentrale Schicht hat einen Call gesehen, aber der
                # Provider hat keine Output-Usage geliefert.
                verbrauch["calls"] += 1
                yield {"ende": "stop"}

        produkt = speicher.produkt_anlegen(self.user, "Test", "Test")
        job = speicher.job_anlegen(self.user, produkt["id"], "bauen", {}, "m")
        auftrag = Auftrag(job["id"], produkt["id"], self.user)
        lauf = pipeline.Lauf(auftrag, user_id=self.user, produkt=produkt, art="bauen",
                             eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=OhneProviderUsage([]))
        asyncio.run(lauf.generieren([], "Test"))
        stand = speicher.job(self.user, job["id"])["verbrauch"]["tokenstand"]
        self.assertEqual(stand["tokens"], 100)
        self.assertEqual(stand["tokens_actual"], 0)
        self.assertEqual(stand["output_tokens_actual"], 0)
        self.assertEqual(stand["output_tokens_estimated"], 100)
        self.assertEqual(stand["output_tokens_incomplete"], 0)
        self.assertEqual(stand["usage_status"], "estimated")
        self.assertTrue(stand["rate_geschaetzt"])

    def test_cancel_keeps_actual_and_estimated_usage_separate_everywhere(self):
        """Ein abgebrochener Auftrag darf seinen vollständigen Tokenstand nicht kürzen."""
        produkt = speicher.produkt_anlegen(self.user, "Test", "Test")
        job = speicher.job_anlegen(self.user, produkt["id"], "bauen", {}, "m")
        auftrag = Auftrag(job["id"], produkt["id"], self.user)
        verwaltung = Auftragsverwaltung()
        tokenstand = {
            "tokens": 203_000,
            "tokens_actual": 15_573,
            "output_tokens_actual": 15_573,
            "input_tokens_actual": 23_929,
            "eingabetokens": 23_929,
            "output_tokens_estimated": 188,
            "output_tokens_incomplete": 187_239,
            "laufend_geschaetzt": 188,
            "abgeschlossen_geschaetzt": 188,
            "abgebrochen_geschaetzt": 187_239,
            "usage_status": "incomplete",
            "geschaetzt": True,
            "rate_geschaetzt": True,
            "modellsekunden": 47.2,
            "aufrufe": 3,
            "laufend": True,
        }

        async def ablauf(laufender):
            await laufender.melde("tokens", **tokenstand)
            self.assertEqual(laufender.schnappschuss()["tokens"], tokenstand)
            laufender.abbruch.set()
            raise asyncio.CancelledError()

        asyncio.run(verwaltung._laufen(auftrag, ablauf))
        gespeichert = speicher.job(self.user, job["id"])
        assert gespeichert is not None
        erwartet = {**tokenstand, "laufend": False}
        self.assertEqual(gespeichert["verbrauch"]["tokenstand"], erwartet)
        self.assertEqual(auftrag.tokens, erwartet)
        letzte_tokens = next(e for e in reversed(gespeichert["ereignisse"]) if e["type"] == "tokens")
        self.assertEqual({k: letzte_tokens[k] for k in erwartet}, erwartet)
