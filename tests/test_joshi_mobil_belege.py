# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Der Fitness-Fall vom 27.09.2026: warum JOSHI über den ersten Versuch nicht hinauskam.

Versuch 1: Ein Änderungsblock enthielt zwei `=======`; der ERSETZEN-Teil samt
Trennmarke landete im JavaScript („Unexpected token '==='“). Die Reparaturen
bekamen nur „Zeile 754“ genannt und fanden die Stelle nicht.

Versuch 2: Die Anwendung war technisch sauber und hatte das Verlangte fast
vollständig umgesetzt — die Abnahme sah es nur nicht: Info-Knöpfe hießen „i“,
aufgeklappte Beschreibungen wurden nicht erfasst, Aufklapper nicht geklickt,
Handybreite nicht gemessen, Verschieben per Touch nicht geprüft. Drei Runden
mit exakt PASS 2 / FAIL 6.

Die Tests hier bilden beides nach; die WebKit-Tests laufen im echten Renderer.
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.joshi import abnahme, pruefer, renderer
from app.joshi.html_werk import bloecke_einzeln, marken_zeilen, statische_befunde

VERTRAG = {"zusammenfassung": "Mobil first, Info-Knöpfe, eigene Übungen", "kriterien": [
    {"id": "weisser_kasten_mobil", "beschreibung": "In der mobilen Ansicht ist oben links kein weißer Kasten mehr zu sehen",
     "stichworte": ["mobile Ansicht", "kein weißer Kasten"], "pflicht": True, "nachweis": "gestaltung"},
    {"id": "mobil_first", "beschreibung": "In schmaler Ansicht stehen die Karten untereinander in einer Spalte und füllen die Breite aus",
     "stichworte": ["Karten", "untereinander"], "pflicht": True, "nachweis": "gestaltung"},
    # So stand es im echten Vertrag: Aktion „sonstiges“ — JOSHI muss „ziehen“ daraus machen.
    {"id": "karten_schieben_mobil", "beschreibung": "In der mobilen Ansicht lassen sich die Karten bewegen",
     "stichworte": ["Karten", "schieben", "mobil"], "pflicht": True, "nachweis": "bedienung", "aktion": "sonstiges"},
    {"id": "desktop_ausklappbar", "beschreibung": "In großer Ansicht lassen sich die Bereiche per Klick auf- und zuklappen",
     "stichworte": ["ausklappen", "Bereich"], "pflicht": True, "nachweis": "bedienung", "aktion": "umschalten"},
    {"id": "eigene_uebung", "beschreibung": "Über „Übung anlegen“ kann der Nutzer eine eigene Übung mit Namen eintragen",
     "stichworte": ["Übung anlegen", "eigene Übung", "Name"], "pflicht": True, "nachweis": "bedienung", "aktion": "speichern"},
    {"id": "info_aufklappen", "beschreibung": "Ein Klick auf den Info-Knopf klappt die Beschreibung auf und wieder zu",
     "stichworte": ["Info", "aufklappen", "Beschreibung"], "pflicht": True, "nachweis": "bedienung", "aktion": "umschalten"},
    {"id": "beschreibung", "beschreibung": "Die Beschreibung verlangt langsame, ruhige, kontrollierte Ausführung",
     "stichworte": ["langsam", "ruhig", "kontrolliert"], "pflicht": True, "nachweis": "inhalt"},
]}

STIL = """<style>
body{margin:0;background:#0b0b0d;color:#eee;font:16px system-ui}
section{margin:12px;padding:12px;border:1px solid #333;border-radius:12px;background:#15151a}
.tage{display:grid;grid-template-columns:1fr;gap:10px}
@media (min-width:800px){.tage{grid-template-columns:repeat(3,1fr)}}
.tag{min-height:80px;padding:8px;border:1px solid #333;border-radius:10px}
.chip{display:flex;gap:6px;align-items:center;padding:6px;margin:4px 0;background:#222;border-radius:8px;touch-action:none}
</style>"""

