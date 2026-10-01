# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Fall „Schichtplaner → Pflegedienst“ (29.09.2026).

- „Versuch es erneut und nutzt den workspace“ wurde zu zwei unerfüllbaren
  Kriterien („Vorgang wird erneut ausgeführt“, „Anwendung zeigt den Workspace“).
- Die Bedienprobe füllte den Statusfilter mit einem Testwert, alle Touren
  verschwanden, „Umplanen“ und „Maps-Link kopieren“ wurden nie geklickt.
- „Farben Rot, Gelb, Grün“ und „Vista-Glas-Optik“ waren umgesetzt, aber nicht messbar.
- „Maps-Link kopieren“ galt über „PDF exportieren“ als belegt.
"""
from __future__ import annotations

import asyncio
import unittest

from app.joshi import abnahme, aenderung, pruefer, renderer

VERTRAG = {"kriterien": [
    {"id": "routen_umplanung", "beschreibung": "Es gibt eine Funktion, mit der eine Route umgeplant werden kann.",
     "stichworte": ["Route", "umplanen"], "pflicht": True, "nachweis": "bedienung", "aktion": "neu"},
    {"id": "apple_maps_link", "beschreibung": "Zu einer Route wird ein Apple-Maps-Link erzeugt, der kopiert werden kann.",
     "stichworte": ["Apple Maps", "Link", "kopieren"], "pflicht": True, "nachweis": "bedienung", "aktion": "export"},
    {"id": "farben", "beschreibung": "Das Design der Anwendung verwendet die Farben Rot, Gelb und Grün.",
     "stichworte": ["Rot", "Gelb", "Grün"], "pflicht": True, "nachweis": "gestaltung"},
    {"id": "glas", "beschreibung": "Die Oberfläche zeigt eine moderne Glas-Optik im Vista-Stil.",
     "stichworte": ["Glas", "Vista"], "pflicht": True, "nachweis": "gestaltung"},
]}

TOUREN = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Touren</title><style>
body{margin:0;font:16px system-ui;background:linear-gradient(#fde2e2,#e2fde8)}
.karte{margin:10px;padding:12px;border-radius:14px;background:rgba(255,255,255,.55);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);box-shadow:0 4px 18px rgba(0,0,0,.12)}
.rot{background:#d32f2f;color:#fff}.gelb{background:#f9c80e}.gruen{background:#2e7d32;color:#fff}
[hidden]{display:none!important}
</style></head><body>
<section class="karte"><label for="status">Status</label>
<select id="status"><option value="alle">Alle</option><option value="storniert">Storniert</option></select>
<button type="button" class="pdf" id="pdf">PDF exportieren</button></section>
<section class="karte" id="liste"></section>
<section class="karte"><span class="rot">Kritisch</span> <span class="gelb">Knapp</span> <span class="gruen">Besetzt</span></section>
<p id="meldung" class="karte"></p>
<script>
const touren = [{id: 1, name: "Frau Meier", status: "offen"}, {id: 2, name: "Herr Kaya", status: "offen"},
                {id: 3, name: "Frau Lenz", status: "offen"}];
function zeichnen() {
  const filter = document.getElementById("status").value;
  const liste = document.getElementById("liste");
  liste.innerHTML = "";
  touren.filter((t) => filter === "alle" || t.status === filter).forEach((t, i) => {
    const d = document.createElement("div");
    d.className = "karte " + ["rot", "gelb", "gruen"][i % 3];
    d.innerHTML = "<b>" + t.name + "</b> <button type='button' class='umplanen'>Umplanen</button>"
      + " <button type='button' class='maps'>Maps-Link kopieren</button>";
    d.querySelector(".umplanen").onclick = () => { document.getElementById("meldung").textContent = "Route von " + t.name + " umgeplant auf Tour 2"; };
    d.querySelector(".maps").onclick = () => { document.getElementById("meldung").textContent = "Link kopiert: https://maps.apple.com/?daddr=" + t.id; };
    liste.appendChild(d);
  });
  const hinweis = document.createElement("div"); hinweis.className = "karte gelb"; hinweis.textContent = "Hinweis";
  liste.appendChild(hinweis);
}
document.getElementById("status").addEventListener("change", zeichnen);
document.getElementById("pdf").onclick = () => { document.getElementById("meldung").textContent = "PDF wurde erstellt"; };
zeichnen();
</script></body></html>"""


