# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Der Prüfer: Nur er entscheidet, ob ein JOSHI-Produkt funktioniert.

Das Modell darf behaupten, was es will. Geprüft wird in drei Stufen:
1. statisch — ist es ein vollständiges, eigenständiges HTML-Dokument?
2. im Browser (WebKit) — lädt es, bleibt es fehlerfrei, ist es nicht leer?
3. Bedienprobe — Felder füllen, Knöpfe drücken: reagiert die Anwendung,
   ohne Fehler, ohne „NaN“? Dazu eine Handy-Breite für das Layout.

Arten von Befunden:
  fehler  – blockiert „bereit“ und löst eine Reparatur aus
  abnahme – der Auftrag ist nachweislich nicht umgesetzt; blockiert ebenfalls
  unbewiesen  – ein Pflichtkriterium ist nicht nachgewiesen (NOT_PROVEN);
            blockiert und wird repariert — unbewiesen ist nicht bestanden
  unbeweisbar – ein Pflichtkriterium kann die Testumgebung grundsätzlich nicht
            nachweisen (zweite Sitzung, Offline); blockiert, keine Reparatur
  luecke  – etwas Erwartetes fehlt; wird repariert, solange Versuche übrig
            sind, blockiert aber nicht
  warnung – wird angezeigt, blockiert nicht
  info    – nur für die technischen Details
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.joshi import renderer
from app.joshi.html_werk import Befund, code_ausschnitt, laufzeit_dokument, originalzeile, statische_befunde


# Was „bereit“ verhindert: technische Fehler, eine nachweislich nicht
# umgesetzte Anforderung — und eine, die nicht nachgewiesen ist.
BLOCKIEREND = {"fehler", "abnahme", "unbewiesen", "unbeweisbar"}
# Was eine Reparatur beheben kann. Unbeweisbares gehört nicht dazu.
REPARIERBAR = {"fehler", "abnahme", "unbewiesen", "luecke"}


@dataclass
class Pruefbericht:
    befunde: list[Befund]
    browser: bool
    gliederung: dict[str, Any] = field(default_factory=dict)
    interaktion: dict[str, Any] = field(default_factory=dict)
    dauer: float = 0.0
    abnahme: dict[str, Any] = field(default_factory=dict)
    exporte: list[dict[str, Any]] = field(default_factory=list)
    aktionen: list[dict[str, Any]] = field(default_factory=list)
    szenarien: list[dict[str, Any]] = field(default_factory=list)
    # Messung in Handybreite (390 px): Spalten, Überlauf, leere Kontrastflächen, Stil.
    mobil: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        # Eine statische Ersatzprüfung ist nützlich für Diagnose, beweist aber
        # nicht, dass die Anwendung in der vorgesehenen Runtime lädt. Ohne
        # WebKit darf daher niemals eine READY-Version entstehen.
        return self.browser and not any(b.art in BLOCKIEREND for b in self.befunde)

    def reparaturbedarf(self) -> list[Befund]:
        return [b for b in self.befunde if b.art in REPARIERBAR]

    def reparaturtext(self) -> str:
        zeilen = []
        for nummer, befund in enumerate(self.reparaturbedarf(), 1):
            zeilen.append(f"{nummer}. {befund.text}" + (f"\n   Technisch: {befund.technik}" if befund.technik else ""))
        return "\n".join(zeilen)

    def kurzfassung(self) -> str:
        fehler = [b for b in self.befunde if b.art in BLOCKIEREND]
        if fehler:
            return fehler[0].text
        if not self.browser:
            return "Statisch geprüft (Browserprüfung nicht verfügbar)."
        teile = ["Lädt fehlerfrei"]
        if self.interaktion.get("geklickt") or self.interaktion.get("gefuellt"):
            teile.append(
                f"Bedienprobe mit {self.interaktion.get('gefuellt', 0)} Eingaben und "
                f"{self.interaktion.get('geklickt', 0)} Klicks bestanden"
            )
        return ", ".join(teile) + "."

    def als_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "browser": self.browser,
            "befunde": [b.als_dict() for b in self.befunde],
            "gliederung": {k: v for k, v in self.gliederung.items() if k not in {"markdown", "zustand"}},
            "interaktion": self.interaktion,
            "dauer": round(self.dauer, 2),
            "kurz": self.kurzfassung(),
            "abnahme": self.abnahme,
            "exporte": self.exporte,
            "aktionen": self.aktionen,
            "szenarien": self.szenarien,
            "mobil": self.mobil,
        }


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß ]+", " ", (text or "").lower()).strip()


