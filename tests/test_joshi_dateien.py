# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Asset-/Eingabeordner und Projekt-Workspace.

SINGLE FILE FIRST — INBOUND WHEN USEFUL — WORKSPACE ONLY WHEN NECESSARY.

Alle Tests laufen in einem eigenen, vorgetäuschten Benutzerordner (HOME) —
nichts davon berührt echte Ordner. Das Modell ist gespielt, der Prüfer auch;
geprüft wird, was JOSHI mit den Dateien tut.
"""
from __future__ import annotations

import asyncio
import zipfile
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

try:
    from test_joshi import FakeRequest, GespielterZugang, SpeicherTestfall
except ImportError:  # als Paket gestartet
    from tests.test_joshi import FakeRequest, GespielterZugang, SpeicherTestfall

from fastapi import HTTPException, UploadFile  # noqa: E402

from app.joshi import dateien, eingaben, export, pipeline, projekt, pruefer, speicher  # noqa: E402
from app.joshi.jobs import verwaltung  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def png(farbe: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    from PIL import Image

    ausgabe = io.BytesIO()
    Image.new("RGB", (8, 8), farbe).save(ausgabe, format="PNG")
    return ausgabe.getvalue()


APP_MIT_ICON = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Aufgaben</title></head>
<body><header><img src="joshi:bild-1" alt="Icon" width="32"><h1>Aufgabenplaner</h1></header>
<label for="aufgabe">Aufgabe</label><input id="aufgabe"><button type="button">Hinzufügen</button>
<script>document.querySelector("button").onclick=()=>{};</script></body></html>"""