# Wie v1: Karten nur per HTML5-Drag&Drop, keine Aufklapper, keine eigenen Übungen.
NUR_HTML5 = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Plan</title>{STIL}</head><body>
<section><h2>Wochenplan</h2><div class="tage">
<div class="tag" data-tag="mo"><h3>Montag</h3><div class="chip" draggable="true" data-id="a">Seitheben</div></div>
<div class="tag" data-tag="di"><h3>Dienstag</h3></div>
<div class="tag" data-tag="mi"><h3>Mittwoch</h3><div class="chip" draggable="true" data-id="b">Klimmzüge</div></div>
</div></section>
<section><h2>Übungen</h2><p>Latzug, Brustpresse, Liegestütze</p><button type="button" id="hinzu">Übung hinzufügen</button></section>
<script>
let gezogen = null;
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("dragstart", () => {{ gezogen = c; }}));
document.querySelectorAll(".tag").forEach((t) => {{
  t.addEventListener("dragover", (e) => e.preventDefault());
  t.addEventListener("drop", (e) => {{ e.preventDefault(); if (gezogen) t.appendChild(gezogen); }});
}});
document.getElementById("hinzu").onclick = () => localStorage.setItem("plan", String(Date.now()));
</script></body></html>"""

# Wie v3, aber mit echtem Touch-Ziehen: Pointer-Events, Aufklapper, Info-Knöpfe „i“, eigene Übungen.
MOBIL_FERTIG = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Plan</title>{STIL}</head><body>
<section><h2><button type="button" class="auf" aria-expanded="true" aria-controls="plan">Wochenplan ▾</button></h2>
<div id="plan" class="tage">
<div class="tag"><h3>Montag</h3><div class="chip" data-drag>Seitheben
  <button type="button" class="info" aria-expanded="false" aria-label="Info zur Übung">i</button>
  <p class="text" hidden>Langsam und ruhig heben, kontrolliert absenken — nur kontrollierte Ausführung baut Kraft auf.</p></div></div>
<div class="tag"><h3>Dienstag</h3></div>
<div class="tag"><h3>Mittwoch</h3><div class="chip" data-drag>Klimmzüge</div></div>
</div></section>
<section><h2>Eigene Übung</h2><label for="name">Name der Übung</label><input id="name" value="Face Pulls">
<button type="button" id="anlegen">Übung anlegen</button><ul id="liste"></ul></section>
<script>
document.querySelectorAll(".auf").forEach((k) => k.addEventListener("click", () => {{
  const ziel = document.getElementById(k.getAttribute("aria-controls"));
  const offen = k.getAttribute("aria-expanded") === "true";
  k.setAttribute("aria-expanded", String(!offen)); ziel.hidden = offen;
}}));
document.querySelectorAll(".info").forEach((k) => k.addEventListener("click", (e) => {{
  e.stopPropagation();
  const text = k.nextElementSibling; const offen = k.getAttribute("aria-expanded") === "true";
  k.setAttribute("aria-expanded", String(!offen)); text.hidden = offen;
}}));
let zug = null;
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("pointerdown", (e) => {{
  if (e.target.closest("button")) return; zug = c;
}}));
document.addEventListener("pointerup", (e) => {{
  if (!zug) return;
  const ziel = document.elementFromPoint(e.clientX, e.clientY);
  const tag = ziel && ziel.closest(".tag");
  if (tag && !tag.contains(zug)) tag.appendChild(zug);
  zug = null;
}});
document.getElementById("anlegen").onclick = () => {{
  const name = document.getElementById("name").value || "Übung";
  const li = document.createElement("li"); li.textContent = "Eigene Übung „" + name + "“ angelegt";
  document.getElementById("liste").appendChild(li);
  localStorage.setItem("eigene", name);
}};
</script></body></html>"""

