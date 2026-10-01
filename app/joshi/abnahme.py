# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Abnahme: Wurde der Auftrag tatsächlich umgesetzt — und ist das bewiesen?

Technisch lauffähig heißt nicht erfüllt. Gefunden im Torture-Test am
19.09.2026: Eine Änderung lief fehlerfrei, setzte den Wunsch aber gar nicht um
— und galt trotzdem als fertig. Gefunden im Tabellenkalkulations-Stresstest am
21.09.2026: „Speichern“, „Laden“ und „Neu“ galten als nicht umgesetzt, weil
nach dem Klick kein neues Element erschien — dabei ist die Wirkung eines
Speichern-Knopfs eine Änderung im Speicher, nicht im DOM.

Der Ablauf:

1. Aus dem Auftrag entsteht ein **Abnahmevertrag**: prüfbare Kriterien mit
   Stichworten und einer **Nachweisart** (inhalt, bedienung, gestaltung,
   ablauf, nicht_pruefbar), bei Bedienung mit der erwarteten **Aktion**
   (speichern, laden, neu, rueckgaengig, wiederholen, export, …).
2. Aus der Browsermessung entsteht ein **Beweisbericht** mit typisierten
   Belegen: je Klick die gemessenen Wirkungen (Speicher geändert, Wert
   geändert, Element ein- oder ausgeblendet, Export angefordert, Download
   ausgelöst …), Aktionsproben (Speichern → Laden stellt den Stand wieder
   her), Szenarien (Arrange → Act → Assert, auch über ein Neuladen) und der
   Stil vorher/nachher.
3. Erst deterministisch prüfen. Nur die dabei offenen Kriterien gehen in
   **einen** kompakten Modellaufruf — nie die ganze HTML-Datei. Das Modell
   muss für „erfüllt“ einen Beleg nennen, den es im Bericht wirklich gibt;
   sonst bleibt das Kriterium unbewiesen.

Ergebnis je Kriterium: PASS (erfuellt), FAIL (fehlt), NOT_PROVEN (unklar oder
in der Testumgebung nicht beweisbar). NOT_PROVEN ist kein PASS: Ein
unbewiesenes Pflichtkriterium verhindert die Promotion.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.joshi.html_werk import Befund, json_aus_antwort

NACHWEISE = ("inhalt", "bedienung", "gestaltung", "ablauf", "nicht_pruefbar")
AKTIONEN = ("speichern", "laden", "neu", "rueckgaengig", "wiederholen", "export", "filter", "umschalten",
            "navigation", "anzeigen", "ziehen", "sonstiges")
# Aktionen, für die eine eigene Aktionsprobe läuft (Speichern → Ändern → Laden …).
# „ziehen“ läuft bei mobilen Wünschen als Touch-Probe in Handybreite (ziehen_touch).
PROBEN = ("speichern", "laden", "neu", "rueckgaengig", "wiederholen", "ziehen")
_MOBIL = re.compile(r"mobil|handy|smartphone|telefon|iphone|android|schmal|kleine[nm]? (?:bildschirm|display)|"
                    r"touch|finger|wisch|antipp", re.I)
_AUFKLAPPEN = re.compile(r"aufklapp|zuklapp|ausklapp|einklapp|akkordeon|klappt|auf- und zu|auf und (?:wieder )?zu", re.I)
# „Schieben/Ziehen mit dem Finger“ verlangt echtes Ziehen; Antippen oder ein
# Verschieben-Menü belegen nur ein allgemeines „verschieben/bewegen“.
_FINGER = re.compile(r"\b(?:zieh\w*|schieben|schiebt|drag\w*|wisch\w*|finger)\b", re.I)
ZIEHBELEGE = {"touch_drag", "pointer_drag", "html5_drag"}
_ZUKLAPPEN = re.compile(r"wieder zu|zuklapp|auf- und zu|auf und (?:wieder )?zu|einklapp", re.I)
_LEERE_FLAECHE = re.compile(r"wei(?:ß|ss)e[rn]? (?:kasten|fläche|bereich|balken|block)|leere[rn]? (?:kasten|fläche|bereich)|"
                            r"(?:kasten|fläche) .{0,20}(?:weiß|weiss|leer)", re.I)
_SPALTE = re.compile(r"eine[rn]? spalte|untereinander|gestapelt|volle(?:n)? breite|füllen die breite|ganze breite", re.I)
_UEBERLAUF = re.compile(r"abgeschnitten|überlauf|horizontal(?:es)? scroll|seitlich scroll|breiter als|"
                        r"vollständig sichtbar|ohne (?:dass )?(?:etwas )?(?:seitlich )?(?:geschoben|gescrollt|verschoben)", re.I)

VERTRAG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "zusammenfassung": {"type": "string"},
        "rueckbau": {"type": "boolean"},
        "kriterien": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "beschreibung": {"type": "string"},
                    "stichworte": {"type": "array", "items": {"type": "string"}},
                    "interaktion": {"type": "boolean"},
                    "pflicht": {"type": "boolean"},
                    "nachweis": {"type": "string", "enum": list(NACHWEISE)},
                    "aktion": {"type": "string", "enum": list(AKTIONEN)},
                },
                "required": ["id", "beschreibung", "stichworte"],
            },
        },
    },
    "required": ["zusammenfassung", "kriterien"],
}

VERTRAG_SYSTEM = """Du zerlegst einen Änderungswunsch an einer kleinen Webanwendung in im Browser nachprüfbare Abnahmekriterien.

Antworte nur mit JSON:
- zusammenfassung: ein Satz, was sich ändern soll
- rueckbau: true, wenn der Nutzer ausdrücklich etwas entfernen, ausblenden oder vereinfachen will, sonst false
- kriterien: 2 bis 8 Einträge (bei sehr umfangreichen Wünschen bis 10), jeweils
  - id: kurzer Schlüssel in Kleinbuchstaben mit Unterstrich, z. B. "absender_felder"
  - beschreibung: ein prüfbarer Satz, was danach in der Anwendung zu sehen oder zu tun sein muss
  - stichworte: 2 bis 4 Wörter, die dann in Beschriftungen, Knöpfen oder Texten der Anwendung auftauchen müssen (keine ganzen Sätze, keine Fachbegriffe aus dem Code)
  - interaktion: true, wenn erst eine Bedienung (Klick) das Geforderte sichtbar macht
  - pflicht: true, außer der Nutzer nennt es ausdrücklich als „optional“ oder „wenn möglich“
  - nachweis: wie es sich im Browser zeigt:
    "inhalt" – etwas ist zu sehen (Text, Feld, Knopf, Tabelle, Überschrift)
    "bedienung" – ein Knopf oder eine Aktion hat eine Wirkung (Speichern, Laden, Neu, Rückgängig, Filter, Export …)
    "gestaltung" – Aussehen (Farbe, Größe, Abstand, Layout)
    "ablauf" – mehrere Schritte oder ein berechnetes Ergebnis, auch nach einem Neuladen oder mit Zeitmessung
    "nicht_pruefbar" – braucht mehrere Geräte, Tabs oder Nutzer gleichzeitig oder eine echte Offline-/Online-Verbindung
  - aktion: nur bei "bedienung": speichern | laden | neu | rueckgaengig | wiederholen | export | filter | umschalten | navigation | anzeigen | ziehen | sonstiges ("ziehen" = Drag & Drop / Verschieben; "umschalten" = Auf-/Zuklappen)

Prüfe nur, was der Nutzer verlangt. Erfinde keine zusätzlichen Wünsche, keine Technik, keine Qualitätsziele."""

PRUEF_SYSTEM = """Du bist die Abnahme von JOSHI. Du siehst nicht den Code, sondern Messwerte aus dem Browser: Überschriften, Knöpfe, Eingabefelder, sichtbaren Text, was jeder Klick bewirkt hat (Speicher, Werte, Sichtbarkeit, Export …), Ergebnisse von Aktionsproben und Szenarien sowie den Stil vorher/nachher.

Beurteile für jedes offene Kriterium ausschließlich anhand dieser Beweise:
- "erfuellt": In den Beweisen ist eindeutig zu sehen, dass es umgesetzt wurde. Nenne dann in "beleg" genau die Stelle: "text", "knoepfe", "felder", "ueberschriften", "stil", "export", "klick:<Beschriftung des Knopfs>", "aktion:<aktion>", "szenario:<id>" oder "mobil" (Messung in Handybreite).
- "fehlt": In den Beweisen fehlt jede Spur davon.
- "unklar": Die Beweise reichen nicht aus.

Sei streng: Ein passender Knopf allein erfüllt kein Kriterium, das eine Wirkung, eine Eingabemaske oder eine Ausgabe verlangt. Ohne Beleg gibt es kein "erfuellt". Antworte nur mit JSON."""

PRUEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ergebnisse": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "urteil": {"type": "string", "enum": ["erfuellt", "fehlt", "unklar"]},
                    "beleg": {"type": "string"},
                    "begruendung": {"type": "string"},
                },
                "required": ["id", "urteil", "beleg"],
            },
        },
    },
    "required": ["ergebnisse"],
}

STOPWOERTER = {
    "eine", "einen", "einer", "einem", "eines", "soll", "sollen", "sollte", "wird", "werden", "kann", "können",
    "muss", "müssen", "damit", "dass", "oder", "und", "aber", "nicht", "noch", "auch", "beim", "beim", "beim",
    "dann", "danach", "sowie", "jeweils", "bitte", "gerne", "anwendung", "seite", "nutzer", "benutzer",
    "sichtbar", "vorhanden", "angezeigt", "anzeigen", "geben", "geben", "erzeugt", "erzeugen", "möglich",
}

# Erkennung aus dem Text, wenn das Modell keine Nachweisart nennt (oder eine
# offensichtlich falsche). Absichtlich eng: Nur echte Mehrsitzungs- und
# Verbindungsanforderungen gelten als in der Testumgebung nicht beweisbar.
_NICHT_PRUEFBAR = re.compile(
    r"zwei(?:ten)? (?:tabs?|fenster|browser)|mehrere(?:n)? (?:tabs|fenster|nutzer|benutzer|geräte|sitzungen)|"
    r"multiplayer|mehrbenutzer|gleichzeitig(?:e|en)? (?:bearbeit|eingab)|synchronisi|echtzeit|"
    r"offline|reconnect|wieder online|verbindungsabbruch|verbindungsverlust", re.IGNORECASE)