class SteuerungTests(unittest.TestCase):
    def test_workspace_instruction_is_no_requirement(self):
        absicht = aenderung.absicht_erkennen("Versuch es erneut und nutzt den workspace", True)
        self.assertEqual((absicht.art, absicht.rest), ("wiederholen", ""))
        self.assertIn("workspace", absicht.steuerung)
        gemischt = aenderung.absicht_erkennen("mach die Karten grün und nutz den projektordner", True)
        self.assertEqual(gemischt.art, "ergaenzen")
        self.assertEqual(gemischt.rest, "mach die Karten grün")
        self.assertEqual(gemischt.steuerung, {"workspace"})

    def test_an_old_line_with_instruction_criteria_heals_itself(self):
        linie = {"vertrag": {"kriterien": [
            {"id": "farben", "beschreibung": "Rot, Gelb, Grün", "herkunft": "root"},
            {"id": "erneuter_versuch", "beschreibung": "Der Vorgang wird erneut ausgeführt", "herkunft": "ergaenzung_1"},
            {"id": "workspace_nutzung", "beschreibung": "Die Anwendung zeigt den Workspace", "herkunft": "ergaenzung_1"}]},
            "ergaenzungen": [{"text": "Versuch es erneut und nutzt den workspace", "job": "j"}]}
        vertrag, korrekturen = aenderung.vertrag_bereinigen(linie)
        self.assertEqual([k["id"] for k in aenderung.aktiver_vertrag(vertrag)["kriterien"]], ["farben"])
        self.assertTrue(korrekturen)
        self.assertEqual(linie["ergaenzungen"][0]["steuerung"], ["workspace"])
        self.assertNotIn("workspace", aenderung.gesamtwunsch({"wunsch": "Pflegedienst", **linie, "vertrag": vertrag}))


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class EchteTourenTests(unittest.TestCase):
    def auswerten(self, html: str) -> tuple[pruefer.Pruefbericht, dict[str, abnahme.Ergebnis]]:
        async def los():
            bericht = await pruefer.pruefen(html, fokus=["route", "umplanen", "maps", "link"])
            aktionen, _ = await pruefer.szenarien_ausfuehren(html, aktionen=abnahme.benoetigte_proben(VERTRAG))
            return bericht, aktionen
        bericht, aktionen = asyncio.run(los())
        beweise = abnahme.beweise_sammeln(bericht.gliederung, bericht.interaktion, aktionen=aktionen, mobil=bericht.mobil)
        return bericht, {e.id: e for e in abnahme.deterministisch_pruefen(VERTRAG, beweise)}

    def test_a_filter_that_empties_the_list_is_reset_before_clicking(self):
        bericht, ergebnisse = self.auswerten(TOUREN)
        geklickt = {k["knopf"] for k in bericht.interaktion["klicks"]}
        self.assertIn("status", bericht.interaktion.get("zurueckgesetzt") or [])
        self.assertIn("Umplanen", geklickt)
        self.assertEqual(ergebnisse["routen_umplanung"].status, "PASS", ergebnisse["routen_umplanung"].begruendung)
        self.assertEqual(ergebnisse["apple_maps_link"].status, "PASS", ergebnisse["apple_maps_link"].begruendung)
        self.assertIn("Maps-Link", ergebnisse["apple_maps_link"].begruendung)

    def test_colors_and_glass_are_measured(self):
        _, ergebnisse = self.auswerten(TOUREN)
        self.assertEqual(ergebnisse["farben"].status, "PASS", ergebnisse["farben"].begruendung)
        self.assertEqual(ergebnisse["glas"].status, "PASS", ergebnisse["glas"].begruendung)
        grau = TOUREN.replace("#d32f2f", "#777").replace("#f9c80e", "#999").replace("#2e7d32", "#555") \
            .replace("backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);", "") \
            .replace("linear-gradient(#fde2e2,#e2fde8)", "#eee")
        _, schlicht = self.auswerten(grau)
        self.assertEqual(schlicht["farben"].status, "FAIL")
        self.assertEqual(schlicht["glas"].status, "FAIL")

    def test_a_pdf_export_does_not_prove_a_copyable_link(self):
        ohne_link = TOUREN.replace(" <button type='button' class='maps'>Maps-Link kopieren</button>", "")
        _, ergebnisse = self.auswerten(ohne_link)
        self.assertNotEqual(ergebnisse["apple_maps_link"].status, "PASS", ergebnisse["apple_maps_link"].begruendung)


if __name__ == "__main__":
    unittest.main()


