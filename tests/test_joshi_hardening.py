# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""JOSHI-Hardening: Änderungslinie, Abschneiden, Teil-Patches, Wächter, Stufen, Beweise.

Grundlage ist der Tabellenkalkulations-Stresstest vom 21.09.2026: Nach einem
gescheiterten Versuch schrieb der Nutzer „versuch es erneut“. Die Antwort
endete mit `length` nach 217.048 Zeichen, 4 von 112 Blöcken passten nicht, ein
kleiner Nachtrag wurde auf das Original angewendet (108 Änderungen gingen
verloren), der Vertrag schrumpfte auf „Anwendung öffnet sich“ und „Knöpfe
anklickbar“, und „Speichern“ galt als nicht umgesetzt, weil kein neues DOM
erschien.

Die Modellantworten sind hier gespielt; die Beweis-Tests am Ende laufen im
echten WebKit-Renderer.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

try:
    from test_joshi import BMI, FakeRequest, GespielterZugang, SpeicherTestfall
except ImportError:  # als Paket gestartet
    from tests.test_joshi import BMI, FakeRequest, GespielterZugang, SpeicherTestfall

from app import database  # noqa: E402
from app.joshi import abnahme, aenderung, grenzen, pipeline, projektdateien, pruefer, renderer, speicher  # noqa: E402
from app.joshi.html_werk import Befund, bloecke_anwenden  # noqa: E402
from app.joshi.jobs import Auftrag, Auftragsverwaltung  # noqa: E402

GROSS = BMI.replace('<p id="ergebnis"></p>', '<p id="ergebnis"></p>' + "<!-- Füllung -->\n" * 600)
TABELLE_WUNSCH = (
    "Erweitere die Tabelle um einen Abhängigkeitsgraphen mit inkrementeller Neuberechnung, "
    "Zykluserkennung mit Fehlermeldung, Fehlerwerte, Excel-artige Rundung, Undo und Redo, "
    "#REF!-Semantik beim Löschen und eine Leistungsanzeige. " + "Details: " + "x " * 700
)


def vertrag(anzahl: int, praefix: str = "k") -> dict[str, Any]:
    worte = ["Diagramm", "Verlauf", "Zyklus", "Rundung", "Fehlerwert", "Leistung", "Protokoll", "Export",
             "Archiv", "Legende"]
    return {"zusammenfassung": f"{anzahl} Anforderungen", "kriterien": [
        {"id": f"{praefix}{n}", "beschreibung": f"Die Anwendung zeigt {worte[n % len(worte)]} {praefix}{n}",
         "stichworte": [worte[n % len(worte)]], "pflicht": True, "nachweis": "inhalt"}
        for n in range(anzahl)]}


def einfache_ui_kriterien(anzahl: int) -> dict[str, Any]:
    """Absichtlich einfache Bedienwünsche, keine versteckten Engine-Schlüsselwörter."""
    return {"zusammenfassung": "kleine Oberflächenwünsche", "kriterien": [
        {"id": f"ui{n}", "beschreibung": f"Die Oberfläche hat einen klaren Schalter {n}",
         "stichworte": [f"Schalter {n}"], "pflicht": True, "nachweis": "bedienung"}
        for n in range(anzahl)]}


class Skriptzugang(GespielterZugang):
    """Gespielte Modellschicht mit frei wählbarem Ende je Antwort und Buchführung."""

    def __init__(self, antworten: list[Any], **kwargs: Any) -> None:
        super().__init__([], **kwargs)
        self.skript = list(antworten)
        self.vertragsfragen = 0
        self.geschlossen = 0

    async def strukturiert(self, modell, nachrichten, schema, *, temperatur, verbrauch):
        if "kriterien" in (schema or {}).get("properties", {}):
            self.vertragsfragen += 1
        return await super().strukturiert(modell, nachrichten, schema, temperatur=temperatur, verbrauch=verbrauch)

    async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
        self.anfragen.append(nachrichten)
        eintrag = self.skript.pop(0)
        text, ende = eintrag if isinstance(eintrag, tuple) else (eintrag, "stop")
        try:
            for stelle in range(0, len(text), 400):
                yield {"text": text[stelle:stelle + 400]}
            yield {"ende": ende}
        finally:
            self.geschlossen += 1


def block(alt: str, neu: str) -> str:
    return f"<<<<<<< SUCHEN\n{alt}\n=======\n{neu}\n>>>>>>> ERSETZEN"


def html_pruefung(protokoll: list[dict[str, Any]] | None = None, user: str = "", produkt_id: str = ""):
    """Gespielter Prüfer, der die Gliederung ehrlich aus dem Kandidaten liest."""
    async def pruefen(html, **_):
        text = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        if protokoll is not None:
            protokoll.append({"version": speicher.produkt(user, produkt_id)["version"] if user else 0,
                              "zeichen": len(html)})
        gliederung = {"ueberschriften": re.findall(r"<h1>(.*?)</h1>", html), "knoepfe": ["Berechnen"],
                      "felder": [{"label": "Gewicht (kg)", "typ": "number"}], "markdown": " ".join(text.split()),
                      "textLaenge": len(text), "anzahl": {}, "sichtbar": {"elemente": 10, "interaktiv": 2,
                                                                          "flaecheProzent": 40}}
        return pruefer.Pruefbericht([], browser=True, gliederung=gliederung,
                                    interaktion={"gefuellt": 1, "geklickt": 1, "klicks": []})
    return pruefen


def lauf(user: str, produkt: dict[str, Any], art: str, zugang: GespielterZugang, text: str,
         pruefung: Any = None, fehler: str = "") -> tuple[Auftrag, dict[str, Any], list[dict[str, Any]]]:
    job = speicher.job_anlegen(user, produkt["id"], art, {"text": text}, "testmodell")
    aktuell = speicher.produkt(user, produkt["id"])

    async def ausfuehren():
        auftrag = Auftrag(job["id"], produkt["id"], user)
        with patch.object(pipeline.pruefer, "pruefen", pruefung or html_pruefung()):
            await pipeline.Lauf(auftrag, user_id=user, produkt=aktuell, art=art,
                                eingabe=pipeline.Eingabe(text=text, fehler=fehler), modell="m",
                                zugang=zugang).ausfuehren()
        return auftrag

    auftrag = asyncio.run(ausfuehren())
    return auftrag, speicher.produkt(user, produkt["id"]), [json.loads(z) for z in auftrag.ereignisse]


class HardeningTestfall(SpeicherTestfall):
    def setUp(self):
        super().setUp()
        speicher.tabellen_anlegen()

    def produkt(self, html: str = GROSS) -> dict[str, Any]:
        produkt = speicher.produkt_anlegen(self.user, "Tabelle", "Tabellenkalkulation", {})
        speicher.version_festschreiben(produkt["id"], html, "Erstfassung", pruefung={
            "ok": True, "browser": True, "gliederung": {"knoepfe": ["Berechnen"], "textLaenge": 400}},
            aktivieren=True, status="ready")
        return speicher.produkt(self.user, produkt["id"])