# Wie die befördert Fassung im Stresstest: Griff „⠿“ mit Pointer-Capture, Listener nur am Griff.
MIT_GRIFF = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Plan</title>{STIL}</head><body>
<section><h2>Wochenplan</h2><div class="tage">
<div class="tag"><h3>Montag</h3><div class="chips"><div class="chip"><span class="chip-grip" data-grip="1">⠿</span> Seitheben</div></div></div>
<div class="tag"><h3>Dienstag</h3><div class="chips"></div></div>
<div class="tag"><h3>Mittwoch</h3><div class="chips"><div class="chip"><span class="chip-grip" data-grip="1">⠿</span> Klimmzüge</div></div></div>
</div></section>
<script>
document.querySelectorAll(".chip-grip").forEach((griff) => griff.addEventListener("pointerdown", (ev) => {{
  ev.preventDefault();
  const karte = griff.closest(".chip"); let ueber = null;
  try {{ griff.setPointerCapture(ev.pointerId); }} catch (e) {{}}
  const weiter = (e) => {{ const el = document.elementFromPoint(e.clientX, e.clientY); ueber = el && el.closest(".tag"); }};
  const ende = () => {{
    griff.removeEventListener("pointermove", weiter); griff.removeEventListener("pointerup", ende);
    if (ueber && !ueber.contains(karte)) ueber.querySelector(".chips").appendChild(karte);
  }};
  griff.addEventListener("pointermove", weiter); griff.addEventListener("pointerup", ende);
}}));
</script></body></html>"""

# Nur „antippen, dann Ziel antippen“ — ohne Ziehen mit dem Finger.
NUR_ANTIPPEN = NUR_HTML5.replace('document.getElementById("hinzu")', """let gewaehlt = null;
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", (e) => {{ e.stopPropagation(); gewaehlt = c; }}));
document.querySelectorAll(".tag").forEach((t) => t.addEventListener("click", () => {{ if (gewaehlt) t.appendChild(gewaehlt); gewaehlt = null; }}));
document.getElementById("hinzu")""".replace("{{", "{").replace("}}", "}"), 1)

# Wie Zwischenstand 5 im Stresstest: Die Karten samt Info-Knöpfen stecken in einem
# eingeklappten Bereich „Karten ausklappen“.
EINGEKLAPPT = MOBIL_FERTIG.replace(
    'aria-expanded="true" aria-controls="plan">Wochenplan ▾</button></h2>\n<div id="plan" class="tage">',
    'aria-expanded="false" aria-controls="plan">Karten ausklappen</button></h2>\n<div id="plan" class="tage" hidden>',
    1).replace("</style>", "[hidden]{display:none!important}</style>", 1)

WEISSER_KASTEN = MOBIL_FERTIG.replace("<section><h2><button",
                                      '<div class="logo" style="width:120px;height:90px;background:#fff"></div><section><h2><button', 1)


class TrennmarkenTests(unittest.TestCase):
    def test_a_block_with_a_marker_is_never_applied(self):
        dokument = "<script>\n  'use strict';\n  start();\n</script>"
        kaputt = ("  'use strict';", "  'use strict';\n  neu();\n=======\n  'use strict';\n  alt();")
        heil = ("  start();", "  starten();")
        neu, offen = bloecke_einzeln(dokument, [kaputt, heil])
        self.assertNotIn("=======", neu)
        self.assertIn("starten();", neu)                       # die heilen Blöcke gelten weiter
        self.assertEqual(offen, [kaputt])                       # der kaputte geht in den Nachtrag

    def test_leftover_markers_are_a_static_error_with_the_spot(self):
        dokument = "<!DOCTYPE html><html><body><script>\nlet a = 1;\n=======\nlet b = 2;\n</script></body></html>"
        self.assertEqual(marken_zeilen(dokument), [3])
        befund = [b for b in statische_befunde(dokument) if "Änderungsmarkierungen" in b.text][0]
        self.assertEqual(befund.art, "fehler")
        self.assertIn(">>    3| =======", befund.technik)
        # Normale Kommentarlinien sind keine Marken.
        self.assertEqual(marken_zeilen("/* ======= */\n<!-- ======= Titel ======= -->"), [])


class BelegRegelnTests(unittest.TestCase):
    """Die Abnahme-Regeln ohne Browser."""

    def beweise(self, klicks: list[dict[str, Any]], **weitere: Any) -> dict[str, Any]:
        return abnahme.beweise_sammeln({"knoepfe": [k["knopf"] for k in klicks], "ueberschriften": ["Plan"],
                                        "markdown": weitere.pop("text", "Wochenplan"), "anzahl": {}},
                                       {"klicks": klicks}, **weitere)

    def urteil(self, kriterium_id: str, beweise: dict[str, Any]) -> abnahme.Ergebnis:
        vertrag = {"kriterien": [k for k in VERTRAG["kriterien"] if k["id"] == kriterium_id]}
        return abnahme.deterministisch_pruefen(vertrag, beweise)[0]

    def test_an_old_other_action_becomes_a_touch_drag_probe(self):
        self.assertIn("ziehen_touch", abnahme.benoetigte_proben(VERTRAG))

    def test_a_probe_on_another_button_proves_nothing(self):
        beweise = self.beweise([{"knopf": "Übung anlegen", "effekte": ["text_changed"], "neuerText": "angelegt"}],
                               aktionen=[{"aktion": "speichern", "knopf": "Als PDF sichern", "ergebnis": "bestanden",
                                          "belege": ["export_requested"]}])
        ergebnis = self.urteil("eigene_uebung", beweise)
        self.assertNotIn("PDF", ergebnis.begruendung)
        self.assertNotEqual(ergebnis.beleg, "aktion:speichern")

    def test_a_named_button_needs_half_the_keywords(self):
        nur_knopf = self.beweise([{"knopf": "Übung anlegen", "effekte": ["local_storage_changed", "dom_added"],
                                   "neuerText": "„Seitheben“ zu Dienstag hinzugefügt"}])
        self.assertEqual(self.urteil("eigene_uebung", nur_knopf).status, "NOT_PROVEN")
        belegt = self.beweise([{"knopf": "Übung anlegen", "effekte": ["local_storage_changed", "dom_added"],
                                "neuerText": "Eigene Übung „Face Pulls“ angelegt"}], text="Name der Übung")
        self.assertEqual(self.urteil("eigene_uebung", belegt).status, "PASS")

    def test_a_named_toggle_must_be_that_toggle_and_close_again(self):
        fremd = self.beweise([{"knopf": "Steuerung ▾", "effekte": ["element_hidden", "toggled"], "aufklapper": True},
                              {"knopf": "Info zur Übung (i)", "effekte": ["text_changed"], "aufklapper": True}])
        ergebnis = self.urteil("info_aufklappen", fremd)
        self.assertEqual(ergebnis.status, "NOT_PROVEN")        # Steuerung zählt nicht, Info klappte nicht zu
        richtig = self.beweise([{"knopf": "Info zur Übung (i)", "effekte": ["element_shown", "text_changed", "toggled"],
                                 "aufklapper": True, "neuerText": "Langsam und ruhig heben"}])
        self.assertEqual(self.urteil("info_aufklappen", richtig).status, "PASS")
        # „Bereiche auf- und zuklappen“ nennt keinen Knopf: jeder echte Aufklapper belegt es.
        self.assertEqual(self.urteil("desktop_ausklappbar", fremd).status, "PASS")

    def test_a_generic_toggle_does_not_prove_a_named_info_button(self):
        # Zwischenstand 5: Kein Info-Knopf geklickt, nur „Karten ausklappen“ — früher ein falsches PASS.
        nur_karten = self.beweise([{"knopf": "Karten ausklappen", "effekte": ["element_shown", "text_changed", "toggled"],
                                    "aufklapper": True}])
        ergebnis = self.urteil("info_aufklappen", nur_karten)
        self.assertEqual(ergebnis.status, "NOT_PROVEN")
        self.assertNotIn("Karten ausklappen", ergebnis.begruendung)
        self.assertEqual(abnahme._knopfnamen(VERTRAG["kriterien"][5]), ["Info"])
        self.assertEqual(abnahme._knopfnamen(VERTRAG["kriterien"][4]), [])    # „Über „Übung anlegen““ nennt keinen Typ

    def test_mobile_layout_is_judged_from_the_390px_measurement(self):
        gut = self.beweise([], mobil={"breite": 390, "spalten": 1, "karten": 7, "kartenbreite": 92,
                                      "ueberlauf": False, "leereFlaechen": []})
        self.assertEqual(self.urteil("mobil_first", gut).status, "PASS")
        self.assertEqual(self.urteil("weisser_kasten_mobil", gut).status, "PASS")
        schlecht = self.beweise([], mobil={"breite": 390, "spalten": 3, "karten": 7, "kartenbreite": 30,
                                           "ueberlauf": True, "leereFlaechen": [
                                               {"tag": "div", "klasse": "logo", "x": 0, "y": 0, "breite": 120,
                                                "hoehe": 90, "farbe": "rgb(255, 255, 255)"}]})
        self.assertEqual(self.urteil("mobil_first", schlecht).status, "FAIL")
        kasten = self.urteil("weisser_kasten_mobil", schlecht)
        self.assertEqual(kasten.status, "FAIL")
        self.assertIn("120×90 px bei x=0, y=0", kasten.begruendung)   # die Reparatur weiß, wo


@unittest.skipUnless(renderer.status().get("verfuegbar"), "WebKit-Renderer auf diesem Rechner nicht übersetzt")
class EchteMobilBelegeTests(unittest.TestCase):
    """Im echten WebKit: dieselben Belege, die im Fitness-Fall fehlten."""

    def auswerten(self, html: str) -> tuple[pruefer.Pruefbericht, list[dict[str, Any]], dict[str, abnahme.Ergebnis]]:
        async def los():
            bericht = await pruefer.pruefen(html, fokus=["info", "anlegen", "karten"])
            aktionen, _ = await pruefer.szenarien_ausfuehren(html, aktionen=abnahme.benoetigte_proben(VERTRAG))
            return bericht, aktionen
        bericht, aktionen = asyncio.run(los())
        beweise = abnahme.beweise_sammeln(bericht.gliederung, bericht.interaktion, aktionen=aktionen,
                                          mobil=bericht.mobil)
        return bericht, aktionen, {e.id: e for e in abnahme.deterministisch_pruefen(VERTRAG, beweise)}

    def test_html5_only_drag_fails_on_touch_with_a_useful_hint(self):
        bericht, aktionen, ergebnisse = self.auswerten(NUR_HTML5)
        self.assertTrue(bericht.ok, bericht.befunde)
        ziehen = next(a for a in aktionen if a["aktion"] == "ziehen_touch")
        self.assertEqual(ziehen["ergebnis"], "gescheitert")
        self.assertIn("Pointer-Events", ziehen["grund"])
        self.assertEqual(ergebnisse["karten_schieben_mobil"].status, "FAIL")
        self.assertEqual(ergebnisse["info_aufklappen"].status, "NOT_PROVEN")
        self.assertEqual(ergebnisse["beschreibung"].status, "NOT_PROVEN")

    def test_the_finished_mobile_version_is_fully_proven(self):
        bericht, aktionen, ergebnisse = self.auswerten(MOBIL_FERTIG)
        self.assertTrue(bericht.ok, bericht.befunde)
        self.assertEqual(bericht.mobil["spalten"], 1)
        self.assertFalse(bericht.mobil["ueberlauf"])
        info = [k for k in bericht.interaktion["klicks"] if k["knopf"].startswith("Info zur Übung")]
        self.assertTrue(info and info[0]["aufklapper"] and info[0]["zurueck"])
        self.assertIn("kontrolliert", info[0]["neuerText"])      # aufgeklappter Text ist Beleg
        ziehen = next(a for a in aktionen if a["aktion"] == "ziehen_touch")
        self.assertEqual(ziehen["ergebnis"], "bestanden", ziehen)
        self.assertIn("touch_drag", ziehen["belege"])
        self.assertEqual({i: e.status for i, e in ergebnisse.items()}, {i: "PASS" for i in ergebnisse},
                         {i: e.begruendung for i, e in ergebnisse.items()})

    def test_a_grip_with_pointer_capture_is_dragged_like_a_finger(self):
        _, aktionen, ergebnisse = self.auswerten(MIT_GRIFF)
        ziehen = next(a for a in aktionen if a["aktion"] == "ziehen_touch")
        self.assertEqual(ziehen["ergebnis"], "bestanden", ziehen)
        self.assertIn("touch_drag", ziehen["belege"])
        self.assertEqual(ergebnisse["karten_schieben_mobil"].status, "PASS")

    def test_tapping_alone_does_not_prove_finger_dragging(self):
        _, aktionen, ergebnisse = self.auswerten(NUR_ANTIPPEN)
        ziehen = next(a for a in aktionen if a["aktion"] == "ziehen_touch")
        self.assertIn("tap_move", ziehen["belege"])
        ergebnis = ergebnisse["karten_schieben_mobil"]
        self.assertEqual(ergebnis.status, "NOT_PROVEN")     # „schieben“ verlangt Ziehen mit dem Finger
        self.assertIn("Nur über Antippen", ergebnis.begruendung)

    def test_info_buttons_inside_a_collapsed_section_are_still_clicked(self):
        bericht, _, ergebnisse = self.auswerten(EINGEKLAPPT)
        klicks = {k["knopf"]: k for k in bericht.interaktion["klicks"]}
        self.assertIn("toggled", klicks["Karten ausklappen"]["effekte"])
        self.assertTrue(any(name.startswith("Info zur Übung") for name in klicks), list(klicks))
        self.assertEqual(ergebnisse["info_aufklappen"].status, "PASS", ergebnisse["info_aufklappen"].begruendung)
        self.assertIn("Info zur Übung", ergebnisse["info_aufklappen"].begruendung)
        self.assertEqual(ergebnisse["beschreibung"].status, "PASS", ergebnisse["beschreibung"].begruendung)

    def test_an_empty_white_box_is_found_in_the_mobile_width(self):
        bericht, _, ergebnisse = self.auswerten(WEISSER_KASTEN)
        flaeche = bericht.mobil["leereFlaechen"][0]
        self.assertEqual((flaeche["breite"], flaeche["hoehe"]), (120, 90))
        self.assertEqual(ergebnisse["weisser_kasten_mobil"].status, "FAIL")


if __name__ == "__main__":
    unittest.main()


try:
    from test_joshi import SpeicherTestfall
except ImportError:  # als Paket gestartet
    from tests.test_joshi import SpeicherTestfall


class DenkstromUndNeufassungTests(SpeicherTestfall):
    """Gemessen am 27.09.2026: 625.000 Zeichen Denkstrom für eine Neufassung von 62.000 Zeichen."""

    def test_endless_thinking_hits_its_own_budget(self):
        from app.joshi import grenzen
        waechter = grenzen.Waechter(62_495, bloecke=True, grenzen=grenzen.Grenzen())
        self.assertEqual(waechter.hart_denken, 187_485)
        weich = waechter.pruefen("", 90, denken=100_000)
        self.assertEqual((weich.art, weich.stufe), ("denken", "weich"))
        hart = waechter.pruefen("", 150, denken=190_000)
        self.assertEqual((hart.art, hart.stufe), ("denken", "hart"))
        # Wer schreibt, darf dabei auch denken — die Ausgabegrenze bleibt die globale.
        normal = grenzen.Waechter(62_495, bloecke=True, grenzen=grenzen.Grenzen())
        vielfalt = "".join(f"<p>Zeile {n}: Übung {n * 7 % 13}</p>\n" for n in range(900))
        self.assertIsNone(normal.pruefen(vielfalt, 30, denken=40_000))

    def test_a_large_markup_only_app_is_rejected_before_a_whole_file_request(self):
        from app.joshi import pipeline
        from app.joshi.jobs import Auftrag
        try:
            from test_joshi import GespielterZugang
        except ImportError:
            from tests.test_joshi import GespielterZugang
        gross = "<!DOCTYPE html><html><body><h1>Plan</h1>" + "<p>Zeile</p>\n" * 5000 + "</body></html>"
        class Zugang(GespielterZugang):
            async def strom(self, modell, nachrichten, *, temperatur, verbrauch):
                self.anfragen.append(nachrichten)

        zugang = Zugang([])
        lauf = pipeline.Lauf(Auftrag("j", "p", self.user), user_id=self.user, produkt={"id": "p", "titel": "T"}, art="aendern",
                             eingabe=pipeline.Eingabe(text="x"), modell="m", zugang=zugang)
        with self.assertRaises(pipeline.Umsetzungsfehler) as fall:
            asyncio.run(lauf.umsetzen(gross, lauf._nachrichten_fuer(gross, "x"), "t", wunsch="x"))
        self.assertIn("nicht sicher in bearbeitbare Projektdateien zerlegen", fall.exception.text)
        self.assertEqual(len(zugang.anfragen), 0)        # kein unsicherer Monster-Aufruf