class AblaufTests(unittest.TestCase):
    """Die Schritte bleiben in der fertigen Antwort sichtbar."""

    def test_stages_and_phases_keep_their_final_state(self):
        from app.joshi.api import ablauf
        ereignisse = [
            {"type": "plan", "schritte": [{"id": "erstellen", "text": "Änderung umsetzen"}, {"id": "pruefen", "text": "Prüfen"}]},
            {"type": "schritt", "schritt": "erstellen", "zustand": "fertig", "text": "3 Stellen geändert"},
            {"type": "stufen", "stufen": [{"nummer": 1, "titel": "Farben", "zustand": "planned"},
                                          {"nummer": 2, "titel": "Routen", "zustand": "planned"}]},
            {"type": "stufe", "nummer": 1, "zustand": "passed"},
            {"type": "stufe", "nummer": 2, "zustand": "failed", "grund": "Patch passte nicht"},
        ]
        daten = ablauf(ereignisse)
        self.assertEqual([(s["titel"], s["zustand"]) for s in daten["stufen"]], [("Farben", "passed"), ("Routen", "failed")])
        self.assertEqual(daten["stufen"][1]["grund"], "Patch passte nicht")
        self.assertEqual([(s["id"], s["zustand"]) for s in daten["schritte"]], [("erstellen", "fertig"), ("pruefen", "offen")])


class WiederholungsTests(unittest.TestCase):
    """29.09.2026: „verssuch es erneut und …“ wurde zum Kriterium „Erneut-Versuchen-Knopf“."""

    def test_retry_phrase_never_becomes_a_requirement(self):
        absicht = aenderung.absicht_erkennen("verssuch es erneut und beziehe auch Daten zu RAM und Netzteile ein.", True)
        self.assertEqual(absicht.art, "wiederholen")                      # weiterer Versuch …
        self.assertEqual(absicht.rest, "beziehe auch Daten zu RAM und Netzteile ein")   # … mit Zusatz, ohne Floskel

    def test_step_reference_and_duplicates_add_nothing(self):
        plan = {"stufen": [{"titel": f"S{n}", "kriterien": []} for n in range(1, 8)]}
        self.assertEqual(aenderung.absicht_erkennen("korrigiere nur Punkt 6 noch responsive", True,
                                                    {"kriterien": [{"id": "x", "beschreibung": "x"}]}, plan).art,
                         "wiederholen")
        linie = {"plan": plan, "vertrag": {"kriterien": [
            {"id": "ram", "beschreibung": "RAM-Daten", "herkunft": "ergaenzung_1"},
            {"id": "erneut_versuchen", "beschreibung": "Knopf, der den Vorgang erneut startet", "herkunft": "ergaenzung_1"},
            {"id": "p6", "beschreibung": "Punkt 6 mobil", "herkunft": "ergaenzung_2"}]},
            "ergaenzungen": [{"text": "versuch es erneut und nimm RAM-Daten dazu"}, {"text": "korrigiere nur Punkt 6"}]}
        vertrag, _ = aenderung.vertrag_bereinigen(linie)
        self.assertEqual([k["id"] for k in aenderung.aktiver_vertrag(vertrag)["kriterien"]], ["ram"])


class DesignRegelTests(unittest.TestCase):
    """30.09.2026: „neues Design mit den Feldern …“ soll bestehen, wenn es erfüllt ist — gemessen, nicht geraten."""

    KRITERIUM = {"id": "neues_design", "nachweis": "gestaltung", "pflicht": True, "stichworte": ["Design"],
                 "beschreibung": "Die Anwendung zeigt sich im neuen Design mit den vorhandenen Feldern Budget, "
                                 "Einsatzzweck, Zielauflösung und Profil wählen."}

    def urteil(self, felder: list[str], schatten: int) -> str:
        farben = {"blau": 8} if schatten else {}
        beweise = abnahme.beweise_sammeln({"felder": [{"label": f} for f in felder], "knoepfe": [], "markdown": " ".join(felder),
                                           "gestaltung": {"farben": farben, "schatten": schatten, "glas": 0}}, {})
        return abnahme.deterministisch_pruefen({"kriterien": [self.KRITERIUM]}, beweise)[0].status

    def test_designed_page_with_the_fields_passes_even_if_renamed(self):
        self.assertEqual(self.urteil(["Budget", "Hauptnutzung", "Zielauflösung", "Profil wählen"], 6), "PASS")

    def test_missing_fields_or_plain_page_do_not_pass(self):
        self.assertEqual(self.urteil(["Budget"], 6), "FAIL")
        self.assertNotEqual(self.urteil(["Budget", "Einsatzzweck", "Zielauflösung", "Profil wählen"], 0), "PASS")