_AKTION_LEXIKON: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ziehen", re.compile(r"drag|\bzieh|verschieb|\bschieb|umsortier|per maus", re.I)),
    ("umschalten", re.compile(r"aufklapp|zuklapp|ausklapp|einklapp|akkordeon|auf- und zu", re.I)),
    ("anzeigen", re.compile(r"öffnet|erscheint|klappt auf|wird angezeigt|zeigt (?:eine|ein|den|die)", re.I)),
    ("rueckgaengig", re.compile(r"rückgängig|undo", re.I)),
    ("wiederholen", re.compile(r"\bredo\b|wiederherstellen|\bwiederholen\b", re.I)),
    ("speichern", re.compile(r"speicher|sichern|\bsave\b", re.I)),
    ("laden", re.compile(r"\bladen\b|\blädt\b|\bload\b|importier", re.I)),
    ("neu", re.compile(r"\bneu\b|\bneues\b|zurücksetz|\breset\b|leeren|\bclear\b", re.I)),
    ("export", re.compile(r"export|\bpdf\b|\bword\b|docx|herunterlad|download|drucken", re.I)),
    ("filter", re.compile(r"filter|\bsuche\b|durchsuch", re.I)),
    ("umschalten", re.compile(r"umschalt|toggle|dunkelmodus|dark ?mode|ein- und ausblend", re.I)),
    ("navigation", re.compile(r"\breiter\b|\btabs?\b|navigation|menü|zwischen (?:den )?(?:seiten|ansichten)", re.I)),
)
_ABLAUF = re.compile(
    r"\d[\d.]*\s*(?:zellen|einträge|zeilen|elemente|datensätze)|performance|millisekund|\bms\b|einfrier|"
    r"inkrementell|zyklus|zirkel|rundung|gerundet|formel|=\s*[a-z]?\d|nach dem neu ?laden|neu geladen|"
    r"reload|bleibt (?:nach|auch)|dauerhaft gespeichert|kohärent|verlauf|berechnet|ergibt|liefert", re.I)
_GESTALTUNG = re.compile(r"farbe|farbig|heller|dunkler|design|schrift|abstand|layout|kontrast|stil\b|hintergrund", re.I)


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß ]+", " ", (text or "").lower())


def _stamm(wort: str) -> str:
    """Grobe Kürzung für deutsche Zusammensetzungen: Empfängerdaten ≈ empfäng."""
    return wort[:6] if len(wort) >= 7 else wort


def aktion_aus_text(text: str) -> str:
    for aktion, muster in _AKTION_LEXIKON:
        if muster.search(text or ""):
            return aktion
    return "sonstiges"


def nachweis_bestimmen(kriterium: dict[str, Any]) -> tuple[str, str]:
    """(nachweis, aktion) — vom Modell genannt, aber gegen den Text geprüft."""
    text = " ".join([kriterium.get("beschreibung", ""), *(kriterium.get("stichworte") or [])])
    genannt = str(kriterium.get("nachweis") or "").strip().lower()
    aktion = str(kriterium.get("aktion") or "").strip().lower()
    if _NICHT_PRUEFBAR.search(text):
        nachweis = "nicht_pruefbar"
    elif genannt == "nicht_pruefbar":
        # Nur echte Mehrsitzungs-/Verbindungsfälle sind unbeweisbar; alles
        # andere versucht JOSHI mit einem Szenario zu belegen.
        nachweis = "ablauf"
    elif genannt in NACHWEISE:
        nachweis = genannt
    elif kriterium.get("interaktion"):
        nachweis = "bedienung"
    elif _ABLAUF.search(text):
        nachweis = "ablauf"
    elif _GESTALTUNG.search(text):
        nachweis = "gestaltung"
    else:
        nachweis = "inhalt"
    if nachweis == "bedienung":
        if aktion not in AKTIONEN or aktion == "sonstiges":
            aktion = aktion_aus_text(kriterium.get("beschreibung", "") + " " + str(kriterium.get("id", "")).replace("_", " "))
            if aktion == "sonstiges" and kriterium.get("interaktion"):
                aktion = "anzeigen"
    else:
        aktion = ""
    return nachweis, aktion


def _kriterium(k: dict[str, Any]) -> dict[str, Any]:
    """Ergänzt ältere Kriterien (nur `interaktion`) um Nachweisart und Aktion."""
    if k.get("nachweis") in NACHWEISE and (k.get("nachweis") != "bedienung"
                                           or (k.get("aktion") in AKTIONEN and k.get("aktion") != "sonstiges")):
        return k
    if k.get("nachweis") == "bedienung" and k.get("aktion") == "sonstiges":
        # Gespeicherte Verträge von vor der Aktion „ziehen“: neu einordnen.
        return {**k, "aktion": aktion_aus_text(k.get("beschreibung", "") + " " + str(k.get("id", "")).replace("_", " "))}
    if "nachweis" not in k and k.get("interaktion"):
        # Alte Verträge: „Interaktion“ hieß immer „ein Klick lässt es erscheinen“.
        return {**k, "nachweis": "bedienung", "aktion": "anzeigen"}
    nachweis, aktion = nachweis_bestimmen(k)
    return {**k, "nachweis": nachweis, "aktion": aktion}


@dataclass
class Ergebnis:
    id: str
    beschreibung: str
    urteil: str            # erfuellt | fehlt | unklar | unbeweisbar
    pflicht: bool = True
    begruendung: str = ""
    nachweis: str = "inhalt"
    beleg: str = ""

    @property
    def status(self) -> str:
        return {"erfuellt": "PASS", "fehlt": "FAIL"}.get(self.urteil, "NOT_PROVEN")

    def als_dict(self) -> dict[str, Any]:
        return {"id": self.id, "beschreibung": self.beschreibung, "urteil": self.urteil, "status": self.status,
                "pflicht": self.pflicht, "nachweis": self.nachweis, "beleg": self.beleg[:120],
                "begruendung": self.begruendung[:300]}


@dataclass
class Abnahmebericht:
    vertrag: dict[str, Any]
    ergebnisse: list[Ergebnis] = field(default_factory=list)
    modell_gefragt: bool = False

    @property
    def offen(self) -> list[Ergebnis]:
        return [e for e in self.ergebnisse if e.pflicht and e.urteil == "fehlt"]

    @property
    def unklar(self) -> list[Ergebnis]:
        return [e for e in self.ergebnisse if e.urteil == "unklar"]

    @property
    def unbewiesen(self) -> list[Ergebnis]:
        return [e for e in self.ergebnisse if e.pflicht and e.urteil == "unklar"]

    @property
    def unbeweisbar(self) -> list[Ergebnis]:
        return [e for e in self.ergebnisse if e.pflicht and e.urteil == "unbeweisbar"]

    def zaehlung(self) -> dict[str, int]:
        zahlen = {"PASS": 0, "FAIL": 0, "NOT_PROVEN": 0}
        for ergebnis in self.ergebnisse:
            zahlen[ergebnis.status] += 1
        return zahlen

    def als_dict(self) -> dict[str, Any]:
        return {
            "zusammenfassung": self.vertrag.get("zusammenfassung", ""),
            "rueckbau": bool(self.vertrag.get("rueckbau")),
            "modell_gefragt": self.modell_gefragt,
            "zaehlung": self.zaehlung(),
            "ergebnisse": [e.als_dict() for e in self.ergebnisse],
        }

    def befunde(self) -> list[Befund]:
        """FAIL und NOT_PROVEN eines Pflichtkriteriums blockieren beide.

        Unterschieden wird nur, ob eine Reparatur helfen kann: Was die
        Testumgebung grundsätzlich nicht nachweisen kann (zweite Sitzung,
        Offline-Verbindung), repariert kein Modell — es bleibt ehrlich offen.
        """
        befunde: list[Befund] = []
        if self.offen:
            namen = "; ".join(e.beschreibung for e in self.offen[:4])
            technik = "Nicht nachgewiesen: " + " | ".join(
                f"{e.id}: {e.beschreibung} ({e.begruendung or 'keine Spur in der Anwendung'})" for e in self.offen)
            befunde.append(Befund("abnahme", "Die gewünschte Änderung ist noch nicht umgesetzt: " + namen, technik))
        if self.unbewiesen:
            befunde.append(Befund(
                "unbewiesen", "Nicht nachgewiesen: " + "; ".join(e.beschreibung for e in self.unbewiesen[:4]),
                " | ".join(f"{e.id} [{e.nachweis}]: {e.begruendung or 'keine messbare Wirkung'}"
                           for e in self.unbewiesen)))
        if self.unbeweisbar:
            befunde.append(Befund(
                "unbeweisbar", "Das kann JOSHI in seiner Testumgebung nicht nachweisen: "
                + "; ".join(e.beschreibung for e in self.unbeweisbar[:4]),
                " | ".join(f"{e.id}: {e.begruendung}" for e in self.unbeweisbar)))
        # Kann-Kriterien (etwa die Funktionshinweise eines Neubaus) sperren
        # nichts und erzeugen keine Warnflut.
        return befunde


# ------------------------------------------------------------------- Vertrag
def vertrag_normalisieren(roh: Any, auftrag: str, grenze: int = 10) -> dict[str, Any]:
    daten = json_aus_antwort(roh)
    daten = daten if isinstance(daten, dict) else {}
    kriterien: list[dict[str, Any]] = []
    for nummer, eintrag in enumerate(daten.get("kriterien") or [], 1):
        if not isinstance(eintrag, dict):
            continue
        beschreibung = str(eintrag.get("beschreibung") or "").strip()[:200]
        if not beschreibung:
            continue
        stichworte = stichwortliste(eintrag.get("stichworte"))
        kennung = re.sub(r"[^a-z0-9_]+", "_", str(eintrag.get("id") or f"kriterium_{nummer}").lower()).strip("_")
        kriterium = {
            "id": kennung or f"kriterium_{nummer}",
            "beschreibung": beschreibung,
            "stichworte": stichworte or stichworte_aus_text(beschreibung),
            "interaktion": bool(eintrag.get("interaktion")),
            "pflicht": eintrag.get("pflicht") is not False,
            "nachweis": str(eintrag.get("nachweis") or ""),
            "aktion": str(eintrag.get("aktion") or ""),
        }
        kriterium["nachweis"], kriterium["aktion"] = nachweis_bestimmen(kriterium)
        kriterium["interaktion"] = kriterium["interaktion"] or kriterium["nachweis"] == "bedienung"
        kriterien.append(kriterium)
    return {
        "zusammenfassung": str(daten.get("zusammenfassung") or auftrag).strip()[:300],
        "rueckbau": bool(daten.get("rueckbau")),
        "kriterien": kriterien[:grenze],
    }