# ------------------------------------------------------------------ A, B
class AenderungslinieTests(HardeningTestfall):
    """A retry never loses the original change intent."""

    def test_retry_phrases_are_recognised(self):
        for satz in ("versuch es erneut es umzusetzten", "nochmal", "Nochmal versuchen bitte",
                     "erneut umsetzen", "probier es nochmal", "try again"):
            self.assertEqual(aenderung.absicht_erkennen(satz, offen=True).art, "wiederholen", satz)
            self.assertEqual(aenderung.absicht_erkennen(satz, offen=True).rest, "", satz)
        mit_zusatz = aenderung.absicht_erkennen("Versuch es nochmal, aber mit einem CSV-Export", offen=True)
        self.assertEqual((mit_zusatz.art, bool(mit_zusatz.rest)), ("wiederholen", True))
        self.assertEqual(aenderung.absicht_erkennen("Mach den Hintergrund blau", offen=True).art, "ergaenzen")
        self.assertEqual(aenderung.absicht_erkennen("Mach den Hintergrund blau", offen=False).art, "neu")
        verworfen = aenderung.absicht_erkennen("Vergiss das, mach stattdessen den Hintergrund blau", offen=True)
        self.assertEqual(verworfen.art, "verwerfen")
        self.assertIn("Hintergrund blau", verworfen.rest)

    def test_deferred_requirements_leave_the_active_contract_and_can_be_restored(self):
        vertrag_ = aenderung.vertrag_einfrieren({"zusammenfassung": "Info und Startfähigkeit", "kriterien": [
            {"id": "info", "beschreibung": "Die Anwendung zeigt Info-Beschreibungen zu jeder Übung",
             "stichworte": ["Info", "Beschreibung"], "pflicht": True},
            {"id": "start", "beschreibung": "Die Anwendung ist lauffähig und startet ohne Fehler",
             "stichworte": ["startet", "Fehler"], "pflicht": True},
        ]})
        plan = {"stufen": [{"titel": "Info-Beschreibungen", "kriterien": ["info"]}]}
        satz = "ok dann mach es lauffähig erstmal ohne info buttons wir prüfen später"

        absicht = aenderung.absicht_erkennen(satz, offen=True, vertrag=vertrag_, plan=plan)
        self.assertEqual((absicht.art, absicht.rest), ("zurueckstellen", ""))
        self.assertEqual(absicht.ziele, ["info"])
        geparkt = aenderung.zurueckstellen(vertrag_, absicht.ziele, satz)
        self.assertEqual([k["id"] for k in aenderung.aktiver_vertrag(geparkt)["kriterien"]], ["start"])
        wieder = aenderung.absicht_erkennen("nimm die Info-Buttons wieder auf", True, geparkt, plan)
        self.assertEqual((wieder.art, wieder.ziele), ("wiederaufnehmen", ["info"]))
        self.assertEqual([k["id"] for k in aenderung.aktiver_vertrag(
            aenderung.wiederaufnehmen(geparkt, wieder.ziele))["kriterien"]], ["info", "start"])

    def test_legacy_defer_addition_is_healed_without_losing_the_root_criterion(self):
        root = {"zusammenfassung": "Info und Startfähigkeit", "kriterien": [
            {"id": "info", "beschreibung": "Die Anwendung zeigt Info-Beschreibungen zu jeder Übung",
             "stichworte": ["Info", "Beschreibung"], "pflicht": True, "herkunft": "root"},
            {"id": "start", "beschreibung": "Die Anwendung ist lauffähig und startet ohne Fehler",
             "stichworte": ["startet", "Fehler"], "pflicht": True, "herkunft": "root"},
            {"id": "keine_info", "beschreibung": "Es gibt keine Info-Buttons", "pflicht": True,
             "herkunft": "ergaenzung_1"},
            {"id": "app_laeuft", "beschreibung": "Die App läuft", "pflicht": True,
             "herkunft": "ergaenzung_1"},
        ]}
        linie = {"vertrag": root, "ergaenzungen": [
            {"text": "ok dann mach es lauffähig erstmal ohne info buttons wir prüfen später"}],
            "plan": {"stufen": [{"titel": "Info-Beschreibungen", "kriterien": ["info"]}]}}
        bereinigt, korrekturen = aenderung.vertrag_bereinigen(linie)
        self.assertEqual(len(korrekturen), 1)
        self.assertEqual([k["id"] for k in aenderung.aktiver_vertrag(bereinigt)["kriterien"]], ["start"])
        self.assertEqual([k["id"] for k in aenderung.zurueckgestellt(bereinigt)], ["info"])
        self.assertTrue(all(k.get("entfallen") for k in bereinigt["kriterien"] if k["id"] in {"keine_info", "app_laeuft"}))
        self.assertEqual(linie["ergaenzungen"][0]["art"], "zurueckstellen")

    def test_a_retry_keeps_all_seven_root_criteria(self):
        produkt = self.produkt()
        erster = Skriptzugang([block("<h1>BMI-Rechner</h1>", "<h1>BMI-Rechner</h1><p>halb</p>")] * 3,
                              vertrag=vertrag(7))
        _, nachher, _ = lauf(self.user, produkt, "aendern", erster, "Baue sieben Dinge ein",
                             pruefung=html_pruefung())
        self.assertEqual(nachher["version"], 1)                    # gescheitert, v1 bleibt
        linie = speicher.offene_aenderung(produkt["id"])
        self.assertEqual(len(linie["vertrag"]["kriterien"]), 7)
        ids = [k["id"] for k in linie["vertrag"]["kriterien"]]

        # Der zweite Versuch: Das Modell würde jetzt einen Mini-Vertrag liefern —
        # darf aber gar nicht erst gefragt werden.
        zweiter = Skriptzugang([block("<h1>BMI-Rechner</h1>", "<h1>BMI-Rechner</h1><p>wieder</p>")] * 3,
                               vertrag=vertrag(2, "mini"))
        _, nachher, ereignisse = lauf(self.user, produkt, "aendern", zweiter, "versuch es erneut es umzusetzten")
        self.assertEqual(zweiter.vertragsfragen, 0)
        vertraege = [e for e in ereignisse if e["type"] == "abnahmevertrag"]
        self.assertEqual([k["id"] for k in vertraege[-1]["vertrag"]["kriterien"]], ids)
        self.assertEqual(vertraege[-1]["versuch"], 2)
        # Das Modell bekam den ursprünglichen Auftrag, nicht „versuch es erneut“.
        auftrag = zweiter.anfragen[0][-1]["content"]
        self.assertIn("Baue sieben Dinge ein", auftrag)
        self.assertIn("Versuch 2", auftrag)
        linie = speicher.offene_aenderung(produkt["id"])
        self.assertEqual(len(linie["versuche"]), 2)
        self.assertEqual(linie["versuche"][1]["text"], "versuch es erneut es umzusetzten")
        self.assertTrue(any("ursprünglichen Auftrag erneut" in e.get("text", "") for e in ereignisse
                            if e["type"] == "hinweis"))

    def test_b_an_added_requirement_extends_the_contract(self):
        produkt = self.produkt()
        lauf(self.user, produkt, "aendern", Skriptzugang(["kaputt"] * 4, vertrag=vertrag(7)), "Baue sieben Dinge ein")
        alt = [k["id"] for k in speicher.offene_aenderung(produkt["id"])["vertrag"]["kriterien"]]
        zweiter = Skriptzugang(["kaputt"] * 4, vertrag={"zusammenfassung": "CSV", "kriterien": [
            {"id": "k0", "beschreibung": "Ein CSV-Export ist möglich", "stichworte": ["CSV"], "pflicht": True}]})
        lauf(self.user, produkt, "aendern", zweiter, "Versuch es nochmal und ergänze zusätzlich einen CSV-Export")
        linie = speicher.offene_aenderung(produkt["id"])
        kriterien = linie["vertrag"]["kriterien"]
        self.assertEqual(len(kriterien), 8)
        self.assertEqual([k["id"] for k in kriterien[:7]], alt)              # alte bleiben unverändert
        self.assertNotEqual(kriterien[7]["id"], "k0")                         # neue ID kollidiert nicht
        self.assertEqual(kriterien[7]["herkunft"], "ergaenzung_1")
        self.assertTrue(all(k["pflicht"] for k in kriterien))
        self.assertEqual(len(linie["ergaenzungen"]), 1)

    def test_an_identical_root_request_is_a_retry_not_a_duplicate_addition(self):
        """Der echte Killer-Retry war der komplette Originalprompt, ohne Retry-Wort."""
        produkt = self.produkt()
        root = "Füge eine Kartenansicht mit drei klaren Filtern hinzu."
        lauf(self.user, produkt, "aendern", Skriptzugang(["kaputt"] * 4, vertrag=vertrag(3, "root")), root)
        vorher = speicher.offene_aenderung(produkt["id"])
        assert vorher is not None
        ids = [k["id"] for k in vorher["vertrag"]["kriterien"]]

        erneut = Skriptzugang(["kaputt"] * 4, vertrag=vertrag(1, "mini"))
        _, _, ereignisse = lauf(self.user, produkt, "aendern", erneut, "  Füge eine Kartenansicht, mit drei klaren Filtern hinzu! ")
        nachher = speicher.offene_aenderung(produkt["id"])
        assert nachher is not None
        self.assertEqual(erneut.vertragsfragen, 0)
        self.assertEqual([k["id"] for k in nachher["vertrag"]["kriterien"]], ids)
        self.assertEqual(len(nachher["versuche"]), 2)
        self.assertTrue(any(e["type"] == "abnahmevertrag" and e["versuch"] == 2 for e in ereignisse))

    def test_discarding_ends_the_open_change(self):
        produkt = self.produkt()
        lauf(self.user, produkt, "aendern", Skriptzugang(["kaputt"] * 4, vertrag=vertrag(3)), "Drei Dinge")
        auftrag, nachher, ereignisse = lauf(self.user, produkt, "aendern", Skriptzugang([]), "verwirf die Änderung")
        self.assertIsNone(speicher.offene_aenderung(produkt["id"]))
        self.assertEqual(nachher["version"], 1)
        self.assertEqual(speicher.job(self.user, auftrag.job_id)["status"], "cancelled")

    def test_a_legacy_failed_change_is_reconstructed_for_a_retry(self):
        """Aufträge von vor der Änderungslinie: Der Wunsch des gescheiterten Auftrags zählt."""
        produkt = self.produkt()
        alt = speicher.job_anlegen(self.user, produkt["id"], "aendern", {"text": TABELLE_WUNSCH[:300]}, "m")
        speicher.job_aendern(alt["id"], status="failed", fehler="abgelehnt",
                             ereignisse=[{"type": "technik", "text": "Modellantwort: 217.048 Zeichen in 587 s (Ende: length)."}])
        wieder = speicher.job_anlegen(self.user, produkt["id"], "aendern", {"text": "versuch es erneut"}, "m")
        speicher.job_aendern(wieder["id"], status="failed", fehler="abgelehnt")
        zugang = Skriptzugang(["kaputt"] * 12, vertrag=vertrag(3))
        _, _, ereignisse = lauf(self.user, produkt, "aendern", zugang, "versuch es erneut es umzusetzten")
        linie = speicher.aenderungen(produkt["id"])[0]
        self.assertTrue(linie["wunsch"].startswith("Erweitere die Tabelle"))
        self.assertEqual(len(linie["versuche"]), 3)
        # Der frühere Versuch war abgeschnitten — also geht es gleich in Schritten weiter.
        self.assertTrue(any(e["type"] == "stufen" for e in ereignisse))