APP_MIT_BILDERN = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Katalog</title></head>
<body><h1>Produktkatalog</h1><img src="joshi:bild-1" alt="a"><img src="joshi:bild-2" alt="b">
<img src="joshi:bild-3" alt="c"><table><tr><td>Kunde A</td></tr></table></body></html>"""


async def gespielte_pruefung(html, **_):
    return pruefer.Pruefbericht([], browser=True, gliederung={}, interaktion={"gefuellt": 1, "geklickt": 1})


class OrdnerTestfall(SpeicherTestfall):
    def setUp(self):
        super().setUp()
        self.heim = tempfile.TemporaryDirectory()
        self.umgebung_heim = patch.dict(os.environ, {"HOME": self.heim.name})
        self.umgebung_heim.start()
        self.eingang = Path(self.heim.name) / "JOSHI-Eingaben"
        self.werkstatt = Path(self.heim.name) / "JOSHI-Workspace"
        self.eingang.mkdir()
        (self.eingang / "icon.png").write_bytes(png())
        (self.eingang / "kunden.csv").write_text("Name;Umsatz\nMüller;1200\nSchmidt;900\n", encoding="utf-8")
        (self.eingang / "anforderungen.pdf").write_bytes(b"%PDF-1.4 Anforderungen: Kundenliste mit Umsatz")
        from app.joshi import api

        self.api = api
        self.zugang = GespielterZugang([])

        async def anhaenge(liste):
            teile = []
            for datei in liste:
                daten = await datei.read()
                teile.append(f'<datei name="{datei.filename}">\n{daten.decode("utf-8", "replace")[:2000]}\n</datei>')
            return "\n".join(teile), [], []

        async def lesen(datei):
            return await datei.read()

        api.einrichten(api.Anbindung(nutzer=lambda request: {"id": self.user}, zugang=self.zugang,
                                     anhaenge=anhaenge, lese_upload=lesen, kontexte=None))

    def tearDown(self):
        self.umgebung_heim.stop()
        self.heim.cleanup()
        super().tearDown()

    def einstellen(self, *, eingaben_an: bool = True, workspace_an: bool = False, **weitere: Any) -> dict[str, Any]:
        daten = {"eingaben": {"aktiv": eingaben_an, "pfad": str(self.eingang)},
                 "workspace": {"aktiv": workspace_an, "pfad": str(self.werkstatt)}, **weitere}
        return asyncio.run(self.api.einstellungen_aendern(FakeRequest(), daten))

    def bauen(self, text: str, antworten: list[str], modus: str = "") -> dict[str, Any]:
        self.zugang.antworten = list(antworten)

        async def ablauf():
            antwort = await self.api.produkt_erstellen(FakeRequest(), text=text, modell="m", chat="", modus=modus,
                                                       dateien=None)
            if "job" in antwort:
                laufend = verwaltung.laufend_fuer(antwort["produkt"]["id"])
                if laufend and laufend.task:
                    await laufend.task
            return antwort

        with patch.object(pipeline.pruefer, "pruefen", gespielte_pruefung):
            return asyncio.run(ablauf())

    def aendern(self, produkt_id: str, text: str, antworten: list[str], modus: str = "") -> dict[str, Any]:
        self.zugang.antworten = list(antworten)

        async def ablauf():
            antwort = await self.api.auftrag_starten(FakeRequest(), produkt_id, text=text, modell="m", art="aendern",
                                                     fehler="", modus=modus, dateien=None)
            if "job" in antwort:
                laufend = verwaltung.laufend_fuer(produkt_id)
                if laufend and laufend.task:
                    await laufend.task
            return antwort

        with patch.object(pipeline.pruefer, "pruefen", gespielte_pruefung):
            return asyncio.run(ablauf())

    def modellanfragen(self) -> str:
        return json.dumps(self.zugang.anfragen, ensure_ascii=False)


# ------------------------------------------------------------ Eingabeordner
class EingabeordnerTests(OrdnerTestfall):
    def test_a_2_inbound_off_nothing_reaches_the_model(self):
        self.einstellen(eingaben_an=False)
        antwort = self.bauen("Erstelle aus @kunden.csv ein Dashboard mit @icon.png", [APP_MIT_ICON])
        job = speicher.job(self.user, antwort["job"]["id"])
        self.assertEqual(job["eingabe"]["eingaben"], [])
        self.assertNotIn("Müller", self.modellanfragen())
        self.assertEqual(speicher.bilder(antwort["produkt"]["id"]), [])

    def test_b_4_an_active_file_is_available_as_data(self):
        self.einstellen()
        wahl = asyncio.run(self.api._eingaben_fuer(self.user, "Erstelle aus der CSV ein kleines Kundendashboard"))
        self.assertEqual([(a.datei.name, a.rolle) for a in wahl.auswahl], [("kunden.csv", "data")])
        self.assertEqual([d.filename for d in self.api._als_upload(wahl.auswahl)], ["kunden.csv"])

    def test_c_a_deactivated_file_is_not_used_unless_named(self):
        self.einstellen()
        asyncio.run(self.api.eingabe_umschalten(FakeRequest(), {"name": "kunden.csv", "aktiv": False}))
        wahl = asyncio.run(self.api._eingaben_fuer(self.user, "Erstelle aus der CSV ein Dashboard"))
        self.assertEqual(wahl.auswahl, [])
        genannt = asyncio.run(self.api._eingaben_fuer(self.user, "Erstelle aus @kunden.csv ein Dashboard"))
        self.assertEqual([a.datei.name for a in genannt.auswahl], ["kunden.csv"])

    def test_d_a_new_file_is_detected_but_not_used(self):
        self.einstellen()
        vorher = asyncio.run(self.api.eingaben_lesen(FakeRequest()))
        (self.eingang / "hero.jpg").write_bytes(png((10, 10, 200)))
        nachher = asyncio.run(self.api.eingaben_lesen(FakeRequest()))
        neu = {d["name"] for d in nachher["dateien"]} - {d["name"] for d in vorher["dateien"]}
        self.assertEqual(neu, {"hero.jpg"})
        self.assertTrue(next(d for d in nachher["dateien"] if d["name"] == "hero.jpg")["aktiv"])
        joshi_js = (ROOT / "static" / "joshi.js").read_text(encoding="utf-8")
        self.assertIn("Neue Datei", joshi_js)
        self.assertIn("setInterval", joshi_js)

    def test_5_irrelevant_files_stay_out_of_a_calculator(self):
        for nummer in range(22):
            (self.eingang / f"datei-{nummer}.txt").write_text("irrelevant", encoding="utf-8")
        self.einstellen()
        wahl = asyncio.run(self.api._eingaben_fuer(self.user, "Baue einen einfachen Taschenrechner."))
        self.assertEqual(wahl.auswahl, [])
        self.assertFalse(wahl.bedarf.noetig)

    def test_3_a_pdf_is_context_and_never_embedded(self):
        self.einstellen()
        wahl = asyncio.run(self.api._eingaben_fuer(self.user, "Baue daraus eine Anwendung."))
        rollen = {a.datei.name: a.rolle for a in wahl.auswahl}
        self.assertEqual(rollen["anforderungen.pdf"], "context")
        self.assertIn("nicht in die Anwendung kopieren", eingaben.rollen_text(wahl.auswahl))
        als_dokument = eingaben.auswaehlen("Die @anforderungen.pdf soll in der Anwendung zum Download verfügbar sein",
                                           dateien.Wurzel(self.eingang, schreibbar=False, name="x").liste())
        self.assertEqual(als_dokument[0].rolle, "asset")

    def test_1_6_f_o_an_icon_is_embedded_in_the_single_file(self):
        self.einstellen()
        antwort = self.bauen("Erstelle mir einen Aufgabenplaner. Nutze das vorhandene Bild als Icon der Anwendung.",
                             [APP_MIT_ICON])
        produkt = speicher.produkt(self.user, antwort["produkt"]["id"])
        self.assertEqual(produkt["version"], 1)
        self.assertNotIn("workspace", produkt["quelle"])                # kein Projektordner
        self.assertFalse(self.werkstatt.exists())
        bilder = speicher.bilder(produkt["id"])
        self.assertEqual([b["datei"] for b in bilder], ["icon.png"])
        portabel = export.portables_html(produkt, speicher.version(produkt["id"], 1),
                                         speicher.bild_data_uris(produkt["id"])).decode()
        self.assertIn("data:image/png;base64,", portabel)               # eine Datei, alles drin
        self.assertIn("img-src data: blob:;", portabel)                  # Standardrichtlinie unverändert

    def test_p_q_12_the_snapshot_protects_the_accepted_version(self):
        self.einstellen()
        antwort = self.bauen("Erstelle einen Aufgabenplaner mit @icon.png als Icon.", [APP_MIT_ICON])
        produkt_id = antwort["produkt"]["id"]
        job = speicher.job(self.user, antwort["job"]["id"])
        schnappschuss = job["eingabe"]["eingaben"][0]
        self.assertEqual({k for k in schnappschuss} >= {"name", "art", "rolle", "groesse", "sha256", "zeit"}, True)
        self.assertEqual((schnappschuss["name"], schnappschuss["rolle"]), ("icon.png", "asset"))
        version = speicher.version(produkt_id, 1)
        self.assertEqual(version["pruefung"]["eingaben"][0]["sha256"], schnappschuss["sha256"])
        vorher = speicher.bild_bytes(produkt_id, "bild-1")[0]
        (self.eingang / "icon.png").write_bytes(png((0, 200, 0)))        # Original ändert sich später
        self.assertEqual(speicher.bild_bytes(produkt_id, "bild-1")[0], vorher)
        self.assertEqual(speicher.version(produkt_id, 1)["html"], version["html"])
        self.assertEqual(dateien.pruefsumme(vorher), schnappschuss["sha256"])


# ------------------------------------------------------------ Workspace
class WorkspaceTests(OrdnerTestfall):
    def viele_bilder(self, anzahl: int = 14) -> None:
        for nummer in range(anzahl):
            (self.eingang / f"produkt-{nummer:02d}.png").write_bytes(png((nummer * 15, 90, 160)))

    def test_e_9_a_small_app_never_creates_a_project(self):
        self.einstellen(workspace_an=True)
        antwort = self.bauen("Baue einen BMI-Rechner.", [APP_MIT_ICON])
        self.assertEqual(speicher.produkt(self.user, antwort["produkt"]["id"])["version"], 1)
        self.assertEqual(list(self.werkstatt.iterdir()), [])            # Ordner freigegeben, aber leer
        self.assertEqual(speicher.job(self.user, antwort["job"]["id"])["eingabe"]["modus"], "einzeldatei")

    # Seit 29.09.2026 ohne Workspace-Schalter: JOSHI fragt nicht mehr, sondern
    # sichert jedes Produkt in seinem internen Arbeitsordner.
    def intern(self, produkt_id: str) -> Path:
        from app import database
        from app.joshi import projektdateien
        return projektdateien.ordner(database.DATA_DIR, speicher.produkt(self.user, produkt_id))

    def test_g_7_h_8_a_big_project_is_built_without_asking(self):
        self.viele_bilder()
        self.einstellen(workspace_an=False)
        antwort = self.bauen("Erstelle daraus eine größere mehrteilige Anwendung.", [APP_MIT_BILDERN])
        self.assertNotIn("empfehlung", antwort)
        produkt = speicher.produkt(self.user, antwort["produkt"]["id"])
        self.assertEqual(produkt["version"], 1)
        self.assertTrue((self.intern(produkt["id"]) / "index.html").is_file())
        self.assertFalse(self.werkstatt.exists())                         # nichts im Nutzer-Workspace

    def test_i_10_11_l_13_a_big_project_gets_its_folder_and_documentation(self):
        self.viele_bilder()
        self.einstellen(workspace_an=False)
        antwort = self.bauen("Erstelle daraus einen vollständigen Produktkatalog mit Verwaltung, "
                             "nutze die Bilder und @kunden.csv", [APP_MIT_BILDERN])
        produkt = speicher.produkt(self.user, antwort["produkt"]["id"])
        ordner = self.intern(produkt["id"])
        self.assertTrue((ordner / "index.html").is_file())
        gezeigt = {b["name"]: b["datei"] for b in speicher.bilder(produkt["id"])}
        self.assertEqual(sorted(p.name for p in (ordner / "assets").iterdir()),
                         sorted(gezeigt[f"bild-{n}"] for n in (1, 2, 3)))  # nur die gezeigten Bilder
        self.assertEqual((ordner / "data" / "kunden.csv").read_text(encoding="utf-8").splitlines()[1], "Müller;1200")
        index = (ordner / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'src="assets/{gezeigt["bild-1"]}"', index)
        doku = (ordner / "JOSHI_PROJECT.md").read_text(encoding="utf-8")
        for abschnitt in ("## Zweck", "## Architektur", "## Daten", "## Eingaben", "## Version / Stand"):
            self.assertIn(abschnitt, doku)
        self.assertTrue(produkt["quelle"]["intern"]["zip"])                # Daten gehören dazu → ZIP
        antwort = asyncio.run(self.api.exportieren(FakeRequest(), produkt["id"], "html"))
        self.assertEqual(antwort.media_type, "application/zip")
        with zipfile.ZipFile(io.BytesIO(antwort.body)) as archiv:
            namen = archiv.namelist()
        self.assertIn(f"{ordner.name}/index.html", namen)
        self.assertIn(f"{ordner.name}/data/kunden.csv", namen)

    def test_m_the_documentation_follows_a_significant_change(self):
        self.viele_bilder()
        self.einstellen(workspace_an=False)
        antwort = self.bauen("Erstelle daraus einen vollständigen Produktkatalog mit Verwaltung",
                             [APP_MIT_BILDERN])
        produkt_id = antwort["produkt"]["id"]
        ordner = self.intern(produkt_id)
        doku = ordner / "JOSHI_PROJECT.md"
        doku.write_text(doku.read_text(encoding="utf-8").replace("## Notizen\n", "## Notizen\nMeine eigene Notiz.\n"),
                        encoding="utf-8")
        self.aendern(produkt_id, "Füge eine Suche hinzu", [APP_MIT_BILDERN.replace("</h1>", "</h1><input id='suche'>")])
        self.assertEqual(speicher.produkt(self.user, produkt_id)["version"], 2)
        neu = doku.read_text(encoding="utf-8")
        self.assertIn("- v2 (", neu)
        self.assertIn("Meine eigene Notiz.", neu)
        self.assertIn("<input id='suche'>", (ordner / "index.html").read_text(encoding="utf-8"))

    def test_a_small_app_is_shared_as_one_html_file(self):
        self.einstellen(workspace_an=False)
        antwort = self.bauen("Baue einen kleinen Inventarplaner", [APP_MIT_ICON])
        produkt_id = antwort["produkt"]["id"]
        self.assertFalse(speicher.produkt(self.user, produkt_id)["quelle"]["intern"]["zip"])
        export_antwort = asyncio.run(self.api.exportieren(FakeRequest(), produkt_id, "html"))
        self.assertTrue(export_antwort.media_type.startswith("text/html"))
        gross = self.aendern(produkt_id, "Mach daraus ein vollständiges Verwaltungssystem mit 2.000 Produktbildern, "
                                         "Datenimport, Dokumentation und mehreren Modulen", [APP_MIT_ICON])
        self.assertNotIn("empfehlung", gross)                             # keine Rückfrage mehr

    def test_n_existing_small_products_are_untouched(self):
        produkt = speicher.produkt_anlegen(self.user, "Alt", "Alt", {})
        speicher.version_festschreiben(produkt["id"], APP_MIT_ICON.replace("joshi:bild-1", "x.png"), "Erstfassung",
                                       pruefung={"ok": True}, aktivieren=True, status="ready")
        einstellungen = speicher.einstellungen(self.user)
        self.assertFalse(einstellungen["eingaben"]["aktiv"])              # alles aus, bis der Nutzer es will
        self.assertFalse(einstellungen["workspace"]["aktiv"])
        antwort = self.aendern(produkt["id"], "Mach die Überschrift blau",
                               [APP_MIT_ICON.replace("joshi:bild-1", "x.png").replace("<h1>", "<h1 style='color:blue'>")])
        job = speicher.job(self.user, antwort["job"]["id"])
        self.assertEqual((job["eingabe"]["eingaben"], job["eingabe"]["modus"]), ([], "einzeldatei"))
        self.assertEqual(speicher.produkt(self.user, produkt["id"])["version"], 2)


# ------------------------------------------------------------ Sicherheit
class OrdnerSicherheitTests(OrdnerTestfall):
    def test_j_15_the_workspace_cannot_be_left(self):
        self.werkstatt.mkdir()
        wurzel = dateien.Wurzel(self.werkstatt, schreibbar=True, name="Workspace")
        for pfad in ("../JOSHI-Eingaben/icon.png", "/etc/passwd", "~/x", "a/../../x", ".ssh/id_rsa", "a\\b", ""):
            with self.assertRaises(dateien.Pfadfehler, msg=pfad):
                wurzel.schreiben(pfad, b"x")
        (self.werkstatt / "raus").symlink_to(self.eingang)
        with self.assertRaises(dateien.Pfadfehler):
            wurzel.schreiben("raus/icon.png", b"x")                       # Symlink-Ausbruch
        with self.assertRaises(dateien.Pfadfehler):
            dateien.ausfuehren({"workspace": wurzel, "eingaben": dateien.Wurzel(self.eingang, schreibbar=False,
                                                                                 name="E")},
                               "workspace.copy", {"quelle": "../JOSHI-Workspace/x", "pfad": "y"})
        self.assertEqual((self.eingang / "icon.png").read_bytes(), png())

    def test_roots_must_be_safe_places(self):
        (Path(self.heim.name) / "Library" / "x").mkdir(parents=True)
        (Path(self.heim.name) / ".ssh").mkdir()
        for pfad in ("/etc", "~", "~/Library/x", "~/.ssh", "/tmp"):
            with self.assertRaises(dateien.Pfadfehler, msg=pfad):
                dateien.wurzel_pruefen(pfad)

    def test_k_the_inbound_folder_is_read_only(self):
        wurzel = dateien.Wurzel(self.eingang, schreibbar=False, name="Asset-/Eingabeordner")
        with self.assertRaises(PermissionError):
            wurzel.schreiben("neu.txt", b"x")
        with self.assertRaises(PermissionError):
            wurzel.loeschen("icon.png")
        with self.assertRaises(PermissionError):
            dateien.ausfuehren({"eingaben": wurzel}, "inbound.write", {"pfad": "x", "daten": b"x"})
        with self.assertRaises(ValueError):
            dateien.ausfuehren({"eingaben": wurzel}, "inbound.read", {"pfad": "icon.png", "mehr": 1})
        self.assertEqual(dateien.ausfuehren({"eingaben": wurzel}, "inbound.read", {"pfad": "icon.png"}), png())
        self.assertTrue((self.eingang / "icon.png").exists())

    def test_14_both_roots_stay_strictly_separate(self):
        for eingang, werkstatt in ((self.eingang, self.eingang), (self.eingang, self.eingang / "projekte"),
                                   (self.werkstatt / "eingaben", self.werkstatt)):
            with self.assertRaises(HTTPException) as fehler:
                asyncio.run(self.api.einstellungen_aendern(FakeRequest(), {
                    "eingaben": {"aktiv": True, "pfad": str(eingang)},
                    "workspace": {"aktiv": True, "pfad": str(werkstatt)}}))
            self.assertEqual(fehler.exception.status_code, 422)
            self.assertIn("getrennte Ordner", fehler.exception.detail)
        gut = self.einstellen(workspace_an=True)
        self.assertTrue(gut["eingaben"]["gueltig"] and gut["workspace"]["gueltig"])
        self.assertTrue(self.werkstatt.is_dir())                          # beim Einschalten angelegt

    def test_generated_apps_get_no_file_capability(self):
        laufzeit = (ROOT / "app" / "joshi" / "laufzeit.js").read_text(encoding="utf-8")
        self.assertNotIn("workspace", laufzeit)
        self.assertNotIn("inbound", laufzeit)
        self.assertIn('window.JOSHI = { version: 1, formate: ERLAUBT.slice(), export: exportieren }', laufzeit)

    def test_the_settings_are_persistent_per_user(self):
        self.einstellen(workspace_an=True)
        gespeichert = speicher.einstellungen(self.user)
        self.assertTrue(gespeichert["eingaben"]["aktiv"])
        self.assertTrue(gespeichert["workspace"]["aktiv"])
        self.assertTrue(gespeichert["workspace"]["pfad"].startswith("~/"))

    def test_mobile_uploads_can_reach_both_roots(self):
        self.einstellen(workspace_an=True)
        asset = UploadFile(filename="iPhone/Notiz.txt", file=io.BytesIO(b"vom iPhone"))
        asset.size = len(b"vom iPhone")
        antwort = asyncio.run(self.api.ordner_importieren(FakeRequest(), "eingaben", [asset]))
        self.assertTrue(antwort["ok"])
        self.assertEqual((self.eingang / "notiz.txt").read_bytes(), b"vom iPhone")

        projektdatei = UploadFile(filename="iPhone/README.md", file=io.BytesIO(b"Workspace"))
        projektdatei.size = len(b"Workspace")
        antwort = asyncio.run(self.api.ordner_importieren(FakeRequest(), "workspace", [projektdatei]))
        self.assertTrue(antwort["ok"])
        self.assertEqual((self.werkstatt / "iphone" / "readme.md").read_bytes(), b"Workspace")


class BedarfTests(unittest.TestCase):
    """Die Entscheidung folgt der realen Struktur, nicht der Zahl der Tokens."""

    def auswahl(self, **arten: int) -> list[eingaben.Auswahl]:
        ergebnis = []
        for art, anzahl in arten.items():
            for nummer in range(anzahl):
                name = f"d{nummer}." + {"bild": "png", "daten": "csv", "dokument": "pdf", "medien": "mp4"}[art]
                datei = dateien.Datei(name, art, 50_000, 0.0, Path(name))
                ergebnis.append(eingaben.Auswahl(datei, eingaben.rolle_bestimmen(datei, ""), "test"))
        return ergebnis

    def test_single_file_first(self):
        for text, auswahl in (("Baue einen BMI-Rechner", []), ("Kundendashboard aus der CSV mit Logo",
                                                               self.auswahl(bild=1, daten=1)),
                              ("Kleiner Produktkatalog", self.auswahl(bild=1, daten=1, dokument=1))):
            self.assertFalse(projekt.bedarf(text, auswahl).noetig, text)

    def test_workspace_only_when_necessary(self):
        self.assertTrue(projekt.bedarf("Katalog", self.auswahl(bild=14)).noetig)
        self.assertTrue(projekt.bedarf("Galerie", self.auswahl(medien=1)).noetig)
        self.assertTrue(projekt.bedarf("Erstelle daraus eine größere mehrteilige Anwendung.",
                                       self.auswahl(bild=4, daten=2)).noetig)
        self.assertTrue(projekt.bedarf("Jetzt 2.000 Produktbilder, CSV-Import und mehrere Module", []).noetig)
        self.assertTrue(projekt.bedarf("Mach die Farben freundlicher", [], bestehend_zeichen=0).noetig is False)


if __name__ == "__main__":
    unittest.main()