def beschriftung_aus(eintrag: str) -> str:
    """„Größe: [Dropdown …] + Eingabefeld“ → „Größe“ — nur die Beschriftung zählt."""
    ohne_klammern = re.sub(r"\[[^\]]*\]|„[^“]*“|\"[^\"]*\"|'[^']*'", " ", eintrag or "")
    return re.split(r"[:=+→–]| - ", ohne_klammern)[0].strip(" .,;")


def ist_handlung(beschriftung: str) -> bool:
    """Knopf-Beschriftungen sind Tätigkeiten: „Berechnen“, „Erneut teilnehmen“."""
    woerter = beschriftung.split()
    return 1 <= len(woerter) <= 3 and bool(re.search(r"(?:en|ern|eln)$", woerter[-1].lower())) \
        and not woerter[-1][:1].isdigit()


def fehlende_bedienelemente(erwartet: list[str], gliederung: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Welche erwarteten Elemente sind nirgends zu sehen?

    Rückgabe (fehlende Handlungen, fehlendes Übriges). Nur ein fehlender Knopf
    wie „Zurücksetzen“ ist eine Lücke, die eine Reparatur lohnt. Kleine Modelle
    nennen hier auch Anzeigen („Ergebnis: BMI-Wert [Anzeige …]“) — gemessen am
    19.09. mit einem lokalen 8B-Modell: Das kostete zwei Reparaturen von je über einer Minute.
    Großzügig: Ein Element gilt als vorhanden, sobald eines seiner
    bedeutungstragenden Wörter irgendwo sichtbar ist.
    """
    fundus = " ".join([
        *gliederung.get("knoepfe", []),
        *[f.get("label", "") for f in gliederung.get("felder", [])],
        *gliederung.get("ueberschriften", []),
        gliederung.get("markdown", "")[:20000],
    ])
    fundus = _normal(fundus)
    handlungen: list[str] = []
    uebrige: list[str] = []
    for eintrag in erwartet[:8]:
        name = beschriftung_aus(eintrag)
        if not name or len(name) > 40:
            continue
        woerter = [w for w in _normal(name).split() if len(w) >= 4] or _normal(name).split()
        if woerter and not any(wort in fundus for wort in woerter):
            (handlungen if ist_handlung(name) else uebrige).append(name)
    return handlungen, uebrige


def sichtwerte(gliederung: dict[str, Any]) -> dict[str, int]:
    """Die Messwerte, an denen sich „zeigt die Anwendung etwas?“ entscheidet."""
    sicht = gliederung.get("sichtbar") or {}
    anzahl = gliederung.get("anzahl") or {}
    felder = len(gliederung.get("felder") or [])
    knoepfe = len(gliederung.get("knoepfe") or [])
    return {
        "text": int(gliederung.get("textLaenge") or 0),
        "elemente": int(sicht.get("elemente") or 0),
        "interaktiv": int(sicht.get("interaktiv") or 0) or felder + knoepfe,
        "flaeche": int(sicht.get("flaecheProzent") or 0),
        "bedienung": felder + knoepfe,
        "bild": int(anzahl.get("diagramme") or 0) + int(anzahl.get("bilder") or 0),
    }


def leerbefunde(gliederung: dict[str, Any]) -> list[Befund]:
    """Geladen ist nicht gezeigt: Eine praktisch leere Seite ist ein Fehler.

    Gefunden im Torture-Test am 19.09.2026: Eine Änderung lieferte eine weiße
    Anwendung, die technisch einwandfrei lud — und sichtbar wurde.
    """
    w = sichtwerte(gliederung)
    if w["bild"]:
        return []
    if w["text"] < 15 and not w["interaktiv"]:
        grund = "Kein sichtbarer Text, kein Bedienelement, kein Diagramm, kein Bild."
    elif w["elemente"] <= 1 and w["text"] < 60:
        grund = f"Nur {w['elemente']} sichtbares Element mit {w['text']} Zeichen Text."
    elif w["flaeche"] < 2 and not w["interaktiv"]:
        grund = f"Der sichtbare Inhalt füllt nur {w['flaeche']} % des Fensters."
    else:
        return []
    return [Befund("fehler", "Die Seite bleibt praktisch leer.",
                   grund + " Gemessen im Browser: " + ", ".join(f"{k}={v}" for k, v in w.items()))]


def regressionsbefunde(baseline: dict[str, Any], gliederung: dict[str, Any],
                       rueckbau: bool = False, interaktion: dict[str, Any] | None = None) -> list[Befund]:
    """Vergleicht die neue Fassung mit der zuletzt geprüften Version.

    Verglichen wird relativ, damit kleine Anwendungen nicht an festen Zahlen
    scheitern. Will der Nutzer ausdrücklich etwas entfernen (rueckbau), greift
    nur noch die Leerprüfung.
    """
    if not baseline or not gliederung or rueckbau:
        return []
    alt = sichtwerte(baseline)
    neu = sichtwerte(gliederung)
    if interaktion:
        # Was erst nach einem Klick erscheint (Drei-Punkte-Menü, Startbildschirm), ist nicht
        # verloren (08.10.2026, Kolibri Jump: Knöpfe wanderten gewollt ins Menü, die Prüfung
        # meldete „deutlich kleiner“, und der gewünschte Umbau wurde nie aktiv).
        klicks = interaktion.get("klicks") or []
        neu["bedienung"] = max(neu["bedienung"], int(interaktion.get("knoepfe") or 0)
                               + int(interaktion.get("felder") or 0))
        neu["text"] += min(sum(len(str(t)) for k in klicks for t in (k.get("neueTexte") or [])), 4000)
    if alt["text"] < 80 and alt["bedienung"] < 2:
        return []   # Die Vorlage war selbst kaum etwas — nichts zu vergleichen.

    def anteil(name: str) -> float:
        return neu[name] / alt[name] if alt[name] else 1.0

    verlust = (f"vorher {alt['text']} Zeichen / {alt['bedienung']} Bedienelemente / {alt['elemente']} Elemente, "
               f"jetzt {neu['text']} / {neu['bedienung']} / {neu['elemente']}")
    if alt["bedienung"] >= 3 and neu["bedienung"] == 0:
        return [Befund("fehler", "Die Änderung hat alle Bedienelemente entfernt.", verlust)]
    if anteil("text") < 0.4 and anteil("bedienung") < 0.6:
        return [Befund("fehler", "Die Änderung hat den größten Teil der Anwendung entfernt.", verlust)]
    if anteil("elemente") < 0.3 and not neu["bild"]:
        return [Befund("fehler", "Von der Anwendung ist fast nichts übrig.", verlust)]
    if anteil("text") < 0.6 or anteil("bedienung") < 0.6:
        return [Befund("warnung", "Die Anwendung ist deutlich kleiner als vorher.", verlust)]
    return []


def _befunde_aus_messung(dokument: str, messung: renderer.Messung, handy: renderer.Messung | None,
                         erwartet: list[str]) -> tuple[list[Befund], dict[str, Any], dict[str, Any]]:
    befunde: list[Befund] = []
    if not messung.ok:
        technik = messung.fehler or "unbekannt"
        if "Zeitüberschreitung" in technik or "Endlosschleife" in technik:
            text = "Die Anwendung hängt beim Laden oder Bedienen (vermutlich eine Endlosschleife)."
        elif "abgestürzt" in technik:
            text = "Die Anwendung bringt den Browser zum Absturz."
        else:
            text = "Die Anwendung ließ sich im Browser nicht laden."
        return [Befund("fehler", text, technik)], {}, {}
    probe = messung.probe or {}
    gliederung = probe.get("vorher") if isinstance(probe.get("vorher"), dict) else {}
    interaktion = probe.get("interaktion") if isinstance(probe.get("interaktion"), dict) else {}
    if not probe:
        befunde.append(Befund("warnung", "Die Bedienprobe konnte nicht laufen.",
                              str(messung.roh.get("probeFehler") or messung.fehler or "")[:300]))

    gesehen: set[str] = set()
    beim_laden = int(probe.get("fehlerBeimLaden") or 0)
    knopf_je_fehler = {
        text: eintrag.get("knopf", "")
        for eintrag in interaktion.get("fehlerJeKnopf", []) or []
        for text in eintrag.get("fehler", [])
    }
    for nummer, eintrag in enumerate(probe.get("fehler") or []):
        text = str(eintrag.get("text") or "").strip()
        quelle = str(eintrag.get("quelle") or "")
        if not text or text in gesehen:
            continue
        gesehen.add(text)
        nummer_im_original = originalzeile(dokument, int(eintrag.get("zeile") or 0))
        zeile = f" (Zeile {nummer_im_original})" if nummer_im_original > 0 else ""
        if quelle == "konsole":
            befunde.append(Befund("warnung", "Die Anwendung meldet intern einen Fehler.", text[:300]))
            continue
        if quelle == "ressource":
            ist_skript = "<script" in text
            befunde.append(Befund("fehler" if ist_skript else "warnung",
                                  "Eine eingebundene Datei fehlt." if ist_skript else "Ein Bild wird nicht angezeigt.",
                                  text[:300]))
            continue
        knopf = knopf_je_fehler.get(text)
        if knopf:
            wann = f"beim Klick auf „{knopf}“"
        elif nummer < beim_laden:
            wann = "beim Start"
        else:
            wann = "bei der Bedienung"
        # Mit dem Code um die Zeile findet eine Reparatur die Stelle, statt zu raten.
        ausschnitt = code_ausschnitt(dokument, nummer_im_original) if nummer_im_original > 0 else ""
        befunde.append(Befund("fehler", f"Ein Skriptfehler tritt {wann} auf.",
                              f"{text}{zeile}" + (f"\nCode um die Stelle:\n{ausschnitt}" if ausschnitt else "")))

    anzahl = gliederung.get("anzahl") or {}
    if gliederung:
        befunde.extend(leerbefunde(gliederung))
    kaputt = [k for k in interaktion.get("kaputteWerte") or [] if isinstance(k, dict)]
    if kaputt:
        erster = kaputt[0]
        befunde.append(Befund(
            "fehler",
            f"Die Anwendung zeigt „{erster.get('wert')}“ {erster.get('wann')} — eine Berechnung oder Anzeige ist fehlerhaft.",
            "Sichtbarer Text enthält " + ", ".join(sorted({str(k.get('wert')) for k in kaputt}))
            + f" {erster.get('wann')}, nachdem alle Felder mit Beispielwerten gefüllt wurden "
            "(Feld-IDs im Skript prüfen, Zahlen mit parseFloat lesen, leere Felder abfangen).",
        ))
    felder, knoepfe = int(interaktion.get("felder") or 0), int(interaktion.get("knoepfe") or 0)
    reagiert = bool(interaktion.get("reaktionEingabe") or interaktion.get("reaktionKlick"))
    if interaktion and not reagiert and (felder or knoepfe):
        if felder and knoepfe:
            befunde.append(Befund(
                "fehler",
                "Die Anwendung reagiert weder auf Eingaben noch auf Klicks.",
                f"{felder} Felder gefüllt und {knoepfe} Knöpfe geklickt; die Seite blieb unverändert. "
                "Vermutlich sind Ereignisse nicht verbunden (IDs stimmen nicht, Skript bricht ab, Handler fehlen).",
            ))
        else:
            befunde.append(Befund("warnung", "Bei der Bedienprobe veränderte sich die Seite nicht.",
                                  f"{felder} Felder, {knoepfe} Knöpfe"))
    downloads = [n for n in messung.navigation if n.startswith("blob:") or n.startswith("data:")]
    wegnavigiert = [n for n in messung.navigation if n not in downloads]
    if downloads:
        befunde.append(Befund("info", "Ein Knopf startet einen Download; in der Prüfung wurde er nicht ausgeführt.",
                              ", ".join(d[:60] for d in downloads[:2])))
    if wegnavigiert:
        befunde.append(Befund("warnung", "Ein Link oder Formular wollte die Seite verlassen; das ist gesperrt.",
                              ", ".join(wegnavigiert[:3])))
    handlungen, uebrige = fehlende_bedienelemente(erwartet, gliederung) if gliederung else ([], [])
    if handlungen:
        befunde.append(Befund(
            "luecke",
            "Es fehlt: " + ", ".join(f"„{h}“" for h in handlungen) + ".",
            "Erwartete Knöpfe laut Auftrag nicht gefunden: " + ", ".join(handlungen),
        ))
    if uebrige:
        befunde.append(Befund("warnung", "Nicht gefunden: " + ", ".join(uebrige) + ".",
                              "Erwartete Elemente ohne passende Beschriftung auf der Seite."))
    if handy is not None and handy.ok and isinstance(handy.probe, dict) and handy.probe.get("ueberlauf"):
        befunde.append(Befund("warnung", "Auf dem Smartphone ist die Seite breiter als der Bildschirm.",
                              "Bei 390 px Breite ist scrollWidth größer als die Fensterbreite (feste Breiten?)."))
    return befunde, gliederung, interaktion


async def exporte_pruefen(wuensche: list[dict[str, Any]], titel: str = "") -> list[dict[str, Any]]:
    """Erzeugt die Dateien, die die Anwendung angefordert hat — wirklich.

    Ein Knopf „Als PDF speichern“ beweist nichts. Erst eine gültige Datei
    belegt, dass die Ausgabe funktioniert.
    """
    from app.joshi import export   # spät, damit der Prüfer schlank bleibt

    ergebnisse: list[dict[str, Any]] = []
    for wunsch in (wuensche or [])[:2]:
        typ = str(wunsch.get("typ") or "").lower()
        eintrag: dict[str, Any] = {"typ": typ, "ziel": str(wunsch.get("ziel") or "")[:60], "ok": False}
        if typ not in export.FORMATE or typ in {"html", "eml"}:
            eintrag["grund"] = "Unbekannter Exporttyp"
            ergebnisse.append(eintrag)
            continue
        try:
            daten = await export.aus_abschnitt(
                format_=typ, html=str(wunsch.get("html") or ""), css=str(wunsch.get("css") or ""),
                titel=str(wunsch.get("titel") or titel or "Dokument"))
            eintrag["ok"] = export.ist_gueltig(daten, typ)
            eintrag["bytes"] = len(daten)
            if not eintrag["ok"]:
                eintrag["grund"] = "Die Datei ist nicht lesbar"
        except Exception as fehler:  # noqa: BLE001 – ein Exportfehler ist ein Befund, kein Absturz
            eintrag["grund"] = str(fehler)[:160]
        ergebnisse.append(eintrag)
    return ergebnisse


async def pruefen(
    dokument: str,
    *,
    assets: dict[str, str] | None = None,
    zustand: dict[str, Any] | None = None,
    erwartet: list[str] | None = None,
    abgeschnitten: bool = False,
    baseline: dict[str, Any] | None = None,
    rueckbau: bool = False,
    fokus: list[str] | None = None,
) -> Pruefbericht:
    beginn = time.monotonic()
    befunde = statische_befunde(dokument)
    if abgeschnitten:
        befunde.insert(0, Befund("fehler", "Die Anwendung ist unvollständig — die Datei bricht mittendrin ab.",
                                 "Kein schließendes </html>; die Ausgabe des Modells wurde abgeschnitten."))
    if not dokument.strip():
        return Pruefbericht(befunde, browser=False, dauer=time.monotonic() - beginn)
    laufzeit = laufzeit_dokument(dokument, modus="pruefung", zustand=zustand, assets=assets)
    try:
        messung, handy = await asyncio.gather(
            renderer.rendern(laufzeit, probe=renderer.pruefskript(fokus), breite=1280, hoehe=900),
            renderer.rendern(laufzeit, probe=renderer.inhaltsskript(), breite=390, hoehe=844, timeout=15),
        )
    except renderer.RendererFehlt as fehlt:
        befunde.append(Befund("info", "Browserprüfung nicht verfügbar; nur statisch geprüft.", str(fehlt)))
        return Pruefbericht(befunde, browser=False, dauer=time.monotonic() - beginn)
    weitere, gliederung, interaktion = _befunde_aus_messung(dokument, messung, handy, list(erwartet or []))
    befunde.extend(weitere)
    befunde.extend(regressionsbefunde(baseline or {}, gliederung, rueckbau, interaktion))
    exporte = await exporte_pruefen((messung.probe or {}).get("exporte") or [], gliederung.get("titel", ""))
    for eintrag in exporte:
        if not eintrag["ok"]:
            befunde.append(Befund("fehler", f"Der {eintrag['typ'].upper()}-Export der Anwendung schlug fehl.",
                                  eintrag.get("grund", "")))
    return Pruefbericht(befunde, browser=True, gliederung=gliederung, interaktion=interaktion,
                        dauer=time.monotonic() - beginn, exporte=exporte, mobil=mobilwerte(handy))


def mobilwerte(handy: renderer.Messung | None) -> dict[str, Any]:
    """Was die Messung in Handybreite zeigt — Belege für „mobil“-Wünsche."""
    if handy is None or not handy.ok or not isinstance(handy.probe, dict):
        return {}
    probe = handy.probe
    layout = probe.get("layout") if isinstance(probe.get("layout"), dict) else {}
    return {"breite": probe.get("breite") or 390, "ueberlauf": bool(probe.get("ueberlauf")),
            "spalten": layout.get("spalten"), "karten": layout.get("karten"),
            "kartenbreite": layout.get("kartenbreite"),
            "leereFlaechen": (layout.get("leereFlaechen") or [])[:5],
            "stil": probe.get("stil") or {}, "textLaenge": probe.get("textLaenge") or 0,
            "knoepfe": len(probe.get("knoepfe") or []), "felder": len(probe.get("felder") or [])}


async def szenarien_ausfuehren(
    dokument: str,
    *,
    assets: dict[str, str] | None = None,
    zustand: dict[str, Any] | None = None,
    aktionen: list[str] | None = None,
    szenarien: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aktionsproben und Szenarien — jede in einer frischen, isolierten Seite.

    Proben mit der Endung `_touch` (etwa `ziehen_touch`) laufen in Handybreite.

    Ein `neu_laden` teilt ein Szenario in Phasen: Die nächste Phase startet in
    einer neuen Seite mit dem Zustand, den die vorige hinterlassen hat —
    genau so, wie die Vorschau eine Anwendung wieder öffnet.
    """
    async def rendern(auftrag: dict[str, Any], stand: dict[str, Any] | None, mobil: bool = False) -> dict[str, Any]:
        seite = laufzeit_dokument(dokument, modus="pruefung", zustand=stand, assets=assets)
        messung = await renderer.rendern(seite, probe=renderer.szenarioskript(auftrag),
                                         breite=390 if mobil else 1280, hoehe=844 if mobil else 900, timeout=30)
        if not messung.ok or not isinstance(messung.probe, dict):
            return {"fehlschlag": messung.fehler or "Die Prüfseite lieferte kein Ergebnis"}
        return messung.probe

    async def proben(liste: list[str], mobil: bool) -> list[dict[str, Any]]:
        if not liste:
            return []
        antwort = await rendern({"aktionen": list(liste)}, zustand, mobil)
        if antwort.get("fehlschlag"):
            return [{"aktion": a, "knopf": "", "ergebnis": "nicht_moeglich", "belege": [],
                     "grund": antwort["fehlschlag"][:200]} for a in liste]
        return [a for a in antwort.get("aktionen") or [] if isinstance(a, dict)]

    desktop = [a for a in aktionen or [] if not a.endswith("_touch")]
    touch = [a for a in aktionen or [] if a.endswith("_touch")]

    async def szenario(eintrag: dict[str, Any]) -> dict[str, Any]:
        phasen: list[list[dict[str, Any]]] = [[]]
        for schritt in eintrag.get("schritte") or []:
            if schritt.get("art") == "neu_laden":
                phasen.append([])
            else:
                phasen[-1].append(schritt)
        stand = zustand
        messwerte: dict[str, Any] = {}
        ergebnis = {"id": eintrag.get("id"), "kriterium": eintrag.get("kriterium"), "phasen": len(phasen)}
        for nummer, schritte in enumerate(phasen, 1):
            antwort = await rendern({"schritte": schritte, "id": eintrag.get("id")}, stand,
                                    eintrag.get("geraet") == "mobil")
            if antwort.get("fehlschlag"):
                return {**ergebnis, "ergebnis": "nicht_beweisbar", "grund": antwort["fehlschlag"][:200],
                        "messwerte": messwerte}
            teil = antwort.get("szenario") or {}
            messwerte.update(teil.get("messwerte") or {})
            if teil.get("ergebnis") != "bestanden":
                grund = str(teil.get("grund") or "")
                if len(phasen) > 1:
                    grund = f"Phase {nummer} von {len(phasen)}: {grund}"
                return {**ergebnis, "ergebnis": teil.get("ergebnis") or "nicht_beweisbar", "grund": grund[:300],
                        "messwerte": messwerte}
            stand = antwort.get("zustand") if isinstance(antwort.get("zustand"), dict) else stand
        return {**ergebnis, "ergebnis": "bestanden", "grund": "", "messwerte": messwerte}

    try:
        ergebnisse = await asyncio.gather(proben(desktop, False), proben(touch, True),
                                          *[szenario(s) for s in (szenarien or [])[:4]])
    except renderer.RendererFehlt as fehlt:
        grund = f"Browserprüfung nicht verfügbar: {fehlt}"
        return ([{"aktion": a, "knopf": "", "ergebnis": "nicht_moeglich", "belege": [], "grund": grund}
                 for a in aktionen or []],
                [{"id": s.get("id"), "kriterium": s.get("kriterium"), "ergebnis": "nicht_beweisbar", "grund": grund}
                 for s in szenarien or []])
    return [*ergebnisse[0], *ergebnisse[1]], list(ergebnisse[2:])