class KomplexitaetsRouterTests(unittest.TestCase):
    """Der Router beurteilt den Vertrag, nicht die Zeichenzahl des Prompts."""

    def test_small_refine_and_many_simple_ui_wishes_stay_fast(self):
        self.assertFalse(aenderung.komplexitaet(einfache_ui_kriterien(1)).gestuft)
        schnell = aenderung.komplexitaet(einfache_ui_kriterien(8))
        self.assertFalse(schnell.gestuft, schnell.als_dict())

    def test_heavy_system_contract_routes_directly_to_stages(self):
        schwer = {"kriterien": [
            {"id": "graph", "beschreibung": "Ein Abhängigkeitsgraph erkennt Zyklen", "pflicht": True,
             "nachweis": "ablauf"},
            {"id": "leistung", "beschreibung": "50.000 Zellen bleiben performant", "pflicht": True,
             "nachweis": "ablauf"},
            {"id": "sichtbar", "beschreibung": "Virtualisierung lädt nur sichtbare Zeilen", "pflicht": True,
             "nachweis": "ablauf"},
            {"id": "sync", "beschreibung": "Mehrbenutzer synchronisieren Konflikte", "pflicht": True,
             "nachweis": "nicht_pruefbar"},
            *einfache_ui_kriterien(2)["kriterien"],
        ]}
        entscheidung = aenderung.komplexitaet(schwer)
        self.assertTrue(entscheidung.gestuft, entscheidung.als_dict())
        self.assertGreaterEqual(entscheidung.schwer, 2)


class ProjektdateienPipelineTests(HardeningTestfall):
    def grosse_anwendung(self) -> str:
        funktionen = "\n".join(f"function berechnen{n}() {{ return {n}; }}" for n in range(1500))
        return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body><main>Werkzeug</main>" \
            "<script>\n" + funktionen + "\n</script></body></html>"

    def lauf_fuer(self, html: str, zugang: GespielterZugang):
        produkt = self.produkt(html)
        job = speicher.job_anlegen(self.user, produkt["id"], "aendern", {"text": "Berechnungen ändern"}, "m")
        auftrag = Auftrag(job["id"], produkt["id"], self.user)
        lauf_ = pipeline.Lauf(auftrag, user_id=self.user, produkt=produkt, art="aendern",
                              eingabe=pipeline.Eingabe(text="Berechnungen ändern"), modell="m", zugang=zugang)
        return produkt, job, auftrag, lauf_

    def test_large_app_changes_through_central_stream_and_persists_per_job(self):
        html = self.grosse_anwendung()
        projekt = projektdateien.zerlegen(html)
        fenster = 16_384
        budget = max(0, int((fenster * pipeline.ZEICHEN_JE_TOKEN - 9_000) / 2))
        gesehen = projektdateien.auswahl_begrenzen(
            projekt, projektdateien.rangfolge(projekt, "Berechnungen ändern"), budget)
        self.assertTrue(gesehen)
        name = next(n for n in gesehen if "function berechnen" in projekt.alle()[n])
        alt = next(line for line in projekt.alle()[name].splitlines() if "function berechnen" in line)
        neuzeile = alt.replace("return 0;", "return 1000;")
        antwort = f"=== ÄNDERN: {name} ===\n{block(alt, neuzeile)}\n=== ENDE ==="
        zugang = Skriptzugang([antwort], fenster=fenster)

        with tempfile.TemporaryDirectory() as temp_dir:
            produkt, job, _, lauf_ = self.lauf_fuer(html, zugang)
            with patch.object(database, "DATA_DIR", Path(temp_dir)):
                kandidat, vollstaendig, beschreibung = asyncio.run(lauf_.umsetzen(
                    html, lauf_._nachrichten_fuer(html, "Berechnungen ändern"), "Änderung", wunsch="Berechnungen ändern"))

            self.assertTrue(vollstaendig)
            self.assertIn("return 1000;", kandidat)
            self.assertEqual(len(zugang.anfragen), 1)
            prompt = zugang.anfragen[0][-1]["content"]
            self.assertIn("Projektübersicht", prompt)
            self.assertIn(f"Datei {name}:", prompt)
            self.assertNotIn("function berechnen1499", prompt)
            ziel = projektdateien.auftrag_ordner(Path(temp_dir), produkt, job["id"])
            self.assertTrue((ziel / "manifest.json").exists())
            self.assertTrue((ziel / "PROJEKT.md").exists())
            gespeichert = projektdateien.laden(ziel, kandidat)
            self.assertIsNotNone(gespeichert)
            self.assertEqual(gespeichert.zusammensetzen(), kandidat)
            self.assertIn("Projektdatei", beschreibung)

    def test_truncated_project_file_answer_never_becomes_a_candidate(self):
        html = self.grosse_anwendung()
        projekt = projektdateien.zerlegen(html)
        name = next(n for n in projektdateien.rangfolge(projekt, "Berechnungen ändern")
                    if "function berechnen" in projekt.alle()[n])
        alt = next(line for line in projekt.alle()[name].splitlines() if "function berechnen" in line)
        antwort = f"=== ÄNDERN: {name} ===\n{block(alt, alt.replace('return 0;', 'return 99;'))}\n=== ENDE ==="
        with tempfile.TemporaryDirectory() as temp_dir:
            produkt, _, _, lauf_ = self.lauf_fuer(html, Skriptzugang([(antwort, "length")], fenster=16_384))
            with patch.object(database, "DATA_DIR", Path(temp_dir)):
                with self.assertRaises(pipeline.Grenzfall) as fall:
                    asyncio.run(lauf_.umsetzen(html, lauf_._nachrichten_fuer(html, "x"), "Änderung", wunsch="x",
                                               gestuft=True))
            self.assertEqual(fall.exception.art, "abgeschnitten")
            self.assertEqual(produkt["version"], 1)
            self.assertEqual(lauf_.patch.status, "abgeschnitten")

    def test_unresolved_project_patch_conflict_never_falls_back_to_a_whole_app_rewrite(self):
        html = self.grosse_anwendung()
        projekt = projektdateien.zerlegen(html)
        name = next(n for n in projektdateien.rangfolge(projekt, "Berechnungen ändern")
                    if "function berechnen" in projekt.alle()[n])
        falsch = block("function berechnen_existiert_nicht() { return 0; }",
                       "function berechnen_existiert_nicht() { return 99; }")
        antwort = f"=== ÄNDERN: {name} ===\n{falsch}\n=== ENDE ==="
        zugang = Skriptzugang([antwort, antwort], fenster=16_384)
        with tempfile.TemporaryDirectory() as temp_dir:
            produkt, _, _, lauf_ = self.lauf_fuer(html, zugang)
            with patch.object(database, "DATA_DIR", Path(temp_dir)):
                with self.assertRaises(pipeline.Grenzfall) as fall:
                    asyncio.run(lauf_.umsetzen(html, lauf_._nachrichten_fuer(html, "x"), "Änderung", wunsch="x",
                                               gestuft=True))
            self.assertEqual(fall.exception.art, "konflikt")
            self.assertEqual(len(zugang.anfragen), 2)  # ein gezielter Nachtrag, keine gesamte HTML-Neufassung
            self.assertEqual(lauf_.patch.status, "konflikt")
            self.assertEqual(produkt["version"], 1)


