# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Ergebnisgarantie und ehrliche Abnahme — die realen Fälle vom 06.10.2026.

Kosmos 3D Explorer: Aus „der Mond umkreist die Sonne statt die Erde, korrigiere den
kleinen Fehler“ wurde ein Vertrag, der den Fehler verlangte. Außerdem scheiterte die
Abnahme an einer festen Uhrzeit im Szenario und an fehlenden Wörtern „Datum/Uhrzeit“,
obwohl „06.10.2026 · 22:18:31“ angezeigt wurde.
"""
import asyncio
import unittest

from app.joshi import abnahme, renderer
from app.joshi.html_werk import laufzeit_dokument


class Fehlerzugang:
    """Antwortet auf die Gegenprobe wie ein Modell, das den Fehler erkennt."""

    def __init__(self, antwort):
        self.antwort = antwort
        self.fragen = 0

    async def strukturiert(self, modell, nachrichten, schema, *, temperatur, verbrauch):
        self.fragen += 1
        return self.antwort


VERDREHT = {"kriterien": [
    {"id": "mond_umkreist_sonne", "beschreibung": "In der Anwendung steht, dass der Mond die Sonne umkreist.",
     "stichworte": ["Mond", "Sonne"], "pflicht": True, "nachweis": "inhalt"},
    {"id": "ring_am_saturn", "beschreibung": "Der Ring ist am Saturn sichtbar.", "stichworte": ["Saturn", "Ring"],
     "pflicht": True, "nachweis": "inhalt"},
]}


class GegenprobeTests(unittest.TestCase):
    def test_a_bug_report_is_recognised(self):
        self.assertTrue(abnahme.ist_fehlerbericht("der Mond umkreist die Sonne statt die Erde, korrigiere den Fehler"))
        self.assertTrue(abnahme.ist_fehlerbericht("Der Saturn Ring ist fälschlich an der Sonne"))
        self.assertFalse(abnahme.ist_fehlerbericht("Füge einen Dunkelmodus hinzu"))

    def test_an_inverted_criterion_is_turned_around(self):
        zugang = Fehlerzugang({"ergebnisse": [
            {"id": "mond_umkreist_sonne", "richtung": "fehler", "beschreibung": "Der Mond umkreist die Erde.",
             "stichworte": ["Mond", "Erde"]},
            {"id": "ring_am_saturn", "richtung": "ziel"}]})
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="der Mond umkreist die Sonne statt die Erde, korrigiere den kleinen Fehler",
            vertrag=VERDREHT, verbrauch={}))
        self.assertTrue(vertrag["gegengeprueft"])
        mond, ring = vertrag["kriterien"]
        self.assertEqual(mond["beschreibung"], "Der Mond umkreist die Erde.")
        self.assertEqual(mond["stichworte"], ["Mond", "Erde"])
        self.assertIn("Sonne umkreist", mond["korrigiert_aus"])
        self.assertEqual(ring["beschreibung"], "Der Ring ist am Saturn sichtbar.")
        self.assertEqual(len(korrigiert), 1)

    def test_an_answer_as_text_is_understood(self):
        import json
        zugang = Fehlerzugang(json.dumps({"ergebnisse": [
            {"id": "mond_umkreist_sonne", "richtung": "fehler", "beschreibung": "Der Mond umkreist die Erde."}]}))
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="X statt Y, korrigiere den Fehler", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(vertrag["kriterien"][0]["beschreibung"], "Der Mond umkreist die Erde.")
        # Nackte Liste im Markdown-Zaun, mit „entfaellt“ — so antwortete glm am 06.10.2026.
        zugang = Fehlerzugang('```json\n[{"id": "mond_umkreist_sonne", "richtung": "fehler", '
                              '"beschreibung": "Der Mond umkreist die Erde."}, '
                              '{"id": "ring_am_saturn", "richtung": "entfaellt"}]\n```')
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="X statt Y, korrigiere den Fehler", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(vertrag["kriterien"][0]["beschreibung"], "Der Mond umkreist die Erde.")
        self.assertTrue(vertrag["kriterien"][1]["entfallen"])
        self.assertEqual(len(korrigiert), 2)
        zugang = Fehlerzugang("kein json")
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="X statt Y, korrigiere den Fehler", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(korrigiert, [])

    def test_an_unrelated_criterion_is_never_turned(self):
        zugang = Fehlerzugang({"ist": "Der Mond umkreist die Sonne", "soll": "Der Mond umkreist die Erde",
                               "ergebnisse": [
            {"id": "mond_umkreist_sonne", "richtung": "fehler", "beschreibung": "Der Mond umkreist die Erde."},
            {"id": "ring_am_saturn", "richtung": "fehler", "beschreibung": "Der Ring ist nirgends."}]})
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="der Mond umkreist die Sonne statt die Erde, korrigiere", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(vertrag["kriterien"][0]["beschreibung"], "Der Mond umkreist die Erde.")
        self.assertEqual(vertrag["kriterien"][1]["beschreibung"], "Der Ring ist am Saturn sichtbar.")
        self.assertEqual(len(korrigiert), 1)

    def test_no_model_call_without_a_bug_report(self):
        zugang = Fehlerzugang({"ergebnisse": []})
        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            zugang, "m", wunsch="Füge einen Dunkelmodus hinzu", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(zugang.fragen, 0)
        self.assertEqual(korrigiert, [])
        self.assertTrue(vertrag["gegengeprueft"])

    def test_a_failing_model_changes_nothing(self):
        class Kaputt:
            async def strukturiert(self, *a, **k):
                raise ValueError("kein JSON")

        vertrag, korrigiert = asyncio.run(abnahme.vertrag_gegenpruefen(
            Kaputt(), "m", wunsch="X statt Y, korrigiere", vertrag=VERDREHT, verbrauch={}))
        self.assertEqual(vertrag, VERDREHT)
        self.assertEqual(korrigiert, [])


class DatumUhrzeitTests(unittest.TestCase):
    def test_a_shown_date_and_time_count_as_keywords(self):
        fundus = abnahme._fundus({"textauszug": "Kosmos 3D Explorer 06.10.2026 · 22:18:31 Erde"})
        self.assertTrue(abnahme._treffer("Datum", fundus))
        self.assertTrue(abnahme._treffer("Uhrzeit", fundus))

    def test_no_date_no_marker(self):
        fundus = abnahme._fundus({"textauszug": "Planeten 8 Monde 146"})
        self.assertFalse(abnahme._treffer("Datum", fundus))
        self.assertFalse(abnahme._treffer("Uhrzeit", fundus))


if __name__ == "__main__":
    unittest.main()


class VollbildTests(unittest.TestCase):
    """08.10.2026, Kolibri Jump: „Spielbereich nimmt den ganzen Bildschirm ein“ war nur geschätzt."""

    def kriterium(self):
        return {"id": "vollbild", "beschreibung": "Der Spielbereich nimmt die gesamte Breite und Höhe des Bildschirms ein.",
                "stichworte": ["Spielbereich"], "nachweis": "gestaltung", "pflicht": True}

    def test_a_canvas_filling_the_screen_is_measured(self):
        urteil, beleg, _ = abnahme._gestaltung_pruefen(self.kriterium(), {"gestaltung": {
            "farben": {}, "schatten": 0, "vollbild": {"breite": 100, "hoehe": 100, "element": "canvas#spiel"}}})
        self.assertEqual(urteil, "erfuellt")
        self.assertIn("canvas#spiel", beleg)

    def test_a_small_area_is_not_full_screen(self):
        urteil, _, _ = abnahme._gestaltung_pruefen(self.kriterium(), {"gestaltung": {
            "farben": {}, "schatten": 0, "vollbild": {"breite": 100, "hoehe": 55, "element": "canvas"}}})
        self.assertEqual(urteil, "fehlt")


SPIEL = """<!DOCTYPE html><html><head><style>html,body{margin:0;height:100%}
canvas{position:fixed;inset:0;width:100%;height:100%}</style></head><body><canvas id="spiel"></canvas>
<script>
window.dispatchEvent(new ErrorEvent("error", {message: "ResizeObserver loop completed with undelivered notifications."}));
window.dispatchEvent(new ErrorEvent("error", {message: "Script error."}));
setTimeout(function(){ window.dispatchEvent(new ErrorEvent("error", {message: "echter Fehler", lineno: 7})); }, 10);
</script></body></html>"""


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class ImBrowserTests(unittest.TestCase):
    def test_hidden_start_is_not_confused_with_restart(self):
        """08.10.2026: „Start unsichtbar“ griff zum sichtbaren „Neustart“."""
        from app.joshi import pruefer
        seite = ("<html><body><button id='s' type='button'>Start</button>"
                 "<button id='n' type='button' style='display:none'>Neustart</button>"
                 "<script>document.getElementById('s').addEventListener('click', function () {"
                 "this.style.display = 'none'; document.getElementById('n').style.display = 'inline-block'; });"
                 "</script></body></html>")
        szenario = [{"id": "s1", "kriterium": "k", "schritte": [
            {"art": "klicken", "ziel": "Start"}, {"art": "warten", "ms": 100}, {"art": "unsichtbar", "ziel": "Start"},
            {"art": "sichtbar", "ziel": "Neustart"}]}]
        _, ergebnisse = asyncio.run(pruefer.szenarien_ausfuehren(seite, szenarien=szenario))
        self.assertEqual(ergebnisse[0]["ergebnis"], "bestanden", ergebnisse)

    def test_animation_frames_run_in_the_check(self):
        """08.10.2026: Im unsichtbaren Prüfbrowser lief requestAnimationFrame nie — Spiele standen still."""
        seite = "<html><body><p id='z'>0</p><script>var n=0;(function f(){n++;document.getElementById('z').textContent=n;requestAnimationFrame(f);})();</script></body></html>"
        messung = asyncio.run(renderer.rendern(laufzeit_dokument(seite, modus="pruefung"), warten=0.6,
                                               probe="return JSON.stringify({n: Number(document.getElementById('z').textContent)});"))
        self.assertGreater(messung.probe["n"], 10)

    def test_benign_messages_are_ignored_and_full_screen_is_measured(self):
        from app.joshi.renderer import INHALT_JS
        messung = asyncio.run(renderer.rendern(laufzeit_dokument(SPIEL, modus="pruefung"), probe=INHALT_JS, warten=0.5))
        fehler = [f["text"] for f in messung.probe["fehler"]]
        self.assertEqual(fehler, ["echter Fehler"])
        vollbild = messung.probe["gestaltung"]["vollbild"]
        self.assertGreaterEqual(vollbild["breite"], 95)
        self.assertGreaterEqual(vollbild["hoehe"], 95)
        self.assertEqual(vollbild["element"], "canvas#spiel")


class SymbolknopfTests(unittest.TestCase):
    def test_three_dots_button_matches_the_named_symbol(self):
        beweise = {"klicks": [{"knopf": "Menü öffnen (⋮)", "effekte": ["element_shown", "toggled"],
                               "aufklapper": True, "zurueck": True, "neueTexte": ["Start"]}]}
        kriterium = {"id": "m", "beschreibung": "Ein erneuter Klick auf das Drei-Punkte-Symbol schließt das Menü wieder.",
                     "stichworte": ["Drei-Punkte-Symbol", "Menü"], "nachweis": "bedienung", "aktion": "umschalten"}
        urteil, _, _ = abnahme._bedienung_pruefen(kriterium, beweise, abnahme._fundus(beweise))
        self.assertEqual(urteil, "erfuellt")


class VerschobenNichtVerlorenTests(unittest.TestCase):
    """08.10.2026: Knöpfe wanderten gewollt ins Drei-Punkte-Menü — kein Inhaltsverlust."""

    def test_controls_revealed_by_clicks_count(self):
        from app.joshi import pruefer
        vorher = {"textLaenge": 193, "knoepfe": ["Start", "Pause", "Weiter", "Neustart", "Ton", "Links", "Schuss",
                                                  "Rechts", "i"], "felder": [], "sichtbar": {"elemente": 34}}
        nachher = {"textLaenge": 120, "knoepfe": ["⋮", "Links", "Schuss", "Rechts"], "felder": [],
                   "sichtbar": {"elemente": 29}}
        self.assertTrue(pruefer.regressionsbefunde(vorher, nachher))          # nur beim Laden gemessen: Verlust
        interaktion = {"knoepfe": 10, "felder": 0, "klicks": [
            {"knopf": "⋮", "neueTexte": ["Start", "Pause", "Weiter", "Neustart", "Ton: an", "Anleitung"]}]}
        self.assertEqual(pruefer.regressionsbefunde(vorher, nachher, interaktion=interaktion), [])