def stichwortliste(roh: Any) -> list[str]:
    """Stichworte robust lesen.

    Gemessen am 20.09.2026: Ein Cloud-Modell lieferte „Angebot drucken“ als
    Zeichenkette statt als Liste — zeichenweise gelesen wären daraus die
    Stichworte „A“, „n“, „g“ geworden.
    """
    if isinstance(roh, str):
        roh = [teil for teil in re.split(r"[,;/|]| und ", roh) if teil.strip()]
    if not isinstance(roh, list):
        return []
    worte = [str(w).strip()[:40] for w in roh if str(w).strip() and len(str(w).strip()) > 1]
    return worte[:5]


def stichworte_aus_text(text: str, grenze: int = 4) -> list[str]:
    woerter = [w for w in _normal(text).split() if len(w) >= 4 and w not in STOPWOERTER]
    gesehen: list[str] = []
    for wort in woerter:
        if wort not in gesehen:
            gesehen.append(wort)
    return gesehen[:grenze]


def vertrag_aus_verstaendnis(verstaendnis: dict[str, Any], auftrag: str) -> dict[str, Any]:
    """Neubau: Das Verständnis liegt schon vor — kein zusätzlicher Modellaufruf."""
    kriterien = []
    for nummer, funktion in enumerate((verstaendnis.get("funktionen") or [])[:5], 1):
        text = str(funktion).strip()[:200]
        if not text:
            continue
        kriterien.append({
            "id": f"funktion_{nummer}",
            "beschreibung": text,
            "stichworte": stichworte_aus_text(text),
            "interaktion": False,
            "pflicht": False,     # Beim Neubau sind es Hinweise, keine Sperre.
            "nachweis": "inhalt",
            "aktion": "",
        })
    return {"zusammenfassung": verstaendnis.get("zweck") or auftrag[:200], "rueckbau": False,
            "kriterien": kriterien}


async def vertrag_erzeugen(zugang: Any, modell: str, *, wunsch: str, bestand: str,
                           verbrauch: dict[str, int]) -> dict[str, Any]:
    """Änderung: Der Wunsch wird zu prüfbaren Kriterien."""
    inhalt = f"Änderungswunsch des Nutzers:\n{wunsch.strip()[:6000]}"
    if bestand:
        inhalt += f"\n\nSo sieht die Anwendung bisher aus:\n{bestand[:1500]}"
    nachrichten = [{"role": "system", "content": VERTRAG_SYSTEM}, {"role": "user", "content": inhalt}]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, VERTRAG_SCHEMA, temperatur=0.1, verbrauch=verbrauch)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 – ohne Vertrag wird nur technisch geprüft
        roh = {}
    vertrag = vertrag_normalisieren(roh, wunsch)
    if not vertrag["kriterien"]:
        # Rückfall ohne Modell: der Wunsch selbst als ein Kriterium.
        vertrag["kriterien"] = [{
            "id": "wunsch", "beschreibung": wunsch.strip()[:200],
            "stichworte": stichworte_aus_text(wunsch), "interaktion": False, "pflicht": True,
            "nachweis": "inhalt", "aktion": "",
        }] if stichworte_aus_text(wunsch) else []
    return vertrag