# ------------------------------------------------------------------ C, D
class AbschneidenUndPatchTests(HardeningTestfall):
    """A truncated response is never a candidate; a partial patch is never a silent success."""

    def test_c_a_truncated_patch_is_never_applied_or_promoted(self):
        produkt = self.produkt()
        abgeschnitten = "\n".join(block("<h1>BMI-Rechner</h1>", "<h1>ABGESCHNITTEN</h1>") for _ in range(1)) \
            + "\n<<<<<<< SUCHEN\n<label"
        zugang = Skriptzugang([(abgeschnitten, "length")] * 8, vertrag=vertrag(2))
        auftrag, nachher, ereignisse = lauf(self.user, produkt, "aendern", zugang, "Zwei Dinge")
        self.assertEqual(nachher["version"], 1)
        for version in speicher.versionen(produkt["id"]):
            self.assertNotIn("ABGESCHNITTEN", speicher.version(produkt["id"], version["nummer"])["html"])
        job = speicher.job(self.user, auftrag.job_id)
        self.assertEqual(job["status"], "failed")
        diagnose = job["ergebnis"]["diagnose"]
        self.assertEqual(diagnose["grund"], "length")
        self.assertEqual(diagnose["patch"]["status"], "abgeschnitten")
        self.assertFalse(diagnose["befoerdert"])
        self.assertTrue(any(s["art"] == "abgeschnitten" for s in diagnose["signale"]))

    def test_c_a_truncated_full_file_is_not_a_candidate(self):
        produkt = self.produkt(BMI)                               # klein: ganze Datei
        halb = BMI[: len(BMI) // 2]
        zugang = Skriptzugang([(halb, "length")] * 12, vertrag=vertrag(1))
        _, nachher, _ = lauf(self.user, produkt, "reparieren", zugang, "", fehler="x ist undefiniert")
        self.assertEqual(nachher["version"], 1)
        self.assertEqual(len(speicher.versionen(produkt["id"])), 1)

    def test_c_a_truncated_stage_continuation_is_never_a_candidate(self):
        """Auch ein zufällig geschlossenes HTML nach `length` bleibt verworfen."""
        teil = BMI.rsplit("</body>", 1)[0]
        zugang = Skriptzugang([(teil, "stop"), ("</body></html>", "length")])
        lauf_ = pipeline.Lauf(Auftrag("j", "p", self.user), user_id=self.user,
                              produkt={"id": "p", "titel": "T"}, art="aendern",
                              eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=zugang)
        with self.assertRaises(pipeline.Grenzfall) as fall:
            asyncio.run(lauf_.umsetzen(BMI, lauf_._nachrichten_fuer(BMI, "x"), "t", wunsch="x", gestuft=True))
        self.assertEqual(fall.exception.art, "abgeschnitten")
        self.assertEqual(lauf_.patch.status, "abgeschnitten")
        self.assertIn("TRUNCATED_STAGE", fall.exception.technik)
        self.assertEqual(zugang.geschlossen, 2)

    def test_c_a_truncated_stage_repair_is_never_a_candidate(self):
        """Die Reparatur einer abgeschnittenen Stufe darf `length` nicht verschlucken."""
        produkt = self.produkt(BMI)
        zugang = Skriptzugang([(BMI, "length")])
        lauf_ = pipeline.Lauf(Auftrag("j", produkt["id"], self.user), user_id=self.user,
                              produkt=produkt, art="aendern", eingabe=pipeline.Eingabe(text="x"),
                              modell="m", zugang=zugang)
        bericht = pruefer.Pruefbericht([Befund("fehler", "Die erste Fassung ist fehlerhaft")], browser=True,
                                       gliederung={"textLaenge": 100, "sichtbar": {"elemente": 3}})

        async def pruefen(*_args, **_kwargs):
            return bericht

        with patch.object(pipeline.pruefer, "pruefen", pruefen):
            _, bester = asyncio.run(lauf_.pruefen_und_reparieren(
                BMI, False, [], stufe="Schritt 1", max_reparaturen=1))
        self.assertFalse(bester.ok)
        self.assertEqual(lauf_.patch.status, "abgeschnitten")
        self.assertEqual(zugang.geschlossen, 1)

    def test_d_the_rebase_keeps_every_block_that_already_fit(self):
        """Der reale Fehler: Der Nachtrag wurde aufs Original angewendet."""
        html = GROSS
        passend = [block(f"<!-- Füllung -->\n<!-- Füllung -->\n", f"<!-- Füllung -->\n<p>ok {n}</p>\n")
                   for n in range(6)]
        # Die ersten sechs Blöcke passen (jeder ersetzt das nächste Füllungs-Paar),
        # zwei nicht.
        falsch = [block("<h2>gibt es nicht</h2>", "<h2>Neu A</h2>"), block("<h3>auch nicht</h3>", "<h3>Neu B</h3>")]
        antwort = "\n".join([*passend, *falsch])
        nachtrag = "\n".join([block('<p id="ergebnis"></p>', '<p id="ergebnis"></p><h2>Neu A</h2>'),
                              block("<h1>BMI-Rechner</h1>", "<h1>BMI-Rechner</h1><h3>Neu B</h3>")])
        zugang = Skriptzugang([antwort, nachtrag])
        lauf_ = pipeline.Lauf(Auftrag("j", "p", self.user), user_id=self.user, produkt={"id": "p", "titel": "T"},
                              art="aendern", eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=zugang)
        neu, vollstaendig, _ = asyncio.run(lauf_.umsetzen(html, lauf_._nachrichten_fuer(html, "x"), "t", wunsch="x"))
        self.assertTrue(vollstaendig)
        for n in range(6):
            self.assertIn(f"<p>ok {n}</p>", neu)                  # nichts ging verloren
        self.assertIn("<h2>Neu A</h2>", neu)
        self.assertIn("<h3>Neu B</h3>", neu)
        self.assertEqual(lauf_.patch.status, "komplett")
        self.assertTrue(lauf_.patch.nachtrag)
        # Der Nachtrag sah den teilweise geänderten Stand, nicht das Original.
        self.assertIn("<p>ok 0</p>", zugang.anfragen[1][-1]["content"])

    def test_d_blocks_that_stay_missing_are_a_conflict_not_a_success(self):
        passend = [block("<!-- Füllung -->\n<!-- Füllung -->\n", f"<!-- Füllung -->\n<p>ok {n}</p>\n")
                   for n in range(7)]
        falsch = [block("<h2>gibt es nicht</h2>", "<h2>X</h2>"), block("<h3>auch nicht</h3>", "<h3>Y</h3>"),
                  block("<h4>nie</h4>", "<h4>Z</h4>")]
        zugang = Skriptzugang(["\n".join([*passend, *falsch]), block("<h5>falsch</h5>", "<h5>Q</h5>")])
        lauf_ = pipeline.Lauf(Auftrag("j", "p", self.user), user_id=self.user, produkt={"id": "p", "titel": "T"},
                              art="aendern", eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=zugang)
        with self.assertRaises(pipeline.Grenzfall) as fall:
            asyncio.run(lauf_.umsetzen(GROSS, lauf_._nachrichten_fuer(GROSS, "x"), "t", wunsch="x", gestuft=True))
        self.assertEqual(fall.exception.art, "konflikt")
        self.assertEqual(lauf_.patch.status, "konflikt")
        self.assertEqual((lauf_.patch.bloecke, lauf_.patch.angewendet, len(lauf_.patch.konflikte)), (10, 7, 3))
        self.assertIn("PATCH_CONFLICT", fall.exception.technik)

    def test_a_small_conflict_may_still_be_rewritten_whole(self):
        """Der bewährte Rückweg bleibt: Bei einer normalen Änderung darf die ganze Datei neu kommen."""
        produkt = self.produkt()
        falsch = block("<h2>gibt es nicht</h2>", "<h2>x</h2>")
        voll = GROSS.replace("Berechnen</button>", "Jetzt berechnen</button>")
        zugang = Skriptzugang([falsch, falsch, voll], vertrag={"zusammenfassung": "x", "kriterien": [
            {"id": "knopf", "beschreibung": "Der Knopf heißt Jetzt berechnen", "stichworte": ["Jetzt berechnen"],
             "pflicht": True, "nachweis": "inhalt"}]})
        _, nachher, _ = lauf(self.user, produkt, "aendern", zugang, "Knopf umbenennen")
        self.assertEqual(nachher["version"], 2)
        self.assertIn("Jetzt berechnen", speicher.version(produkt["id"], 2)["html"])


# ------------------------------------------------------------------ K, L, M
class GestufterModusTests(HardeningTestfall):
    """Intermediate stages never replace the active product; only full root acceptance promotes."""

    def stufen_antworten(self, worte: list[str]) -> list[str]:
        return [block("<h1>BMI-Rechner</h1>", f"<h1>BMI-Rechner</h1><p>{wort}</p>") for wort in worte]

    def test_deferred_stage_is_reported_and_not_sent_to_the_model(self):
        produkt = self.produkt()
        vertrag_ = aenderung.vertrag_einfrieren({"kriterien": [
            {"id": "info", "beschreibung": "Info-Beschreibungen zu Übungen", "stichworte": ["Info"],
             "pflicht": True},
            {"id": "start", "beschreibung": "Die Anwendung startet fehlerfrei", "stichworte": ["startet"],
             "pflicht": True},
        ]})
        vertrag_ = aenderung.zurueckstellen(vertrag_, ["info"], "Erstmal ohne Info")
        plan = {"quelle": "test", "stufen": [
            {"titel": "Info-Beschreibungen", "auftrag": "Info erklären", "kriterien": ["info"]},
            {"titel": "Startfähigkeit", "auftrag": "Startfehler beheben", "kriterien": ["start"]},
        ]}
        linie = speicher.aenderung_anlegen(self.user, produkt["id"], "Root-Auftrag", vertrag_, basis=1)
        linie = speicher.aenderung_aendern(linie["id"], plan=plan)
        job = speicher.job_anlegen(self.user, produkt["id"], "aendern", {"text": "versuch es erneut"}, "m")
        auftrag = Auftrag(job["id"], produkt["id"], self.user)
        lauf_ = pipeline.Lauf(auftrag, user_id=self.user, produkt=produkt, art="aendern",
                              eingabe=pipeline.Eingabe(text="versuch es erneut"), modell="m",
                              zugang=Skriptzugang([]))
        lauf_.linie = linie
        lauf_.vertrag_gesamt = vertrag_
        lauf_.vertrag = aenderung.aktiver_vertrag(vertrag_)
        lauf_.wunsch = "Root-Auftrag"
        calls: list[str] = []

        async def fake_umsetzen(html: str, _nachrichten, _fortschritt: str, *, wunsch: str = "", gestuft=False):
            calls.append(wunsch)
            return html + "<!-- start repaired -->", True, "Teständerung"

        async def fake_pruefen(html: str, *_args, **_kwargs):
            return html, pruefer.Pruefbericht([], browser=True, gliederung={"textLaenge": 100})

        lauf_.umsetzen = fake_umsetzen
        lauf_.pruefen_und_reparieren = fake_pruefen
        result, vollstaendig = asyncio.run(lauf_.aendern_gestuft(speicher.version(produkt["id"], 1)["html"]))

        self.assertTrue(vollstaendig)
        self.assertIn("<!-- start repaired -->", result)
        self.assertEqual(len(calls), 1)
        self.assertIn("SCHRITT 2 VON 2", calls[0])
        stufenmeldung = next(e for e in auftrag.gespeicherte_ereignisse() if e["type"] == "stufen")
        self.assertEqual([s["zustand"] for s in stufenmeldung["stufen"]], ["deferred", "planned"])
        self.assertTrue(any("übersprungen" in e.get("text", "") for e in auftrag.gespeicherte_ereignisse()
                            if e["type"] == "technik"))

    def test_k_m_stages_stay_internal_and_promotion_happens_once(self):
        produkt = self.produkt()
        vertrag6 = vertrag(6)
        worte = [k["stichworte"][0] for k in vertrag6["kriterien"]]
        # Rückfallplan nach Regel: 3 Schritte à 2 Kriterien.
        antworten = self.stufen_antworten([f"{worte[0]} {worte[1]}", f"{worte[2]} {worte[3]}", f"{worte[4]} {worte[5]}"])
        zugang = Skriptzugang(antworten, vertrag=vertrag6)
        protokoll: list[dict[str, Any]] = []
        festschreibungen: list[bool] = []
        original = speicher.version_festschreiben

        def zaehlend(*args, **kwargs):
            festschreibungen.append(bool(kwargs.get("aktivieren")))
            return original(*args, **kwargs)

        with patch.object(pipeline.speicher, "version_festschreiben", zaehlend):
            _, nachher, ereignisse = lauf(self.user, produkt, "aendern", zugang, TABELLE_WUNSCH,
                                          pruefung=html_pruefung(protokoll, self.user, produkt["id"]))
        self.assertTrue(any(e["type"] == "stufen" for e in ereignisse))
        # Drei Schrittprüfungen und die Endabnahme — während aller Schritte blieb v1 aktiv.
        self.assertEqual(len(protokoll), 4)
        self.assertEqual({p["version"] for p in protokoll}, {1})
        self.assertEqual(festschreibungen, [True])                         # genau eine Promotion
        self.assertEqual(nachher["version"], 2)
        endfassung = speicher.version(produkt["id"], 2)
        for wort in worte:
            self.assertIn(wort, endfassung["html"])
        # Die Endabnahme lief gegen alle sechs Root-Kriterien, nicht gegen einen Teil.
        self.assertEqual(len(endfassung["pruefung"]["abnahme"]["ergebnisse"]), 6)
        self.assertEqual(endfassung["pruefung"]["abnahme"]["zaehlung"]["PASS"], 6)
        self.assertEqual(speicher.aenderungen(produkt["id"])[0]["status"], "umgesetzt")

    def test_l_a_failing_later_stage_keeps_the_active_version_and_resumes(self):
        produkt = self.produkt()
        vertrag6 = vertrag(6)
        worte = [k["stichworte"][0] for k in vertrag6["kriterien"]]
        # Schritt 1 gelingt, Schritt 2 bleibt zweimal ohne seine Stichworte.
        antworten = self.stufen_antworten([f"{worte[0]} {worte[1]}", "nichts", "wieder nichts"])
        zugang = Skriptzugang(antworten, vertrag=vertrag6)
        auftrag, nachher, ereignisse = lauf(self.user, produkt, "aendern", zugang, TABELLE_WUNSCH)
        self.assertEqual(nachher["version"], 1)
        self.assertEqual(speicher.job(self.user, auftrag.job_id)["status"], "failed")
        self.assertEqual(len(speicher.versionen(produkt["id"])), 1)       # kein halber Kandidat
        linie = speicher.offene_aenderung(produkt["id"])
        self.assertEqual(linie["checkpoint_stufe"], 1)
        self.assertIn(worte[0], linie["checkpoint"])
        fehler = [e for e in ereignisse if e["type"] == "fehler"][0]["text"]
        self.assertIn("Schritt 2 von 3", fehler)
        self.assertIn("versuch es erneut", fehler)

        # „versuch es erneut“ setzt bei Schritt 2 fort — Schritt 1 wird nicht neu geschrieben.
        weiter = Skriptzugang(self.stufen_antworten([f"{worte[2]} {worte[3]}", f"{worte[4]} {worte[5]}"]))
        _, nachher, ereignisse = lauf(self.user, produkt, "aendern", weiter, "versuch es erneut")
        self.assertEqual(len(weiter.anfragen), 2)
        self.assertTrue(any("bei Schritt 2 weiter" in e.get("text", "") for e in ereignisse if e["type"] == "hinweis"))
        self.assertEqual(nachher["version"], 2)                            # der erste Lauf schrieb keinen Kandidaten
        self.assertEqual([v["abgelehnt"] for v in speicher.versionen(produkt["id"])], [False, False])
        for wort in worte:
            self.assertIn(wort, speicher.version(produkt["id"], 2)["html"])

    def test_one_shot_truncation_switches_to_stages(self):
        produkt = self.produkt()
        vertrag2 = vertrag(2)
        worte = [k["stichworte"][0] for k in vertrag2["kriterien"]]
        antworten = [(block("<h1>BMI-Rechner</h1>", "<h1>x</h1>") + "\n<<<<<<< SUCHEN\n<la", "length"),
                     *self.stufen_antworten([f"{worte[0]} {worte[1]}"])]
        zugang = Skriptzugang(antworten, vertrag=vertrag2)
        _, nachher, ereignisse = lauf(self.user, produkt, "aendern", zugang, "Zwei Dinge")
        hinweise = [e.get("text", "") for e in ereignisse if e["type"] == "hinweis"]
        self.assertTrue(any("geprüft" in h and "Schritt" in h for h in hinweise))
        self.assertEqual(nachher["version"], 2)
        self.assertNotIn("<h1>x</h1>", speicher.version(produkt["id"], 2)["html"])


# ------------------------------------------------------------------ N, O
class AbbruchUndWaechterTests(HardeningTestfall):
    def test_n_cancel_during_a_long_generation_cleans_up(self):
        produkt = self.produkt()

        class Langsam(GespielterZugang):
            def __init__(self):
                super().__init__([])
                self.geschlossen = False
                self.stuecke = 0

            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                try:
                    while True:
                        self.stuecke += 1
                        yield {"text": "<p>weiter</p>\n"}
                        await asyncio.sleep(0.01)
                finally:
                    self.geschlossen = True

        zugang = Langsam()
        job = speicher.job_anlegen(self.user, produkt["id"], "reparieren", {"text": "x"}, "m")
        verwaltung = Auftragsverwaltung()

        async def ablauf():
            auftrag = Auftrag(job["id"], produkt["id"], self.user)

            async def schritt(laufender):
                await pipeline.Lauf(laufender, user_id=self.user, produkt=produkt, art="reparieren",
                                    eingabe=pipeline.Eingabe(text="", fehler="x"), modell="m",
                                    zugang=zugang).ausfuehren()

            verwaltung.starten(auftrag, schritt)
            while zugang.stuecke < 20:
                await asyncio.sleep(0.01)
            self.assertTrue(verwaltung.abbrechen(job["id"], self.user))
            await asyncio.gather(auftrag.task, return_exceptions=True)
            return auftrag

        auftrag = asyncio.run(ablauf())
        self.assertEqual(auftrag.status, "cancelled")
        self.assertTrue(zugang.geschlossen)                                # der Strom endete wirklich
        self.assertEqual(speicher.produkt(self.user, produkt["id"])["version"], 1)
        self.assertEqual(len(speicher.versionen(produkt["id"])), 1)
        prozesse = subprocess.run(["pgrep", "-f", "joshi-render"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(prozesse, "")
        self.assertEqual(glob.glob(os.path.join(os.environ.get("TMPDIR", "/tmp"), "joshi-*")), [])

    def test_o_a_runaway_generation_is_stopped_without_a_broken_version(self):
        produkt = self.produkt(BMI)

        class Endlos(GespielterZugang):
            def __init__(self):
                super().__init__([])
                self.geschlossen = 0

            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                try:
                    while True:
                        yield {"text": "<div class='zeile'>immer gleich</div>\n" * 40}
                        await asyncio.sleep(0.001)
                finally:
                    self.geschlossen += 1

        zugang = Endlos()
        auftrag, nachher, ereignisse = lauf(self.user, produkt, "reparieren", zugang, "", fehler="x")
        self.assertEqual(nachher["version"], 1)
        self.assertEqual(len(speicher.versionen(produkt["id"])), 1)
        job = speicher.job(self.user, auftrag.job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("kontrolliert beendet", job["fehler"])
        self.assertTrue(any(s["stufe"] == "hart" for s in job["ergebnis"]["diagnose"]["signale"]))
        self.assertGreaterEqual(zugang.geschlossen, 1)

    def test_the_watchdog_is_relative_and_configurable(self):
        g = grenzen.Grenzen()
        klein = grenzen.Waechter(7609, bloecke=True, grenzen=g)
        self.assertEqual(klein.hart_zeichen, 160_000)
        gross = grenzen.Waechter(200_000, bloecke=True, grenzen=g)
        self.assertEqual(gross.hart_zeichen, 2_000_000)                 # große Apps dürfen groß ändern
        self.assertIsNone(klein.pruefen("x" * 1000, 5))
        # 112 Blöcke gegen eine Datei von 7.609 Zeichen: harte Grenze.
        signal = klein.pruefen("<<<<<<< SUCHEN\na\n=======\nb\n>>>>>>> ERSETZEN\n" * 112, 10)
        self.assertEqual((signal.art, signal.stufe), ("bloecke", "hart"))
        with patch.dict(os.environ, {"JOSHI_GRENZE_HART_MINIMUM": "5000", "JOSHI_GRENZE_HART_FAKTOR": "2"}):
            eng = grenzen.Grenzen.aus_umgebung()
        self.assertEqual((eng.hart_minimum, eng.hart_faktor), (5000, 2.0))
        self.assertTrue(grenzen.ist_abgeschnitten("length"))
        self.assertTrue(grenzen.ist_abgeschnitten("MAX_TOKENS"))
        self.assertFalse(grenzen.ist_abgeschnitten("stop"))


# ------------------------------------------------------------------ Promotion
class PromotionsschutzTests(HardeningTestfall):
    """The last accepted version always wins over an unverified candidate."""

    def setUp(self):
        super().setUp()
        from app.joshi import api

        self.api = api
        api.einrichten(api.Anbindung(nutzer=lambda request: {"id": self.user}, zugang=GespielterZugang([]),
                                     anhaenge=None, lese_upload=None, kontexte=None))
        self.p = self.produkt()
        speicher.version_festschreiben(self.p["id"], GROSS + "<!-- abgelehnt -->", "Kandidat",
                                       pruefung={"ok": False, "abgelehnt": True})
        speicher.version_festschreiben(self.p["id"], GROSS + "<!-- v3 -->", "Gute Änderung",
                                       pruefung={"ok": True}, aktivieren=True, status="ready")

    def test_a_rejected_candidate_needs_explicit_consent(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as fehler:
            asyncio.run(self.api.version_aktivieren(FakeRequest(), self.p["id"], 2))
        self.assertEqual(fehler.exception.status_code, 409)
        self.assertIn("nie freigegeben", str(fehler.exception.detail))
        antwort = asyncio.run(self.api.version_aktivieren(FakeRequest(), self.p["id"], 2, bewusst=True))
        self.assertEqual(antwort["produkt"]["version"], 2)
        self.assertEqual(antwort["produkt"]["status"], "needs_attention")

    def test_undo_skips_rejected_candidates(self):
        antwort = asyncio.run(self.api.rueckgaengig(FakeRequest(), self.p["id"]))
        self.assertEqual(antwort["produkt"]["version"], 1)
        self.assertTrue([v for v in speicher.versionen(self.p["id"]) if v["nummer"] == 2][0]["abgelehnt"])


# ------------------------------------------------------------------ J, Beweise
class BeweisTests(unittest.TestCase):
    """Acceptance is evidence-based and action-specific; NOT_PROVEN is not PASS."""

    def beweise(self, klicks: list[dict[str, Any]], **weitere: Any) -> dict[str, Any]:
        return abnahme.beweise_sammeln({"knoepfe": [k["knopf"] for k in klicks], "ueberschriften": ["Notizen"],
                                        "markdown": "Notizen Titel Text", "anzahl": {}},
                                       {"klicks": klicks}, **weitere)

    def kriterium(self, aktion: str, text: str, stichwort: str) -> dict[str, Any]:
        return {"kriterien": [{"id": aktion, "beschreibung": text, "stichworte": [stichwort], "pflicht": True,
                               "nachweis": "bedienung", "aktion": aktion}]}

    def urteil(self, vertrag_: dict[str, Any], beweise: dict[str, Any]) -> abnahme.Ergebnis:
        return abnahme.deterministisch_pruefen(vertrag_, beweise)[0]

    def test_e_storage_change_proves_save_without_new_dom(self):
        beweise = self.beweise([{"knopf": "Speichern", "effekte": ["local_storage_changed"], "speicher": ["notiz"]}])
        ergebnis = self.urteil(self.kriterium("speichern", "Speichern sichert die Notiz", "Speichern"), beweise)
        self.assertEqual(ergebnis.status, "PASS")
        self.assertIn("local_storage_changed", ergebnis.begruendung)
        self.assertEqual(ergebnis.beleg, "klick:Speichern")

    def test_f_g_action_probes_prove_load_and_reset(self):
        beweise = self.beweise([], aktionen=[
            {"aktion": "laden", "knopf": "Laden", "ergebnis": "bestanden", "belege": ["local_storage_restored"]},
            {"aktion": "neu", "knopf": "Neu", "ergebnis": "gescheitert", "belege": [],
             "grund": "Nach „Neu“ blieben die eingegebenen Daten unverändert"}])
        self.assertEqual(self.urteil(self.kriterium("laden", "Laden stellt den Stand wieder her", "Laden"),
                                     beweise).status, "PASS")
        neu = self.urteil(self.kriterium("neu", "Neu leert die Notiz", "Neu"), beweise)
        self.assertEqual(neu.status, "FAIL")

    def test_h_an_export_request_counts_without_new_dom(self):
        beweise = self.beweise([{"knopf": "Exportieren", "effekte": ["export_requested"], "export": "pdf"}])
        self.assertEqual(self.urteil(self.kriterium("export", "Die Notiz lässt sich exportieren", "Exportieren"),
                                     beweise).status, "PASS")
        download = self.beweise([{"knopf": "Herunterladen", "effekte": ["download_triggered"]}])
        self.assertEqual(self.urteil(self.kriterium("export", "Die Notiz lässt sich herunterladen", "Herunterladen"),
                                     download).status, "PASS")

    def test_i_a_click_without_any_effect_fails(self):
        beweise = self.beweise([{"knopf": "Speichern", "effekte": []}])
        ergebnis = self.urteil(self.kriterium("speichern", "Speichern sichert die Notiz", "Speichern"), beweise)
        self.assertEqual(ergebnis.status, "FAIL")
        self.assertIn("keine nachweisbare Wirkung", ergebnis.begruendung)
        # Eine Wirkung, die nicht zur Aktion passt, beweist nichts.
        falsch = self.beweise([{"knopf": "Speichern", "effekte": ["text_changed"]}])
        self.assertEqual(self.urteil(self.kriterium("speichern", "Speichern sichert", "Speichern"), falsch).status,
                         "NOT_PROVEN")

    def test_j_the_model_judge_cannot_pass_without_evidence(self):
        vertrag_ = self.kriterium("speichern", "Speichern sichert die Notiz", "Speichern")
        beweise = self.beweise([{"knopf": "Speichern", "effekte": ["text_changed"]}])
        for beleg in ("", "knoepfe", "klick:Laden", "aktion:speichern", "text"):
            zugang = GespielterZugang([], urteile={"ergebnisse": [
                {"id": "speichern", "urteil": "erfuellt", "beleg": beleg, "begruendung": "sieht gut aus"}]})
            bericht = asyncio.run(abnahme.pruefen(zugang, "m", vertrag_, beweise,
                                                  verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
            self.assertEqual(bericht.ergebnisse[0].status, "NOT_PROVEN", beleg)
            self.assertEqual([b.art for b in bericht.befunde()], ["unbewiesen"])
        pruefbericht = pruefer.Pruefbericht([Befund("unbewiesen", "x")], browser=True)
        self.assertFalse(pruefbericht.ok)                                    # UNKNOWN != PASS

    def test_a_valid_citation_lets_the_judge_confirm(self):
        vertrag_ = {"kriterien": [{"id": "hell", "beschreibung": "Der Hintergrund ist heller", "stichworte": ["hell"],
                                   "pflicht": True, "nachweis": "gestaltung"}]}
        beweise = abnahme.beweise_sammeln({"knoepfe": ["X"], "stil": {"seite": "rgb(250, 250, 250)"}}, {},
                                          baseline={"stil": {"seite": "rgb(20, 20, 20)"}})
        zugang = GespielterZugang([], urteile={"ergebnisse": [
            {"id": "hell", "urteil": "erfuellt", "beleg": "stil", "begruendung": "20 → 250"}]})
        bericht = asyncio.run(abnahme.pruefen(zugang, "m", vertrag_, beweise,
                                              verbrauch={"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))
        self.assertEqual(bericht.ergebnisse[0].status, "PASS")

    def test_multi_session_requirements_are_honestly_not_provable(self):
        vertrag_ = abnahme.vertrag_normalisieren({"kriterien": [
            {"id": "sync", "beschreibung": "Zwei Tabs bearbeiten dieselbe Zelle und bleiben synchron",
             "stichworte": ["Tab"], "nachweis": "ablauf"},
            {"id": "offline", "beschreibung": "Offline-Eingaben werden nach dem Reconnect übernommen",
             "stichworte": ["Offline"]}]}, "x")
        self.assertEqual([k["nachweis"] for k in vertrag_["kriterien"]], ["nicht_pruefbar", "nicht_pruefbar"])
        ergebnisse = abnahme.deterministisch_pruefen(vertrag_, self.beweise([]))
        self.assertEqual({e.status for e in ergebnisse}, {"NOT_PROVEN"})
        bericht = abnahme.Abnahmebericht(vertrag_, ergebnisse)
        self.assertEqual([b.art for b in bericht.befunde()], ["unbeweisbar"])
        self.assertNotIn("unbeweisbar", pruefer.REPARIERBAR)                 # keine sinnlose Reparatur

    def test_scenarios_are_data_not_code(self):
        roh = {"szenarien": [{"kriterium": "k1", "schritte": [
            {"art": "eingeben", "ziel": "A1", "wert": "=0.1+0.2"}, {"art": "eval", "wert": "alert(1)"},
            {"art": "text_enthaelt", "wert": "0.3"}]},
            {"kriterium": "fremd", "schritte": [{"art": "keine_fehler"}]}]}
        szenarien = abnahme.szenarien_normalisieren(roh, ["k1"])
        self.assertEqual(len(szenarien), 1)
        self.assertEqual([s["art"] for s in szenarien[0]["schritte"]], ["eingeben", "text_enthaelt"])


# ------------------------------------------------------------ echtes WebKit
NOTIZEN = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>Notizen</title></head>
<body>
<h1>Notizen</h1>
<label for="titel">Titel</label><input id="titel" value="Einkauf">
<label for="text">Text</label><textarea id="text">Milch</textarea>
<button type="button" id="speichern">Speichern</button>
<button type="button" id="laden">Laden</button>
<button type="button" id="neu">Neu</button>
<button type="button" id="archiv">Archivieren</button>
<button type="button" id="pdf">Als PDF exportieren</button>
<button type="button" id="undo">Rückgängig</button>
<button type="button" id="redo">Wiederholen</button>
<p id="zaehler">Zeichen: 5</p>
<script>
const titel = document.getElementById("titel"), text = document.getElementById("text");
const verlauf = [], zukunft = [];
let letzter = titel.value;
function zaehlen() { document.getElementById("zaehler").textContent = "Zeichen: " + text.value.length; }
titel.addEventListener("change", () => { verlauf.push(letzter); zukunft.length = 0; letzter = titel.value; });
text.addEventListener("input", zaehlen);
document.getElementById("speichern").onclick = () =>
  localStorage.setItem("notiz", JSON.stringify({ t: titel.value, x: text.value }));
document.getElementById("laden").onclick = () => {
  const d = JSON.parse(localStorage.getItem("notiz") || "null");
  if (d) { verlauf.push(letzter); titel.value = d.t; text.value = d.x; letzter = d.t; zaehlen(); }
};
document.getElementById("neu").onclick = () => {
  verlauf.push(letzter); titel.value = ""; text.value = ""; letzter = ""; zaehlen();
};
document.getElementById("archiv").onclick = () => {};
document.getElementById("pdf").onclick = () => window.JOSHI.export({ type: "pdf", target: "body", filename: "notiz.pdf" });
document.getElementById("undo").onclick = () => {
  if (!verlauf.length) return; zukunft.push(titel.value); titel.value = verlauf.pop(); letzter = titel.value;
};
document.getElementById("redo").onclick = () => {
  if (!zukunft.length) return; verlauf.push(titel.value); titel.value = zukunft.pop(); letzter = titel.value;
};
const gemerkt = JSON.parse(localStorage.getItem("notiz") || "null");
if (gemerkt) { titel.value = gemerkt.t; text.value = gemerkt.x; letzter = gemerkt.t; }
zaehlen();
</script>
</body></html>"""

NOTIZ_VERTRAG = {"zusammenfassung": "Notizen speichern, laden, neu anlegen", "kriterien": [
    {"id": "speichern", "beschreibung": "Speichern sichert die Notiz", "stichworte": ["Speichern"],
     "pflicht": True, "nachweis": "bedienung", "aktion": "speichern"},
    {"id": "laden", "beschreibung": "Laden stellt die gespeicherte Notiz wieder her", "stichworte": ["Laden"],
     "pflicht": True, "nachweis": "bedienung", "aktion": "laden"},
    {"id": "neu", "beschreibung": "Neu leert die Notiz", "stichworte": ["Neu"],
     "pflicht": True, "nachweis": "bedienung", "aktion": "neu"},
    {"id": "export", "beschreibung": "Die Notiz lässt sich exportieren", "stichworte": ["exportieren"],
     "pflicht": True, "nachweis": "bedienung", "aktion": "export"},
    {"id": "archiv", "beschreibung": "Archivieren legt die Notiz im Archiv ab", "stichworte": ["Archivieren"],
     "pflicht": True, "nachweis": "bedienung", "aktion": "sonstiges"},
]}


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class EchteBeweisTests(unittest.TestCase):
    """Die neue Beweiskette im echten WebKit — der reale Fehlerfall als Regressionstest."""

    @classmethod
    def setUpClass(cls):
        cls.bericht = asyncio.run(pruefer.pruefen(NOTIZEN))
        cls.aktionen, cls.szenarien = asyncio.run(pruefer.szenarien_ausfuehren(
            NOTIZEN, aktionen=abnahme.benoetigte_proben(NOTIZ_VERTRAG) + ["rueckgaengig", "wiederholen"]))

    def klick(self, name: str) -> dict[str, Any]:
        return next(k for k in self.bericht.interaktion["klicks"] if k["knopf"] == name)

    def test_e_save_shows_up_in_storage_not_in_the_dom(self):
        speichern = self.klick("Speichern")
        self.assertIn("local_storage_changed", speichern["effekte"])
        self.assertNotIn("dom_added", speichern["effekte"])
        self.assertEqual(speichern["speicher"], ["notiz"])

    def test_h_export_is_a_capability_request(self):
        self.assertIn("export_requested", self.klick("Als PDF exportieren")["effekte"])

    def test_i_a_dead_button_has_no_effect(self):
        self.assertEqual(self.klick("Archivieren")["effekte"], [])

    def test_f_g_action_probes_in_a_real_page(self):
        ergebnisse = {a["aktion"]: a for a in self.aktionen}
        self.assertEqual(ergebnisse["speichern"]["ergebnis"], "bestanden", ergebnisse["speichern"])
        self.assertEqual(ergebnisse["laden"]["ergebnis"], "bestanden", ergebnisse["laden"])
        self.assertIn("local_storage_restored", ergebnisse["laden"]["belege"])
        self.assertEqual(ergebnisse["neu"]["ergebnis"], "bestanden", ergebnisse["neu"])
        self.assertEqual(ergebnisse["rueckgaengig"]["ergebnis"], "bestanden", ergebnisse["rueckgaengig"])
        self.assertEqual(ergebnisse["wiederholen"]["ergebnis"], "bestanden", ergebnisse["wiederholen"])

    def test_the_real_failure_case_now_passes_on_evidence(self):
        """„Kein Klick ließ etwas Neues erscheinen“ — jetzt mit Beweisen je Aktion."""
        beweise = abnahme.beweise_sammeln(self.bericht.gliederung, self.bericht.interaktion,
                                          exporte=self.bericht.exporte, aktionen=self.aktionen)
        ergebnisse = {e.id: e for e in abnahme.deterministisch_pruefen(NOTIZ_VERTRAG, beweise)}
        self.assertEqual({k: ergebnisse[k].status for k in ("speichern", "laden", "neu", "export")},
                         {"speichern": "PASS", "laden": "PASS", "neu": "PASS", "export": "PASS"})
        self.assertEqual(ergebnisse["archiv"].status, "FAIL")
        self.assertTrue(all("Kein Klick ließ" not in e.begruendung for e in ergebnisse.values()))

    def test_scenarios_survive_a_real_reload(self):
        aktionen, szenarien = asyncio.run(pruefer.szenarien_ausfuehren(NOTIZEN, szenarien=[
            {"id": "s_persist", "kriterium": "persist", "schritte": [
                {"art": "eingeben", "ziel": "Titel", "wert": "Urlaub"},
                {"art": "klicken", "ziel": "Speichern"},
                {"art": "neu_laden"},
                {"art": "wert_ist", "ziel": "titel", "wert": "Urlaub"},
                {"art": "speicher_enthaelt", "wert": "Urlaub"}]},
            {"id": "s_falsch", "kriterium": "falsch", "schritte": [
                {"art": "eingeben", "ziel": "Text", "wert": "abc"}, {"art": "text_enthaelt", "wert": "Zeichen: 99"}]},
            {"id": "s_zwei", "kriterium": "zwei", "schritte": [
                {"art": "zweite_sitzung"}, {"art": "keine_fehler"}]},
            {"id": "s_zeit", "kriterium": "zeit", "schritte": [
                {"art": "messen"}, {"art": "eingeben", "ziel": "Text", "wert": "x" * 50},
                {"art": "dauer_hoechstens", "ms": 5000}, {"art": "text_enthaelt", "wert": "Zeichen: 50"}]},
        ]))
        ergebnisse = {s["id"]: s for s in szenarien}
        self.assertEqual(ergebnisse["s_persist"]["ergebnis"], "bestanden", ergebnisse["s_persist"])
        self.assertEqual(ergebnisse["s_persist"]["phasen"], 2)
        self.assertEqual(ergebnisse["s_falsch"]["ergebnis"], "gescheitert")
        self.assertIn("Zeichen: 3", ergebnisse["s_falsch"]["grund"])
        self.assertEqual(ergebnisse["s_zwei"]["ergebnis"], "nicht_beweisbar")
        self.assertEqual(ergebnisse["s_zeit"]["ergebnis"], "bestanden", ergebnisse["s_zeit"])
        self.assertIn("dauer_ms_3", ergebnisse["s_zeit"]["messwerte"])

    def test_the_generic_probe_still_passes_the_app(self):
        self.assertTrue(self.bericht.ok, self.bericht.befunde)


if __name__ == "__main__":
    unittest.main()