# ------------------------------------------------------------------- Beweise
def beweise_sammeln(gliederung: dict[str, Any], interaktion: dict[str, Any],
                    baseline: dict[str, Any] | None = None,
                    exporte: list[dict[str, Any]] | None = None,
                    aktionen: list[dict[str, Any]] | None = None,
                    szenarien: list[dict[str, Any]] | None = None,
                    mobil: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kompakter Beweisbericht aus der Browsermessung — nie die HTML-Datei."""
    felder = [{"label": f.get("label", ""), "typ": f.get("typ", "")} for f in (gliederung.get("felder") or [])[:25]]
    klicks = []
    for k in (interaktion.get("klicks") or [])[:24]:
        eintrag = {"knopf": k.get("knopf", ""), "neueFelder": k.get("neueFelder", 0),
                   "neueTexte": (k.get("neueTexte") or [])[:8], "neuerText": str(k.get("neuerText") or "")[:400]}
        if k.get("aufklapper"):
            eintrag["aufklapper"] = True
            eintrag["zurueck"] = bool(k.get("zurueck"))
        if k.get("merkmal"):
            eintrag["merkmal"] = str(k["merkmal"])[:80]
        effekte = [str(e) for e in (k.get("effekte") or [])]
        if not effekte and (eintrag["neueFelder"] or eintrag["neueTexte"] or k.get("neueKnoepfe")):
            effekte = ["dom_added"]      # ältere Messung: etwas ist erschienen
        eintrag["effekte"] = effekte
        for schluessel in ("speicher", "export", "geleert"):
            if k.get(schluessel):
                eintrag[schluessel] = k[schluessel]
        klicks.append(eintrag)
    beweise: dict[str, Any] = {
        "ueberschriften": (gliederung.get("ueberschriften") or [])[:12],
        "knoepfe": (gliederung.get("knoepfe") or [])[:20],
        "felder": felder,
        "textauszug": re.sub(r"\n{2,}", "\n", str(gliederung.get("markdown") or ""))[:1200],
        "klicks": klicks,
        "zahlen": {"felder": len(gliederung.get("felder") or []), "knoepfe": len(gliederung.get("knoepfe") or []),
                   **{k: v for k, v in (gliederung.get("anzahl") or {}).items() if k != "elemente"}},
    }
    if exporte:
        beweise["exporte"] = [{"typ": e.get("typ"), "ok": bool(e.get("ok")), "bytes": e.get("bytes", 0),
                               "grund": e.get("grund", "")} for e in exporte[:3]]
    if aktionen:
        beweise["aktionen"] = [{k: a.get(k) for k in ("aktion", "knopf", "ergebnis", "belege", "grund")}
                               for a in aktionen[:8]]
    if szenarien:
        beweise["szenarien"] = [{k: s.get(k) for k in ("id", "kriterium", "ergebnis", "grund", "messwerte")}
                                for s in szenarien[:8]]
    if mobil:
        beweise["mobil"] = {k: mobil.get(k) for k in ("breite", "spalten", "karten", "kartenbreite", "ueberlauf",
                                                       "leereFlaechen", "knoepfe", "felder")}
    if gliederung.get("gestaltung"):
        beweise["gestaltung"] = gliederung["gestaltung"]
    beweise["reaktion"] = {"eingabe": bool(interaktion.get("reaktionEingabe")),
                           "gefuellt": int(interaktion.get("gefuellt") or 0)}
    if gliederung.get("stil"):
        beweise["stil"] = {"nachher": gliederung["stil"]}
        if baseline and baseline.get("stil"):
            beweise["stil"]["vorher"] = baseline["stil"]
    if baseline:
        beweise["vorher"] = {"felder": len(baseline.get("felder") or []),
                             "knoepfe": len(baseline.get("knoepfe") or []),
                             "ueberschriften": (baseline.get("ueberschriften") or [])[:8]}
    return beweise


def beweisbar(beweise: dict[str, Any]) -> bool:
    """Ohne Messwerte gibt es kein Urteil.

    Liefert die Browsermessung nichts Sichtbares, entscheidet die Leerprüfung —
    die Abnahme schweigt, statt blind „nicht umgesetzt“ zu sagen.
    """
    return bool(beweise.get("ueberschriften") or beweise.get("knoepfe") or beweise.get("felder")
                or len(str(beweise.get("textauszug") or "")) >= 40
                or beweise.get("aktionen") or beweise.get("szenarien"))


def _fundus(beweise: dict[str, Any]) -> str:
    knoepfe = [re.sub(r"\(\s*[iℹⓘ]\s*\)", " Info ", k) for k in beweise.get("knoepfe", [])]
    teile = [*beweise.get("ueberschriften", []), *knoepfe,
             *[f["label"] for f in beweise.get("felder", [])], beweise.get("textauszug", "")]
    for klick in beweise.get("klicks", []):
        teile.append(klick.get("knopf", ""))
        teile.append(klick.get("neuerText", ""))
        teile.extend(klick.get("neueTexte", []))
    return _normal(" ".join(t for t in teile if t))


def _treffer(stichwort: str, fundus: str) -> bool:
    wort = _normal(stichwort).strip()
    if not wort:
        return False
    return all(_stamm(teil) in fundus for teil in wort.split() if len(teil) >= 3) if " " in wort \
        else _stamm(wort) in fundus


# Welche Ausgabe ein Kriterium verlangt — dafür genügt kein Knopf, dafür muss
# eine Datei entstanden sein.
AUSGABEWORTE = {
    "pdf": ("pdf",),
    "docx": ("docx", "word", "doc-datei"),
    "png": ("png",),
    "jpg": ("jpg", "jpeg"),
}


_NUR_SICHTBAR = re.compile(r"knopf|knöpfe|button|schaltfläche|beschrift|sichtbar|zu sehen|vorhanden|angezeigt", re.I)
_ERZEUGT = re.compile(r"erzeug|exportier|herunterlad|download|gespeichert als|als datei|erstellt eine|wird erstellt", re.I)


def geforderte_ausgaben(kriterium: dict[str, Any]) -> set[str]:
    beschreibung = kriterium.get("beschreibung", "")
    # „Die Knöpfe … und Als PDF exportieren sind sichtbar“ verlangt keine PDF-Datei (30.09.2026).
    if kriterium.get("nachweis") == "inhalt" and _NUR_SICHTBAR.search(beschreibung) \
            and not re.search(r"(?:wird|werden)\s+\w*\s*(?:erzeugt|exportiert|heruntergeladen)", beschreibung, re.I):
        return set()
    text = _normal(" ".join([beschreibung, *(kriterium.get("stichworte") or [])]))
    return {typ for typ, worte in AUSGABEWORTE.items() if any(wort in text for wort in worte)}


def nachgewiesene_ausgaben(beweise: dict[str, Any]) -> set[str]:
    return {str(e.get("typ")) for e in beweise.get("exporte") or [] if e.get("ok")}


# Welche gemessene Wirkung eine Aktion belegt. Ein Speichern-Knopf zeigt sich
# im Speicher, nicht im DOM; ein Export in der Anforderung an JOSHI.
WIRKUNG = {
    "speichern": {"local_storage_changed", "export_requested", "download_triggered"},
    "laden": {"local_storage_restored"},
    "neu": {"reset"},
    "rueckgaengig": {"undo_restored"},
    "wiederholen": {"redo_restored"},
    "export": {"export_requested", "download_triggered"},
    "filter": {"element_hidden", "element_shown"},
    "umschalten": {"state_changed", "value_changed", "element_shown", "element_hidden", "text_changed",
                   "route_changed", "modal_opened"},
    "navigation": {"route_changed", "element_shown", "element_hidden", "modal_opened", "dom_added"},
    "anzeigen": {"dom_added", "element_shown", "modal_opened", "route_changed"},
}
NEUTRAL = {"runtime_error"}
# Knopfbeschriftungen je Aktion — dieselbe Liste wie in renderer/szenario.js.
KNOPF = {
    "speichern": re.compile(r"speicher|sichern|\bsave\b|💾", re.I),
    "laden": re.compile(r"\bladen\b|\bload\b|öffnen|importier|wiederherstellen", re.I),
    "neu": re.compile(r"^\s*(?:\+\s*)?neu\b|\bneue[sr]?\b|zurücksetz|\breset\b|leeren|\bclear\b|\bnew\b", re.I),
    "rueckgaengig": re.compile(r"rückgängig|\bundo\b|↶|⟲|↩", re.I),
    "wiederholen": re.compile(r"\bwiederholen\b|\bredo\b|↷|⟳|↪", re.I),
    "export": re.compile(r"export|pdf|word|docx|herunterlad|download|drucken|csv", re.I),
    "filter": re.compile(r"filter|such", re.I),
    "umschalten": re.compile(r"umschalt|toggle|aufklapp|zuklapp|ausklapp|einklapp|\binfo\b|details|mehr anzeigen|"
                             r"▾|▸|▼|▶|⌄|›|ⓘ|ℹ", re.I),
}


def ist_mobil(kriterium: dict[str, Any]) -> bool:
    return bool(_MOBIL.search(" ".join([kriterium.get("beschreibung", ""), str(kriterium.get("id", "")).replace("_", " ")])))


def probenname(kriterium: dict[str, Any]) -> str:
    """Welche Probe ein Bedien-Kriterium belegt — Ziehen auf dem Handy per Touch."""
    aktion = kriterium.get("aktion") or ""
    return f"{aktion}_touch" if aktion == "ziehen" and ist_mobil(kriterium) else aktion


# Ein generischer Speichern-Klick reicht bei einem mehrstufigen Eintrag nicht:
# „Namen eingeben → hinzufügen/speichern → in Liste sichtbar → nach Neuladen
# noch vorhanden“ ist ein Ablauf. Solche Abläufe werden aus der gemessenen
# Oberfläche deterministisch gebaut und brauchen keinen Modellaufruf.
_MEHRSTUFIGER_EINTRAG = re.compile(
    r"(?:name[nsm]?|benennen|eintrag|übung|aufgabe|artikel|kontakt|formular).{0,100}"
    r"(?:eintrag|hinzufüg|anlegen|speicher|erscheint|liste|bibliothek|dauerhaft|nach dem (?:neu ?laden|reload))|"
    r"(?:eintrag|übung|aufgabe|artikel|kontakt).{0,100}(?:name[nsm]?|speicher|liste|bibliothek)", re.I | re.S)


def mehrstufiger_eintrag(kriterium: dict[str, Any]) -> bool:
    """Ob ein Bedienkriterium einen Eintrag über ein Eingabefeld speichert."""
    if kriterium.get("nachweis") != "bedienung" or kriterium.get("aktion") != "speichern":
        return False
    text = " ".join([kriterium.get("beschreibung", ""), *(kriterium.get("stichworte") or [])])
    return bool(_MEHRSTUFIGER_EINTRAG.search(text))


def _szenario_fuer_eintrag(kriterium: dict[str, Any], gliederung: dict[str, Any]) -> dict[str, Any] | None:
    """Baut eine sichere Eingabe-/Speicher-/Reload-Probe aus der Oberfläche."""
    if not mehrstufiger_eintrag(kriterium):
        return None
    text = _normal(" ".join([kriterium.get("beschreibung", ""), *(kriterium.get("stichworte") or [])]))
    woerter = [w for w in text.split() if len(w) >= 3]
    felder = gliederung.get("felder") or []
    kandidaten = []
    for feld in felder:
        if str(feld.get("typ", "")).lower() in {"checkbox", "radio", "select"}:
            continue
        merkmal = _normal(f"{feld.get('id', '')} {feld.get('label', '')}")
        punkte = sum(_stamm(w) in merkmal for w in woerter)
        if re.search(r"name|titel|bezeichnung|eintrag|übung|aufgabe", merkmal, re.I):
            punkte += 3
        kandidaten.append((punkte, feld))
    if not kandidaten:
        return None
    _, feld = max(kandidaten, key=lambda eintrag: eintrag[0])
    knoepfe = [str(k) for k in (gliederung.get("knoepfe") or []) if str(k).strip()]
    genannt = [m.strip() for m in re.findall(r"[„\"]([^”\"]+)[”\"]", kriterium.get("beschreibung", ""))]
    ziel = next((k for k in knoepfe if any(_treffer(n, _normal(k)) for n in genannt)), None)
    if ziel is None:
        ziel = next((k for k in knoepfe if re.search(r"hinzufüg|anleg|speicher|save|add", k, re.I)), None)
    if ziel is None:
        return None
    marker = f"JOSHI-Prüfung-{kriterium.get('id', 'eintrag')[:24]}"
    return {"id": f"s_{kriterium.get('id', 'eintrag')}"[:60], "kriterium": kriterium["id"],
            "schritte": [
                {"art": "eingeben", "ziel": str(feld.get("id") or feld.get("label") or ""), "wert": marker},
                {"art": "klicken", "ziel": ziel},
                {"art": "text_enthaelt", "wert": marker},
                {"art": "speicher_enthaelt", "wert": marker},
                {"art": "neu_laden"},
                {"art": "text_enthaelt", "wert": marker},
                {"art": "speicher_enthaelt", "wert": marker},
                {"art": "keine_fehler"},
            ]}


def gezielte_szenarien(vertrag: dict[str, Any], gliederung: dict[str, Any]) -> list[dict[str, Any]]:
    """Szenarien für mehrstufige Bedienkriterien — ohne Modellbehauptung."""
    ergebnis = []
    for roh in vertrag.get("kriterien") or []:
        kriterium = _kriterium(roh)
        szenario = _szenario_fuer_eintrag(kriterium, gliederung)
        if szenario:
            ergebnis.append(szenario)
    return ergebnis[:4]


_EINGABE_FUER_ABLAUF = re.compile(r"eingeb|eintrag|eintragen|erfass|anleg|hinzufüg|hinzufueg", re.I)
_SPEICHERN_FUER_ABLAUF = re.compile(r"speicher|sicher|persist|dauerhaft", re.I)
_ERGEBNIS_FUER_ABLAUF = re.compile(r"erschein|sichtbar|liste|wiederfind|nach (?:dem )?neu ?laden", re.I)


def braucht_ablaufszenario(kriterium: dict[str, Any]) -> bool:
    """Eine Folge aus Eingabe, Speichern und Ergebnis ist kein einzelner Save-Klick.

    Das gilt auch für eingefrorene Verträge mit ``bedienung/speichern``: Eine
    globale Speichern-Probe könnte sonst einen ganz anderen Knopf (z. B. einen
    PDF-Export) betätigen und die gewünschte Eingabe nicht nachweisen.
    """
    k = _kriterium(kriterium)
    if k.get("nachweis") != "bedienung":
        return False
    text = str(k.get("beschreibung") or "")
    return bool(_EINGABE_FUER_ABLAUF.search(text) and _SPEICHERN_FUER_ABLAUF.search(text)
                and _ERGEBNIS_FUER_ABLAUF.search(text))


def _mobil_pruefen(kriterium: dict[str, Any], beweise: dict[str, Any]) -> tuple[str, str, str] | None:
    """Layout-Wünsche für das Handy — gemessen in 390 px Breite, nicht geraten."""
    m = beweise.get("mobil") or {}
    if not m or not ist_mobil(kriterium):
        return None
    text = kriterium.get("beschreibung", "")
    breite = m.get("breite") or 390
    if _LEERE_FLAECHE.search(text):
        flaechen = m.get("leereFlaechen") or []
        if not flaechen:
            return "erfuellt", f"In {breite} px Breite keine leere, farblich abstechende Fläche gemessen", "mobil"
        f = flaechen[0]
        return "fehlt", (f"In {breite} px Breite: leere Fläche <{f.get('tag')} class=\"{f.get('klasse')}\"> "
                         f"{f.get('breite')}×{f.get('hoehe')} px bei x={f.get('x')}, y={f.get('y')}, "
                         f"Hintergrund {f.get('farbe')}"), ""
    if _SPALTE.search(text) and m.get("spalten"):
        if m["spalten"] == 1 and not m.get("ueberlauf") and (m.get("kartenbreite") or 0) >= 70:
            return "erfuellt", (f"In {breite} px Breite: {m.get('karten')} Karten in einer Spalte, "
                                f"{m.get('kartenbreite')} % breit, kein Überlauf"), "mobil"
        return "fehlt", (f"In {breite} px Breite: Karten in {m['spalten']} Spalte(n), {m.get('kartenbreite')} % breit"
                         + (", Seite breiter als der Bildschirm" if m.get("ueberlauf") else "")), ""
    if _UEBERLAUF.search(text):
        if not m.get("ueberlauf"):
            return "erfuellt", f"In {breite} px Breite kein horizontaler Überlauf", "mobil"
        return "fehlt", f"In {breite} px Breite ist die Seite breiter als der Bildschirm", ""
    if kriterium.get("nachweis") == "gestaltung":
        # Allgemein „mobil first / gut auf dem Handy“: gemessen an Spalten,
        # Überlauf, leeren Flächen und erreichbaren Bedienelementen.
        probleme = []
        if m.get("ueberlauf"):
            probleme.append("Seite breiter als der Bildschirm")
        if (m.get("spalten") or 1) > 1:
            probleme.append(f"Karten in {m['spalten']} Spalten")
        if m.get("leereFlaechen"):
            f = m["leereFlaechen"][0]
            probleme.append(f"leere Fläche {f.get('breite')}×{f.get('hoehe')} px bei x={f.get('x')}, y={f.get('y')}")
        if not (m.get("knoepfe") or m.get("felder")):
            probleme.append("keine Bedienelemente sichtbar")
        if probleme:
            return "fehlt", f"In {breite} px Breite: " + "; ".join(probleme), ""
        return "erfuellt", (f"In {breite} px Breite: eine Spalte, kein Überlauf, keine leeren Flächen, "
                            f"{m.get('knoepfe')} Knöpfe und {m.get('felder')} Felder sichtbar"), "mobil"
    return None


def _knopf_text(klick: dict[str, Any]) -> str:
    """Beschriftung plus Merkmale; ein Symbolknopf „(i)“ heißt „Info“."""
    text = f"{klick.get('knopf', '')} {klick.get('merkmal', '')}"
    text = re.sub(r"\(\s*[iℹⓘ]\s*\)|^\s*[iℹⓘ]\s*$", " info ", text)
    return _normal(text)


# „Info-Knopf“, „Plus-Button“, „Infoknopf“: Das Kriterium nennt ein bestimmtes Bedienelement.
_KNOPFNAME = re.compile(r"\b([A-Za-zÄÖÜäöüß]{2,})-?(?:knopf|knöpfe|button|buttons|schalter|icon|symbol)\b", re.I)
_KEIN_KNOPFNAME = {"ein", "eine", "einen", "jeder", "jeden", "jede", "den", "der", "die", "das", "dem", "druck",
                   "klick", "bedien", "auf", "zu", "neuen", "neue", "eigenen", "eigene", "kleinen", "kleine"}


def _knopfnamen(kriterium: dict[str, Any]) -> list[str]:
    """Die Namen der Bedienelemente, die die Beschreibung ausdrücklich nennt."""
    namen = []
    for treffer in _KNOPFNAME.finditer(kriterium.get("beschreibung", "")):
        wort = treffer.group(1)
        if wort.lower() not in _KEIN_KNOPFNAME and wort not in namen:
            namen.append(wort)
    return namen


def _genannte_klicks(kriterium: dict[str, Any], beweise: dict[str, Any]) -> list[dict[str, Any]]:
    """Klicks auf Knöpfe, die das Kriterium mit seinen Stichworten nennt — die besten zuerst.

    Gewertet wird, wie viele Stichworte in Beschriftung und aufgedecktem Text
    stehen: „eigene Übung anlegen“ passt besser zu „Eigene Übung „Test“ angelegt“
    als zu einem beliebigen Knopf mit „Übung“.
    """
    stichworte = kriterium.get("stichworte") or []
    namen = _knopfnamen(kriterium)
    bewertet = []
    for nummer, klick in enumerate(beweise.get("klicks", [])):
        name = _knopf_text(klick)
        # Nennt die Beschreibung einen „Info-Knopf“, muss der Knopf so heißen.
        if namen and not any(_treffer(w, name) for w in namen):
            continue
        if not any(_treffer(w, name) for w in [*stichworte, *namen]):
            continue
        gesamt = name + " " + _normal(klick.get("neuerText", ""))
        bewertet.append((-sum(_treffer(w, gesamt) for w in stichworte), nummer, klick))
    return [k for _, _, k in sorted(bewertet, key=lambda e: (e[0], e[1]))]


def _nennt_knopf(kriterium: dict[str, Any], beweise: dict[str, Any]) -> bool:
    """Nennt das Kriterium einen Knopf, den es auf der Seite gibt? Dann zählt nur dieser.

    Nennt die Beschreibung ausdrücklich einen „Info-Knopf“, gilt das auch dann,
    wenn die Probe keinen fand — sonst belegt ein beliebiger Aufklapper ihn.
    """
    if _knopfnamen(kriterium):
        return True
    stichworte = kriterium.get("stichworte") or []
    namen = [_normal(n) for n in beweise.get("knoepfe") or []] + [_knopf_text(k) for k in beweise.get("klicks", [])]
    return any(_treffer(w, n) for w in stichworte for n in namen if n.strip())


def _passende_klicks(kriterium: dict[str, Any], beweise: dict[str, Any]) -> list[dict[str, Any]]:
    aktion = kriterium.get("aktion") or ""
    muster = KNOPF.get(aktion)
    stichworte = kriterium.get("stichworte") or []
    treffer = []
    for klick in beweise.get("klicks", []):
        name = klick.get("knopf", "")
        if (muster and muster.search(name)) or any(_treffer(w, _normal(name)) for w in stichworte):
            treffer.append(klick)
    return treffer


# „Live-Ansicht“: Die Seite reagiert auf Eingaben, ohne dass ein Knopf nötig ist.
_LIVE = re.compile(r"\blive\b|sofort|unmittelbar|automatisch aktualis|in echtzeit|echtzeit|ohne (?:dass )?(?:ein )?"
                   r"(?:speichern|neu ?laden|knopf|button|klick)", re.I)


def _bedienung_pruefen(kriterium: dict[str, Any], beweise: dict[str, Any], fundus: str) -> tuple[str, str, str]:
    """(urteil, begründung, beleg) für ein Kriterium, das eine Wirkung verlangt."""
    reaktion = beweise.get("reaktion") or {}
    if _LIVE.search(kriterium.get("beschreibung", "")) and reaktion.get("gefuellt"):
        if reaktion.get("eingabe"):
            return "erfuellt", (f"Die Ansicht reagierte direkt auf {reaktion['gefuellt']} geänderte Eingaben — "
                                "ohne Knopf"), "felder"
        return "fehlt", f"{reaktion['gefuellt']} Eingaben geändert, die Ansicht blieb gleich", ""
    aktion = kriterium.get("aktion") or "sonstiges"
    probe_name = probenname(kriterium)
    stichworte = kriterium.get("stichworte") or []
    genannt = _nennt_knopf(kriterium, beweise)
    # „Ein Link, der kopiert werden kann“ ist keine Datei: Ein PDF-Export belegt
    # ihn nicht, nur ein Knopf, der zum Kriterium passt.
    if aktion == "export" and not geforderte_ausgaben(kriterium) \
            and re.search(r"link|url|kopier|zwischenablage|teilen", kriterium.get("beschreibung", ""), re.I):
        genannt = True
    for probe in beweise.get("aktionen") or []:
        if probe.get("aktion") != probe_name:
            continue
        # Die Probe nahm den ersten passenden Knopf. Nennt das Kriterium einen
        # anderen („Übung hinzufügen“ statt „Als PDF sichern“), belegt sie nichts.
        if aktion != "ziehen" and probe.get("knopf") and genannt \
                and not any(_treffer(w, _normal(probe["knopf"])) for w in stichworte):
            continue
        belege = ", ".join(probe.get("belege") or [])
        wer = f"„{probe.get('knopf')}“: " if probe.get("knopf") else ""
        if probe.get("ergebnis") == "bestanden":
            text_alles = " ".join([kriterium.get("beschreibung", ""), str(kriterium.get("id", "")).replace("_", " "),
                                   *(kriterium.get("stichworte") or [])])
            if aktion == "ziehen" and _FINGER.search(text_alles) and not ZIEHBELEGE & set(probe.get("belege") or []):
                methode = "Antippen" if "tap_move" in (probe.get("belege") or []) else "ein Verschieben-Menü"
                return "unklar", (f"Nur über {methode} verschiebbar ({belege}); Ziehen mit dem Finger "
                                  "(Pointer-Events am Griff) wirkte nicht"), ""
            return "erfuellt", f"Aktionsprobe {probe_name} {wer}{belege}", f"aktion:{probe_name}"
        if probe.get("ergebnis") == "gescheitert":
            return "fehlt", f"Aktionsprobe {probe_name} {wer}{probe.get('grund')}", ""
        if probe.get("ergebnis") == "nicht_moeglich" and aktion == "ziehen":
            return "unklar", f"Ziehprobe nicht möglich: {probe.get('grund')}", ""
    if aktion == "ziehen":
        return "unklar", "Keine Ziehprobe gelaufen", ""
    text = kriterium.get("beschreibung", "")
    if aktion in {"umschalten", "anzeigen"} and _AUFKLAPPEN.search(text):
        # Aufklappen belegen Aufklapper (<summary>, aria-expanded) mit sichtbarer
        # Wirkung; „auf und wieder zu“ verlangt, dass der zweite Klick zurückklappt.
        passend = [k for k in _genannte_klicks(kriterium, beweise) if k.get("aufklapper")]
        # Nennt das Kriterium einen Knopf („Info-Knopf“), zählt nur dieser —
        # sonst belegt jeder Aufklapper, dass es aufklappbare Bereiche gibt.
        kandidaten = passend if (passend or genannt) else [k for k in beweise.get("klicks", []) if k.get("aufklapper")]
        wirkung = {"element_shown", "text_changed", "dom_added", "element_hidden"}
        for klick in kandidaten:
            effekte = set(klick.get("effekte") or [])
            if not effekte & wirkung:
                continue
            if _ZUKLAPPEN.search(text) and "toggled" not in effekte:
                continue
            return "erfuellt", (f"Aufklapper „{klick['knopf']}“: {', '.join(sorted(effekte - NEUTRAL))}"
                                + (" — klappt wieder zu" if "toggled" in effekte else "")), f"klick:{klick['knopf']}"
        if kandidaten:
            return "unklar", (f"Aufklapper „{kandidaten[0]['knopf']}“ gefunden, aber "
                              + ("er klappte nicht wieder zu" if _ZUKLAPPEN.search(text) else "ohne sichtbare Wirkung")), ""
        return "unklar", "Kein Aufklapper (<summary> oder aria-expanded) gefunden oder geklickt", ""
    if aktion == "anzeigen":
        # „Ein Klick öffnet eine Maske mit …“: Stichworte in den Beweisen und
        # ein Klick, der tatsächlich etwas erscheinen ließ.
        treffer = [w for w in stichworte if _treffer(w, fundus)]
        erschienen = [k for k in beweise.get("klicks", []) if set(k.get("effekte") or []) & WIRKUNG["anzeigen"]]
        if treffer and len(treffer) * 2 >= len(stichworte) and erschienen:
            return "erfuellt", "gefunden: " + ", ".join(treffer), f"klick:{erschienen[0].get('knopf', '')}"
        if not erschienen:
            return "unklar", "Kein Klick ließ etwas Neues erscheinen", ""
        return "unklar", f"Stichworte ohne Spur: {', '.join(w for w in stichworte if w not in treffer)}", ""
    klicks = _genannte_klicks(kriterium, beweise) if genannt else _passende_klicks(kriterium, beweise)
    erwartet = WIRKUNG.get(aktion)
    muster = KNOPF.get(aktion)
    for klick in klicks:
        effekte = set(klick.get("effekte") or []) - NEUTRAL
        if erwartet is None and effekte:
            return "erfuellt", f"Klick auf „{klick['knopf']}“: {', '.join(sorted(effekte))}", f"klick:{klick['knopf']}"
        # Der genannte Knopf ist kein typischer „speichern“-Knopf (etwa „Übung
        # anlegen“): Dann belegt jede sichtbare oder gespeicherte Wirkung ihn.
        if genannt and muster and not muster.search(klick.get("knopf", "")):
            breit = effekte & {"dom_added", "element_shown", "text_changed", "value_changed", "local_storage_changed"}
            # Mindestens die Hälfte der Stichworte muss sich in Knopf, Rückmeldung
            # oder Seite wiederfinden: „Übung hinzufügen“ allein belegt keine
            # „eigene Übung mit Namen“.
            umfeld = _normal(klick.get("knopf", "") + " " + klick.get("neuerText", "")) + " " + fundus
            if breit and sum(_treffer(w, umfeld) for w in stichworte) * 2 < len(stichworte):
                breit = set()
            if breit:
                return "erfuellt", (f"Klick auf „{klick['knopf']}“: {', '.join(sorted(breit))}"
                                    + (f" — „{klick['neuerText'][:80]}“" if klick.get("neuerText") else "")), \
                    f"klick:{klick['knopf']}"
            continue    # Die vermutete Aktion passt nicht zu diesem Knopf — ihre Wirkung belegt hier nichts.
        if erwartet and effekte & erwartet:
            gefunden = sorted(effekte & erwartet)
            zusatz = f" ({', '.join(klick['speicher'])})" if klick.get("speicher") else ""
            return "erfuellt", f"Klick auf „{klick['knopf']}“: {', '.join(gefunden)}{zusatz}", f"klick:{klick['knopf']}"
    if klicks:
        wirkungen = sorted({e for k in klicks for e in (k.get("effekte") or [])} - NEUTRAL)
        if not wirkungen:
            return "fehlt", (f"Klick auf „{klicks[0]['knopf']}“ zeigte keine nachweisbare Wirkung "
                             "(kein Speicher, kein Wert, kein Text, keine Anforderung)"), ""
        return "unklar", (f"Klick auf „{klicks[0]['knopf']}“ bewirkte {', '.join(wirkungen)}, "
                          f"aber nicht das für „{aktion}“ Erwartete"), ""
    return "unklar", f"Kein Knopf für „{aktion}“ gefunden oder geklickt", ""


# Farbwünsche und Glas-Optik lassen sich messen (29.09.2026: „rot, gelb, grün“
# und „Vista-Glas“ waren umgesetzt, die Abnahme sah sie nicht).
_FARBWORTE = {"rot": ("rot", "red"), "orange": ("orange",), "gelb": ("gelb", "yellow", "gold", "amber"),
              "gruen": ("grün", "gruen", "green"), "blau": ("blau", "blue"), "lila": ("lila", "violett", "purple"),
              "pink": ("pink", "magenta", "rosa"), "tuerkis": ("türkis", "tuerkis", "cyan", "teal")}
_GLAS = re.compile(r"glas|glass|milchglas|frosted|transluz|durchscheinend|vista|aero|blur|unschärf", re.I)


def _genannte_elemente(beschreibung: str) -> list[str]:
    """„… mit den (vorhandenen) Feldern Budget, Einsatzzweck, Zielauflösung und Profil wählen“ → Liste."""
    treffer = re.search(r"(?:feldern|feld|elementen|knöpfen|bereichen|angaben)\s+([^.;:]+)", beschreibung or "", re.I)
    if not treffer:
        return []
    teile = re.split(r",|\bund\b|\bsowie\b", treffer.group(1))
    return [t.strip(" „“\"'") for t in teile if 2 < len(t.strip()) < 40][:12]


def _gestaltung_pruefen(kriterium: dict[str, Any], beweise: dict[str, Any]) -> tuple[str, str, str] | None:
    messung = beweise.get("gestaltung")
    if not messung:
        return None
    text = " ".join([kriterium.get("beschreibung", ""), *(kriterium.get("stichworte") or [])]).lower()
    farben = messung.get("farben") or {}
    genannt = [f for f, worte in _FARBWORTE.items() if any(re.search(rf"\b{w}", text) for w in worte)]
    if genannt and re.search(r"farbe|farben|color|colour|töne|ton\b|palette|akzent|design|gestalt", text):
        fehlend = [f for f in genannt if farben.get(f, 0) < 2]
        gezaehlt = ", ".join(f"{f} {farben.get(f, 0)}×" for f in genannt)
        if fehlend:
            return "fehlt", f"Farbfamilien gemessen: {gezaehlt} — zu wenig: {', '.join(fehlend)}", ""
        return "erfuellt", f"Farbfamilien auf sichtbaren Elementen: {gezaehlt}", "stil"
    if re.search(r"schatten|shadow|highlight|hervorgehoben|hebt sich|heben sich|tiefe|plastisch", text):
        schatten, farben_gesamt = int(messung.get("schatten") or 0), sum((messung.get("farben") or {}).values())
        if schatten >= 3 and farben_gesamt >= 3:
            return "erfuellt", (f"Schatten auf {schatten} sichtbaren Elementen, {farben_gesamt}× farbige Akzente "
                                f"({', '.join(sorted(messung.get('farben') or {}))})"), "stil"
        return "fehlt", f"Kaum Tiefe: {schatten} Elemente mit Schatten, {farben_gesamt}× farbige Akzente", ""
    # „Die Anwendung zeigt sich im neuen Design mit den Feldern Budget, Einsatzzweck, …“:
    # messbar als (a) die genannten Elemente sind da und (b) die Seite ist sichtbar gestaltet
    # (30.09.2026: sonst entschied das Modell nach Augenmaß und lehnte eine korrekte v6 ab).
    if re.search(r"design|optik|gestaltung|aussehen|\blook\b|oberfläche|layout|stil\b", text) and not _GLAS.search(text):
        genannt = _genannte_elemente(kriterium.get("beschreibung", ""))
        fundus = beweise.get("_fundus") or ""
        fehlend = [g for g in genannt if not _treffer(g, fundus)]
        schatten, farben = int(messung.get("schatten") or 0), sum((messung.get("farben") or {}).values())
        gestaltet = schatten >= 3 or int(messung.get("glas") or 0) >= 2 or farben >= 5
        # Umbenannte Felder zählen mit („Hauptnutzung“ statt „Einsatzzweck“): Gibt es mindestens so viele
        # Eingabefelder wie genannt und findet sich die Mehrheit der Namen, sind die Felder da.
        anzahl = int((beweise.get("zahlen") or {}).get("felder") or 0)
        umbenannt = anzahl >= len(genannt) and len(fehlend) * 2 < len(genannt)
        if genannt and len(fehlend) * 5 > len(genannt) and not umbenannt:
            return "fehlt", f"Im Design fehlen genannte Elemente: {', '.join(fehlend)}", ""
        if gestaltet:
            return "erfuellt", ((f"{len(genannt) - len(fehlend)} von {len(genannt)} genannten Elementen namentlich, "
                                 f"{anzahl} Eingabefelder vorhanden; " if genannt else "")
                                + f"gestaltete Oberfläche: {schatten}× Schatten, {farben}× Farbakzente, "
                                  f"{messung.get('glas', 0)}× Glaseffekt"), "stil"
    if _GLAS.search(text):
        glas, transparent = int(messung.get("glas") or 0), int(messung.get("transparent") or 0)
        if glas >= 2 and transparent >= 2:
            return "erfuellt", (f"Glaseffekt gemessen: {glas} Elemente mit backdrop-filter, "
                                f"{transparent} halbtransparente Flächen, {messung.get('schatten', 0)} mit Schatten"), "stil"
        return "fehlt", f"Kaum Glaseffekt: {glas}× backdrop-filter, {transparent} halbtransparente Flächen", ""
    return None


def _stil_unterschiede(beweise: dict[str, Any]) -> dict[str, tuple[str, str]]:
    stil = beweise.get("stil") or {}
    vorher, nachher = stil.get("vorher") or {}, stil.get("nachher") or {}
    return {k: (str(vorher.get(k)), str(nachher.get(k))) for k in nachher if vorher and vorher.get(k) != nachher.get(k)}


def deterministisch_pruefen(vertrag: dict[str, Any], beweise: dict[str, Any]) -> list[Ergebnis]:
    """Was sich messen lässt, wird gemessen — ohne Modell."""
    fundus = _fundus(beweise)
    erzeugt = nachgewiesene_ausgaben(beweise)
    szenarien = {s.get("kriterium"): s for s in beweise.get("szenarien") or []}
    ergebnisse: list[Ergebnis] = []
    for roh in vertrag.get("kriterien", []):
        kriterium = _kriterium(roh)
        nachweis = kriterium.get("nachweis", "inhalt")
        stichworte = kriterium.get("stichworte") or []
        beleg = ""
        if nachweis == "nicht_pruefbar":
            urteil, begruendung = "unbeweisbar", (
                "Braucht eine zweite Sitzung oder eine echte Verbindung — die Prüfumgebung stellt nur eine "
                "isolierte Seite ohne Netz bereit")
        elif nachweis == "ablauf" or braucht_ablaufszenario(kriterium):
            szenario = szenarien.get(kriterium["id"])
            if szenario and szenario.get("ergebnis") == "bestanden":
                urteil, beleg = "erfuellt", f"szenario:{szenario.get('id')}"
                werte = szenario.get("messwerte") or {}
                begruendung = "Szenario bestanden" + (f" ({json.dumps(werte, ensure_ascii=False)[:120]})"
                                                       if werte else "")
            elif szenario and szenario.get("ergebnis") == "gescheitert":
                urteil, begruendung = "fehlt", f"Szenario gescheitert: {szenario.get('grund', '')}"
            elif szenario and szenario.get("ergebnis") == "nicht_beweisbar":
                urteil, begruendung = "unklar", f"Szenario nicht ausführbar: {szenario.get('grund', '')}"
            else:
                urteil, begruendung = "unklar", "Kein Szenario gelaufen"
        elif nachweis == "bedienung":
            # Mehrstufige Einträge werden ausschließlich durch ihr Ablauf-
            # Szenario bewertet. Ein allgemeiner „Speichern“- oder PDF-Klick
            # darf diesen Nachweis nicht ersetzen.
            szenario = szenarien.get(kriterium["id"]) if mehrstufiger_eintrag(kriterium) else None
            if szenario and szenario.get("ergebnis") == "bestanden":
                urteil, beleg, begruendung = "erfuellt", f"szenario:{szenario.get('id')}", "Szenario bestanden"
            elif szenario and szenario.get("ergebnis") == "gescheitert":
                urteil, begruendung, beleg = "fehlt", f"Szenario gescheitert: {szenario.get('grund', '')}", ""
            elif szenario and szenario.get("ergebnis") == "nicht_beweisbar":
                urteil, begruendung, beleg = "unklar", f"Szenario nicht ausführbar: {szenario.get('grund', '')}", ""
            else:
                urteil, begruendung, beleg = _bedienung_pruefen(kriterium, beweise, fundus)
        elif nachweis in {"gestaltung", "inhalt"} and _mobil_pruefen(kriterium, beweise):
            urteil, begruendung, beleg = _mobil_pruefen(kriterium, beweise)
        elif nachweis == "gestaltung" and _gestaltung_pruefen(kriterium, {**beweise, "_fundus": fundus}):
            urteil, begruendung, beleg = _gestaltung_pruefen(kriterium, {**beweise, "_fundus": fundus})
        elif nachweis == "gestaltung":
            unterschiede = _stil_unterschiede(beweise)
            urteil = "unklar"
            begruendung = ("Stil geändert: " + "; ".join(f"{k}: {a} → {b}" for k, (a, b) in unterschiede.items())
                           if unterschiede else "Keine gemessene Stiländerung")
        else:
            treffer = [w for w in stichworte if _treffer(w, fundus)]
            genug = bool(treffer) and len(treffer) * 2 >= len(stichworte)
            urteil = "erfuellt" if genug else "unklar"
            beleg = "text" if genug else ""
            begruendung = ("gefunden: " + ", ".join(treffer)) if genug else (
                f"Stichworte ohne Spur: {', '.join(w for w in stichworte if w not in treffer)}"
                if stichworte else "keine Stichworte")
        # Verlangt das Kriterium eine Datei, zählt nur eine wirklich erzeugte.
        gefordert = geforderte_ausgaben(kriterium)
        if gefordert and nachweis != "nicht_pruefbar":
            fehlend = gefordert - erzeugt
            if fehlend:
                urteil, beleg = "unklar", ""
                begruendung = ("Keine erzeugte Datei nachgewiesen: " + ", ".join(sorted(fehlend)).upper())
            else:
                urteil, beleg = "erfuellt", "export"
                begruendung = "Datei erzeugt und lesbar: " + ", ".join(sorted(gefordert)).upper()
        ergebnisse.append(Ergebnis(
            id=kriterium["id"], beschreibung=kriterium["beschreibung"], pflicht=kriterium.get("pflicht", True),
            urteil=urteil, begruendung=begruendung, nachweis=nachweis, beleg=beleg,
        ))
    return ergebnisse


# Welche Belege das Modell für welche Nachweisart nennen darf.
_BELEGARTEN = {
    "inhalt": {"text", "knoepfe", "felder", "ueberschriften", "klick", "szenario", "aktion", "mobil"},
    "bedienung": {"klick", "aktion", "szenario", "export"},
    "gestaltung": {"stil", "klick", "mobil"},
    "ablauf": {"szenario", "klick", "aktion"},
}


def beleg_gueltig(beleg: str, nachweis: str, beweise: dict[str, Any]) -> bool:
    """Gibt es den genannten Beleg wirklich — und passt er zur Nachweisart?

    Ein Modellurteil „erfüllt“ ohne messbaren Beleg ist eine Behauptung, kein
    Nachweis. Dann bleibt das Kriterium unbewiesen.
    """
    beleg = (beleg or "").strip()
    art, _, ziel = beleg.partition(":")
    art, ziel = art.strip().lower(), ziel.strip()
    if art not in _BELEGARTEN.get(nachweis, set()):
        return False
    if art == "text":
        return len(str(beweise.get("textauszug") or "")) >= 20
    if art in {"knoepfe", "felder", "ueberschriften"}:
        return bool(beweise.get(art))
    if art == "export":
        return bool(nachgewiesene_ausgaben(beweise))
    if art == "stil":
        return bool(_stil_unterschiede(beweise))
    if art == "mobil":
        return bool(beweise.get("mobil"))
    if art == "klick":
        ziel_normal = _normal(ziel).strip()
        return any(_normal(k.get("knopf", "")).strip() == ziel_normal
                   and set(k.get("effekte") or []) - NEUTRAL for k in beweise.get("klicks", []))
    if art == "aktion":
        return any(a.get("aktion") == ziel and a.get("ergebnis") == "bestanden" for a in beweise.get("aktionen") or [])
    if art == "szenario":
        return any(str(s.get("id")) == ziel and s.get("ergebnis") == "bestanden"
                   for s in beweise.get("szenarien") or [])
    return False


async def pruefen(zugang: Any, modell: str, vertrag: dict[str, Any], beweise: dict[str, Any], *,
                  verbrauch: dict[str, int], streng: bool = True) -> Abnahmebericht:
    """Deterministisch, dann höchstens ein kompakter Modellaufruf."""
    ergebnisse = deterministisch_pruefen(vertrag, beweise)
    bericht = Abnahmebericht(vertrag=vertrag, ergebnisse=ergebnisse)
    # Nur Offenes geht ans Modell. Gemessene Fehlschläge (Aktionsprobe,
    # Szenario) überstimmt es nicht, und Unbeweisbares fragt niemand: Auch das
    # Modell hätte keinen Beleg.
    # Bei mehrstufigen Eingabe-/Speicherwünschen ist nur die Browserfolge ein
    # Beleg. Ein Modell darf ein fehlendes oder nicht ausführbares Szenario
    # nicht nachträglich mit einem allgemeinen Klickbeleg für erfüllt erklären.
    ablaufpflicht = {k["id"] for roh in vertrag.get("kriterien") or []
                    if braucht_ablaufszenario(k := _kriterium(roh))}
    offen = [e for e in ergebnisse if e.urteil == "unklar" and e.id not in ablaufpflicht]
    if not offen:
        return bericht
    beschreibungen = [{"id": e.id, "beschreibung": e.beschreibung, "nachweis": e.nachweis} for e in offen]
    nachrichten = [
        {"role": "system", "content": PRUEF_SYSTEM},
        {"role": "user", "content":
            f"Auftrag: {vertrag.get('zusammenfassung', '')}\n\n"
            f"Offene Kriterien:\n{_kurz_json(beschreibungen)}\n\n"
            f"Beweise aus dem Browser:\n{_kurz_json(beweise, 5000)}"},
    ]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, PRUEF_SCHEMA, temperatur=0.0, verbrauch=verbrauch)
        bericht.modell_gefragt = True
    except Exception:  # noqa: BLE001 – ohne Antwort bleibt es bei der Messung
        roh = {}
    urteile = {}
    daten = json_aus_antwort(roh)
    if isinstance(daten, dict):
        for eintrag in daten.get("ergebnisse") or []:
            if isinstance(eintrag, dict) and eintrag.get("id"):
                urteile[str(eintrag["id"])] = (str(eintrag.get("urteil") or "unklar"),
                                               str(eintrag.get("beleg") or ""),
                                               str(eintrag.get("begruendung") or "")[:300])
    for ergebnis in offen:
        urteil, beleg, begruendung = urteile.get(ergebnis.id, ("", "", ""))
        if urteil == "erfuellt":
            if beleg_gueltig(beleg, ergebnis.nachweis, beweise):
                ergebnis.urteil, ergebnis.beleg = "erfuellt", beleg
                ergebnis.begruendung = begruendung or ergebnis.begruendung
            else:
                # Das Modell behauptet — die Messung belegt es nicht.
                ergebnis.urteil = "unklar"
                ergebnis.begruendung = (f"Modellurteil ohne gültigen Beleg ({beleg or 'kein Beleg'}); "
                                        + ergebnis.begruendung)[:300]
        elif urteil in {"fehlt", "unklar"}:
            ergebnis.urteil = urteil
            ergebnis.begruendung = begruendung or ergebnis.begruendung
        elif streng:
            # Kein Urteil und keine Spur in den Beweisen: Das gilt als nicht
            # umgesetzt, damit eine unerfüllte Änderung nie durchrutscht.
            ergebnis.urteil = "fehlt"
    return bericht


# ----------------------------------------------------------------- Szenarien
SZENARIO_SCHRITTE = ("eingeben", "klicken", "taste", "warten", "messen", "neu_laden",
                     "zweite_sitzung", "offline", "online")
SZENARIO_PRUEFUNGEN = ("text_enthaelt", "text_fehlt", "wert_ist", "wert_enthaelt", "speicher_enthaelt",
                       "keine_fehler", "sichtbar", "unsichtbar", "dauer_hoechstens")

SZENARIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "szenarien": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kriterium": {"type": "string"},
                    "schritte": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "art": {"type": "string", "enum": [*SZENARIO_SCHRITTE, *SZENARIO_PRUEFUNGEN]},
                                "ziel": {"type": "string"},
                                "wert": {"type": "string"},
                                "ms": {"type": "number"},
                            },
                            "required": ["art"],
                        },
                    },
                },
                "required": ["kriterium", "schritte"],
            },
        },
    },
    "required": ["szenarien"],
}

SZENARIO_SYSTEM = """Du schreibst für JOSHI kurze Prüfszenarien (Arrange → Act → Assert), die in einem echten Browser gegen eine fertige Webanwendung laufen. Du siehst nicht den Code, nur die gemessene Oberfläche: Felder (id, Beschriftung), Knöpfe (Beschriftung), Überschriften und Text.

Antworte nur mit JSON: szenarien — höchstens ein Szenario je Kriterium, jeweils kriterium (die ID) und 2 bis 14 schritte.
Schritte (art):
- eingeben: ziel = id oder Beschriftung eines Feldes, wert = Eingabe (Formeln wie "=A1+1" als Text)
- klicken: ziel = Beschriftung oder id eines Knopfs
- taste: ziel = Feld, wert = Taste ("Enter", "Tab", "Escape")
- warten: ms (höchstens 2000)
- messen: startet die Zeitmessung
- neu_laden: lädt die Seite neu, gespeicherte Daten bleiben erhalten
- zweite_sitzung, offline, online: nur wenn das Kriterium es wirklich verlangt
Prüfungen (art):
- text_enthaelt / text_fehlt: wert = Text, der auf der Seite (oder in ziel) stehen muss bzw. nicht stehen darf
- wert_ist / wert_enthaelt: ziel = Feld, wert = erwarteter Inhalt
- speicher_enthaelt: wert = Text, der im gespeicherten Zustand (localStorage) stehen muss
- keine_fehler: keine Skriptfehler seit Beginn
- sichtbar / unsichtbar: ziel = Beschriftung oder id
- dauer_hoechstens: ms seit "messen"

Verwende nur Ziele, die in der Messung vorkommen. Jedes Szenario endet mit mindestens einer Prüfung. Zahlen so erwarten, wie die Anwendung sie anzeigt.
Bei einem Wunsch "Namen eintragen und speichern; erscheint danach" prüfe die ganze Folge: ein eindeutiger Testname fehlt zunächst, wird in das passende Feld eingegeben, der passende Knopf geklickt, der Testname erscheint, nach neu_laden erscheint er erneut. Ein anderer Speichern- oder Exportknopf genügt nicht."""


def _mehrschrittfolge(schritte: list[dict[str, Any]]) -> bool:
    """Ein Mehrschritt-Beleg muss denselben neuen Wert vor und nach Reload zeigen."""
    laden = next((i for i, s in enumerate(schritte) if s["art"] == "neu_laden"), -1)
    if laden < 0:
        return False
    for eingabe in range(laden):
        schritt = schritte[eingabe]
        wert = str(schritt.get("wert") or "").strip()
        if schritt["art"] != "eingeben" or not schritt.get("ziel") or len(wert) < 6:
            continue
        klick = next((i for i in range(eingabe + 1, laden)
                      if schritte[i]["art"] == "klicken" and schritte[i].get("ziel")), -1)
        if klick < 0:
            continue
        def erwartet(index: int) -> bool:
            return schritte[index]["art"] == "text_enthaelt" and \
                _normal(wert) in _normal(str(schritte[index].get("wert") or ""))
        vorher_fehlend = any(schritte[i]["art"] == "text_fehlt"
                              and _normal(wert) in _normal(str(schritte[i].get("wert") or ""))
                              for i in range(eingabe))
        if vorher_fehlend and any(erwartet(i) for i in range(klick + 1, laden)) and \
                any(erwartet(i) for i in range(laden + 1, len(schritte))):
            return True
    return False


def szenarien_normalisieren(roh: Any, kriterien_ids: list[str], grenze: int = 4,
                           mehrschritt_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Nur bekannte Schritte, begrenzte Werte — die Szenarien sind Daten, kein Code."""
    daten = json_aus_antwort(roh)
    daten = daten if isinstance(daten, dict) else {}
    erlaubt = set(SZENARIO_SCHRITTE) | set(SZENARIO_PRUEFUNGEN)
    szenarien: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    for eintrag in daten.get("szenarien") or []:
        if not isinstance(eintrag, dict):
            continue
        kriterium = str(eintrag.get("kriterium") or "")
        if kriterium not in kriterien_ids or kriterium in gesehen:
            continue
        schritte = []
        for schritt in eintrag.get("schritte") or []:
            if not isinstance(schritt, dict) or schritt.get("art") not in erlaubt:
                continue
            sauber: dict[str, Any] = {"art": schritt["art"]}
            if schritt.get("ziel") is not None:
                sauber["ziel"] = str(schritt["ziel"])[:120]
            if schritt.get("wert") is not None:
                sauber["wert"] = str(schritt["wert"])[:500]
            if schritt.get("ms") is not None:
                try:
                    sauber["ms"] = max(0, min(60000, int(float(schritt["ms"]))))
                except (TypeError, ValueError):
                    pass
            schritte.append(sauber)
        schritte = schritte[:25]
        if not any(s["art"] in SZENARIO_PRUEFUNGEN for s in schritte):
            continue
        if kriterium in (mehrschritt_ids or set()) and not _mehrschrittfolge(schritte):
            continue
        gesehen.add(kriterium)
        szenarien.append({"id": f"s_{kriterium}"[:60], "kriterium": kriterium, "schritte": schritte})
    return szenarien[:grenze]


def _eingabe_szenario(kriterium: dict[str, Any], gliederung: dict[str, Any]) -> dict[str, Any] | None:
    """Leitet eine gezielte Probe nur bei eindeutigem Feld und Knopf ab.

    Die Ziele stammen ausschließlich aus der *gemessenen* Oberfläche. Wenn
    mehrere Elemente gleich gut passen, soll ein generiertes Szenario die
    Mehrdeutigkeit auflösen — wir raten hier nicht auf einen PDF-Knopf.
    """
    beschreibung = str(kriterium.get("beschreibung") or "")
    suchtext = _normal(beschreibung)
    zitate = [a or b for a, b in re.findall(r"„([^“]+)“|\"([^\"]+)\"", beschreibung)]

    def punkte(name: str) -> int:
        woerter = [w for w in _normal(name).split() if len(w) >= 4]
        return sum(_stamm(w) in suchtext for w in woerter)

    knoepfe = [str(n) for n in (gliederung.get("knoepfe") or []) if str(n).strip()]
    knopfwertung = [(punkte(name) + 100 * any(_normal(name).strip() == _normal(z).strip() for z in zitate),
                     name) for name in knoepfe]
    knopfwertung = sorted((p, n) for p, n in knopfwertung if p > 0)
    if not knopfwertung or (len(knopfwertung) > 1 and knopfwertung[-1][0] == knopfwertung[-2][0]):
        return None
    knopf = knopfwertung[-1][1]

    felder = [f for f in (gliederung.get("felder") or []) if isinstance(f, dict)
              and f.get("typ") in {"text", "search", "email", "tel", "url", "textarea"}]
    feldwertung = [(punkte(str(f.get("label") or "") + " " + str(f.get("id") or "")), f)
                   for f in felder]
    feldwertung = sorted(((p, f) for p, f in feldwertung if p > 0), key=lambda eintrag: eintrag[0])
    if not feldwertung or (len(feldwertung) > 1 and feldwertung[-1][0] == feldwertung[-2][0]):
        return None
    feld = feldwertung[-1][1]
    ziel = str(feld.get("id") or feld.get("label") or "").strip()
    if not ziel:
        return None
    wert = "JOSHI Testeintrag " + uuid.uuid4().hex[:8]
    schritte = [
        {"art": "text_fehlt", "wert": wert},
        {"art": "eingeben", "ziel": ziel, "wert": wert},
        {"art": "klicken", "ziel": knopf},
        {"art": "text_enthaelt", "wert": wert},
        {"art": "neu_laden"},
        {"art": "text_enthaelt", "wert": wert},
        {"art": "keine_fehler"},
    ]
    return {"id": f"s_{kriterium['id']}"[:60], "kriterium": kriterium["id"], "schritte": schritte}


async def szenarien_erzeugen(zugang: Any, modell: str, *, kriterien: list[dict[str, Any]],
                             gliederung: dict[str, Any], verbrauch: dict[str, int]) -> list[dict[str, Any]]:
    """Ein kompakter Modellaufruf: Szenarien aus Kriterien und gemessener Oberfläche."""
    if not kriterien:
        return []
    automatisch = [s for k in kriterien if braucht_ablaufszenario(k)
                   if (s := _eingabe_szenario(k, gliederung)) is not None]
    offen = [k for k in kriterien if k["id"] not in {s["kriterium"] for s in automatisch}]
    if not offen or len(automatisch) >= 4:
        return automatisch[:4]
    oberflaeche = {
        "felder": [{k: f.get(k) for k in ("id", "label", "typ")} for f in (gliederung.get("felder") or [])[:40]],
        "knoepfe": (gliederung.get("knoepfe") or [])[:40],
        "ueberschriften": (gliederung.get("ueberschriften") or [])[:12],
        "text": re.sub(r"\n{2,}", "\n", str(gliederung.get("markdown") or ""))[:1500],
    }
    nachrichten = [
        {"role": "system", "content": SZENARIO_SYSTEM},
        {"role": "user", "content":
            "Kriterien:\n" + _kurz_json([{"id": k["id"], "beschreibung": k["beschreibung"]} for k in offen])
            + "\n\nGemessene Oberfläche:\n" + _kurz_json(oberflaeche, 5000)},
    ]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, SZENARIO_SCHEMA, temperatur=0.0, verbrauch=verbrauch)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 – ohne Szenario bleibt das Kriterium unbewiesen
        roh = {}
    erzeugt = szenarien_normalisieren(
        roh, [k["id"] for k in offen], grenze=4 - len(automatisch),
        mehrschritt_ids={k["id"] for k in offen if braucht_ablaufszenario(k)})
    return [*automatisch, *erzeugt]


def benoetigte_proben(vertrag: dict[str, Any]) -> list[str]:
    """Welche Aktionsproben der Vertrag braucht — keine, wenn er keine verlangt."""
    gewuenscht = []
    for roh in vertrag.get("kriterien") or []:
        kriterium = _kriterium(roh)
        if kriterium.get("nachweis") == "bedienung" and kriterium.get("aktion") in PROBEN \
                and not braucht_ablaufszenario(kriterium):
            gewuenscht.append(probenname(kriterium))
    reihenfolge = [*PROBEN, "ziehen_touch"]
    return [a for a in reihenfolge if a in gewuenscht]


def szenario_kriterien(vertrag: dict[str, Any]) -> list[dict[str, Any]]:
    return [k for k in (_kriterium(r) for r in vertrag.get("kriterien") or [])
            if k.get("nachweis") == "ablauf" or braucht_ablaufszenario(k)]


def _kurz_json(wert: Any, grenze: int = 4000) -> str:
    return json.dumps(wert, ensure_ascii=False)[:grenze]
