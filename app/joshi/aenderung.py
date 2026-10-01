# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Änderungslinie: Ein Änderungsauftrag verliert nie seinen ursprünglichen Wunsch.

Gefunden im Tabellenkalkulations-Stresstest am 21.09.2026: Nach einem
gescheiterten Versuch schrieb der Nutzer nur „versuch es erneut es
umzusetzten“. JOSHI behandelte diesen Satz als neuen Auftrag — der
Abnahmevertrag schrumpfte von sechs Anforderungen auf „die Anwendung öffnet
sich“ und „Speichern/Laden/Neu lassen sich anklicken“.

Jetzt gilt:

- Ein Änderungsauftrag (`joshi_changes`) hat einen **Root-Wunsch** und einen
  **Root-Vertrag** mit stabilen Kriterien-IDs.
- „versuch es erneut“ ist ein weiterer **Versuch** desselben Auftrags: gleicher
  Wunsch, gleicher Vertrag, dazu die Befunde der bisherigen Versuche.
- Schreibt der Nutzer bei offenem Auftrag etwas Neues, ist es eine
  **Ergänzung**: neue Kriterien kommen dazu, alte Pflichtkriterien bleiben.
- „verwirf das“ / „stattdessen …“ beendet den offenen Auftrag bewusst.
- „erstmal ohne die Info-Knöpfe, prüfen wir später“ **stellt zurück**: Die
  passenden Kriterien bleiben mit ihrer ID im Vertrag, zählen aber nicht, bis
  der Nutzer sie wieder aufnimmt („nimm die Info-Knöpfe wieder auf“).

Die Erkennung ist deterministisch — kein Modellaufruf, keine Verzögerung.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.joshi.html_werk import json_aus_antwort

_WIEDERHOLEN = re.compile(
    r"\b(?:nochmal|noch\s*mal|noch\s+einmal|erneut|wiederhole\w*|neuer\s+versuch|versuch\w*|probier\w*|"
    r"retry|try\s+again|again)\b", re.IGNORECASE)
_VERWERFEN = re.compile(
    r"\b(?:vergiss\s+(?:das|es|den\s+auftrag|die\s+änderung)|verwirf\w*|verwerfen|stattdessen|"
    r"lass\s+(?:das|es)\s+(?:sein|bleiben)|nicht\s+mehr\s+umsetzen|neuer\s+auftrag|"
    r"brich\s+(?:das|den\s+auftrag|die\s+änderung)\s+ab)\b", re.IGNORECASE)
# Wörter, die in einer Wiederholungsbitte keinen eigenen Inhalt tragen.
_FUELLWORTE = {
    "es", "das", "den", "die", "der", "bitte", "noch", "mal", "einmal", "jetzt", "doch", "einfach", "ganz",
    "komplett", "vollständig", "vollstaendig", "richtig", "sauber", "alles", "direkt", "gleich", "nun",
    "umsetzen", "umzusetzen", "umzusetzten", "umsetzten", "umgesetzt", "machen", "mach", "zu", "und", "mit",
    "aber", "diesmal", "dieses", "ein", "eine", "an", "auf", "dem", "wie", "gesagt", "wie", "besprochen",
    "auftrag", "änderung", "aenderung", "anforderungen", "vorher", "vorhin", "davor", "bauen", "bau",
    "hinbekommen", "schaffen", "hin", "kriegen", "bekommst", "du", "kannst", "könntest", "koenntest", "ich",
    "würde", "gerne", "gern", "hast", "ist", "war", "please", "it", "do", "again", "once", "more",
}


# Anweisungen an JOSHI selbst („nutz den Workspace“) sind keine Anforderung an
# die Anwendung. Gefunden am 29.09.2026: Aus „Versuch es erneut und nutzt den
# workspace“ wurden die Kriterien „Der Vorgang wird erneut ausgeführt“ und „Die
# Anwendung zeigt an, dass der Workspace verwendet wird“ — unerfüllbar.
_STEUERUNG = re.compile(
    r"\b(?:und\s+)?(?:(?:nutz|benutz|verwend|nimm|arbeite)\w*\s+(?:(?:mit|im|in)\s+)?(?:(?:den|das|die|dem|dein\w*)\s+)?"
    r"(?:projekt[-\s]?)?(?:workspace|arbeitsbereich|projektordner|projektmodus|projekt[-\s]?dateien)|"
    r"(?:mit|im|über\s+den|ueber\s+den)\s+(?:projekt[-\s]?)?(?:workspace|projektordner))\b", re.I)


# „versuch es erneut“ (auch vertippt: „verssuch“), „mach nochmal“, „korrigiere nur Punkt 6“:
# Anweisungen an JOSHI. Gefunden am 29.09.2026: daraus wurden die Kriterien
# „Erneut-Versuchen-Knopf“ und „Bereich von Punkt 6 auf dem Handy“.
_WIEDERHOLUNGSFLOSKEL = re.compile(
    r"\b(?:ve?r+s*u+c+h\w*|probier\w*|mach\w*|starte?\w*)\s+(?:es|das|den\s+auftrag)?\s*"
    r"(?:nochmal|noch\s*mal|noch\s+einmal|erneut|wieder)\b(?:\s+und\b)?|\b(?:nochmal|erneut)\b(?:\s+und\b)?", re.I)
_SCHRITTVERWEIS = re.compile(r"\b(?:nur\s+)?(?:punkt|schritt|stufe)\s*(\d{1,2})\b|\bab\s+(?:schritt\s+|punkt\s+)?(\d{1,2})\b",
                             re.I)


def steuerung(text: str) -> tuple[str, set[str]]:
    """Entfernt Anweisungen an JOSHI aus dem Satz; Rückgabe: (Rest, erkannte Anweisungen)."""
    roh = text or ""
    gefunden = {"workspace"} if _STEUERUNG.search(roh) else set()
    rest = _STEUERUNG.sub(" ", roh)
    if _WIEDERHOLUNGSFLOSKEL.search(rest):
        gefunden.add("wiederholen")
        rest = _WIEDERHOLUNGSFLOSKEL.sub(" ", rest)
    schritte = [a or b for a, b in _SCHRITTVERWEIS.findall(rest)]
    if schritte:
        gefunden |= {f"schritt:{n}" for n in schritte}
        rest = _SCHRITTVERWEIS.sub(" ", rest)
    return re.sub(r"^[\s,.;:!-]*(?:und\s+)?|[\s,.;:!-]+$", "", re.sub(r"\s+", " ", rest)).strip(), gefunden


@dataclass
class Absicht:
    art: str             # neu | wiederholen | ergaenzen | verwerfen | zurueckstellen | wiederaufnehmen
    rest: str = ""       # Inhalt, der über die Wiederholungsbitte hinausgeht
    ziele: list[str] = field(default_factory=list)   # zurückstellen/wiederaufnehmen: betroffene Kriterien-IDs
    steuerung: set[str] = field(default_factory=set)  # Anweisungen an JOSHI, z. B. {"workspace"}


def _inhaltsworte(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zäöüß0-9]{3,}", text.lower()) if w not in _FUELLWORTE]


def absicht_erkennen(text: str, offen: bool, vertrag: dict[str, Any] | None = None,
                     plan: dict[str, Any] | None = None) -> Absicht:
    """Was will der Nutzer mit diesem Satz — bezogen auf einen offenen Auftrag?

    Mit dem Vertrag des offenen Auftrags erkennt JOSHI auch, ob der Satz Teile
    zurückstellt oder zurückgestellte wieder aufnimmt.
    """
    roh, anweisungen = steuerung((text or "").strip())
    # „korrigiere nur Punkt 6 noch responsive handy design“: Verweist der Satz auf einen
    # Schritt des Plans, meint er diesen Schritt — keine neuen Kriterien.
    if offen and vertrag:
        zurueck = zurueckstellen_erkennen(roh, vertrag, plan)
        if zurueck:
            return Absicht("zurueckstellen", _rest_nach_zurueckstellen(roh), zurueck, steuerung=anweisungen)
    if offen and plan and any(a.startswith("schritt:") for a in anweisungen):
        nummern = {int(a.split(":")[1]) for a in anweisungen if a.startswith("schritt:")}
        if all(1 <= n <= len(plan.get("stufen") or []) for n in nummern):
            return Absicht("wiederholen", "", steuerung=anweisungen)
    if anweisungen and not _inhaltsworte(_WIEDERHOLEN.sub(" ", roh)):
        # Nur „mach es nochmal, im Workspace“: ein weiterer Versuch mit Anweisung.
        return Absicht("wiederholen" if offen else "neu", "", steuerung=anweisungen)
    absicht = _absicht(roh, offen, vertrag, plan)
    # „versuch es erneut, aber mit X“: ein weiterer Versuch mit Zusatz X (ohne die Floskel).
    if "wiederholen" in anweisungen and absicht.art == "ergaenzen":
        absicht.art = "wiederholen"
    absicht.steuerung = anweisungen
    return absicht


def _absicht(roh: str, offen: bool, vertrag: dict[str, Any] | None, plan: dict[str, Any] | None) -> Absicht:
    if offen and vertrag:
        zurueck = zurueckstellen_erkennen(roh, vertrag, plan)
        if zurueck:
            return Absicht("zurueckstellen", _rest_nach_zurueckstellen(roh), zurueck)
        wieder = wiederaufnehmen_erkennen(roh, vertrag, plan)
        if wieder:
            return Absicht("wiederaufnehmen", "", wieder)
    if _VERWERFEN.search(roh):
        rest = _VERWERFEN.sub(" ", roh)
        rest = re.sub(r"^[\s,.;:!-]+|[\s,.;:!-]+$", "", rest)
        return Absicht("verwerfen", rest if _inhaltsworte(rest) else "")
    if not offen:
        return Absicht("neu", roh)
    if _WIEDERHOLEN.search(roh):
        if not _inhaltsworte(_WIEDERHOLEN.sub(" ", roh)):
            return Absicht("wiederholen", "")
        # „Versuch es nochmal, aber mit dunklem Design“ oder „Füge einen
        # Wiederholen-Knopf hinzu“: Es steckt echter Inhalt darin. Der ganze
        # Satz wird zur Ergänzung — nichts wird herausgeschnitten.
        return Absicht("wiederholen", roh)
    return Absicht("ergaenzen", roh)


def wunsch_normalisieren(text: str) -> str:
    """Vergleichbare Form eines Nutzerwunschs ohne dessen Bedeutung umzudeuten.

    Ein wortgleicher erneut abgeschickter Auftrag ist kein neuer Zusatz.  Wir
    normalisieren deshalb nur Schreibvarianten, die bei erneutem Senden keinen
    neuen Wunsch ausdrücken: Unicode, Groß-/Kleinschreibung, Leerraum und
    Satzzeichen.  Eine unscharfe Ähnlichkeitssuche wäre hier gefährlich: Sie
    könnte eine echte Ergänzung unbemerkt verschlucken.
    """
    roh = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(re.findall(r"[^\W_]+", roh, re.UNICODE))


def ist_identischer_wunsch(text: str, linie: dict[str, Any]) -> bool:
    """Ist `text` derselbe Root- bzw. Gesamtwunsch einer offenen Linie?

    Damit wird ein erneut gesendeter Originalprompt deterministisch zum Retry.
    Beide Vergleiche sind absichtlich exakt nach Normalisierung; neue Wörter
    bleiben eine Ergänzung und erhalten eigene Kriterien.
    """
    eingabe = wunsch_normalisieren(text)
    if not eingabe:
        return False
    return eingabe in {
        wunsch_normalisieren(linie.get("wunsch", "")),
        wunsch_normalisieren(gesamtwunsch(linie)),
    }


# ------------------------------------------------------------------ Vertrag
def kennung(text: str, vorhanden: set[str]) -> str:
    """Stabile, eindeutige Kriterien-ID — einmal vergeben, nie wieder geändert."""
    basis = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower()).strip("_")[:40] or "kriterium"
    kandidat, nummer = basis, 2
    while kandidat in vorhanden:
        kandidat, nummer = f"{basis}_{nummer}", nummer + 1
    return kandidat


def vertrag_einfrieren(vertrag: dict[str, Any], herkunft: str = "root",
                       vorhanden: set[str] | None = None) -> dict[str, Any]:
    """Vergibt eindeutige IDs und vermerkt, woher jedes Kriterium kommt."""
    belegt = set(vorhanden or set())
    kriterien = []
    for kriterium in vertrag.get("kriterien") or []:
        eintrag = dict(kriterium)
        eintrag["id"] = kennung(eintrag.get("id") or eintrag.get("beschreibung", ""), belegt)
        eintrag["herkunft"] = eintrag.get("herkunft") or herkunft
        belegt.add(eintrag["id"])
        kriterien.append(eintrag)
    return {**vertrag, "kriterien": kriterien}


def vertrag_ergaenzen(root: dict[str, Any], zusatz: dict[str, Any], nummer: int) -> dict[str, Any]:
    """final_contract = root_contract + ausdrücklich hinzugefügte Anforderungen."""
    vorhanden = {k["id"] for k in root.get("kriterien") or []}
    neu = vertrag_einfrieren(zusatz, herkunft=f"ergaenzung_{nummer}", vorhanden=vorhanden)
    zusammenfassung = root.get("zusammenfassung", "")
    if zusatz.get("zusammenfassung"):
        zusammenfassung = f"{zusammenfassung} Zusätzlich: {zusatz['zusammenfassung']}".strip()
    return {
        **root,
        "zusammenfassung": zusammenfassung[:600],
        "rueckbau": bool(root.get("rueckbau")) or bool(zusatz.get("rueckbau")),
        "kriterien": [*(root.get("kriterien") or []), *neu["kriterien"]],
    }


# ------------------------------------------------------------ Zurückstellen
# Gefunden am 27.09.2026: „ok dann mach es lauffähig erstmal ohne info buttons
# wir prüfen später.“ JOSHI machte daraus eine Ergänzung mit den neuen
# Kriterien „keine Info-Knöpfe“ und „App läuft“, behielt aber alle drei
# Info-Kriterien — und scheiterte erneut an genau dem Schritt, den der Nutzer
# zurückstellen wollte. Checkpoint 4 war da längst ein geprüfter Stand.
_AUFSCHUB = re.compile(r"\b(?:erst\s*mal|erstmal|erst\s+einmal|vorerst|zunächst|zunaechst|fürs\s+erste|"
                       r"später|spaeter|danach|nachher|lauffähig|lauffaehig|zum\s+laufen|erst\s+später)\b", re.I)
_OHNE = re.compile(r"\bohne\s+([^,.;!?]+)", re.I)
_WEG = re.compile(r"\blass\w*\s+([^,.;!?]+?)\s+(?:(?:erst\s*mal|erstmal|vorerst|zunächst|noch)\s+)?weg\b", re.I)
_SPAETER = re.compile(r"([^,.;!?]+?)\s+(?:(?:machen|kommen?|bauen|prüfen|pruefen|testen|klären)\s+(?:wir\s+)?)?"
                      r"(?:erst\s+)?(?:später|spaeter|danach|nachher)\b", re.I)
# „lass die Demo Daten drin“, „behalte X“, „X bleiben drin“: der Nutzer nimmt einen Wunsch zurück
# (30.09.2026: daraus wurde ein zweites, gegenteiliges Kriterium neben „Demo-Daten entfernen“).
_DRIN = re.compile(r"\blass\w*\s+([^,.;!?]+?)\s+(?:doch\s+)?(?:drin|drinnen|stehen|so|bestehen|erhalten)\b|"
                   r"\bbehalt\w*\s+([^,.;!?]+)|([^,.;!?]+?)\s+(?:soll|sollen|dürfen|bleib\w*)\s+(?:doch\s+)?"
                   r"(?:drin|bestehen|erhalten|bleiben)\b", re.I)
_STREICHEN = re.compile(r"\b(?:streich\w*|zurückstell\w*|zurueckstell\w*|verschieb\w*)\s+([^,.;!?]+)", re.I)
_WIEDER = re.compile(r"\b(?:wieder\s+(?:auf|rein|dazu|mit)|(?:nimm|hol)\w*\s+[^,.;!?]*?\s+wieder|"
                     r"jetzt\s+(?:doch\s+)?(?:auch\s+)?(?:die|den|das)?\s*[^,.;!?]{2,40}?\s+(?:umsetzen|einbauen|machen|dazu)|"
                     r"reaktivier\w*|zurückhol\w*|zurueckhol\w*)", re.I)
_SATZSTOPP = {"wir", "und", "dann", "bitte", "erst", "erstmal", "später", "spaeter", "aber", "oder", "machen", "mach",
              "prüfen", "pruefen", "testen", "schauen", "kümmern", "ok", "okay", "also", "danach", "nachher", "vorerst",
              "zunächst", "zunaechst", "mal", "noch", "es", "sie", "weg", "lassen", "lass", "sollen", "soll", "können",
              "kann", "ich", "du", "uns", "jetzt", "einmal", "fürs", "erste", "wieder", "auf", "rein", "dazu"}
_ARTIKEL = {"die", "der", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "diese", "diesen",
            "dieses", "mein", "meine", "unsere", "alle", "jede", "jeden", "jeder", "mit", "von", "vom", "zum", "zur"}
_ALLGEMEIN = {"button", "buttons", "knopf", "knöpfe", "knoepfe", "funktion", "funktionen", "feature", "features",
              "teil", "teile", "sache", "sachen", "zeug", "bereich", "bereiche", "element", "elemente", "punkt",
              "punkte", "anforderung", "anforderungen", "schalter", "icon", "icons", "symbol", "symbole"}


def _woerter(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß0-9][a-zäöüß0-9-]*", (text or "").lower())


def _gruppe(woerter: list[str]) -> list[str]:
    ergebnis = []
    for wort in woerter:
        if wort in _SATZSTOPP:
            break
        if wort not in _ARTIKEL:
            ergebnis.append(wort)
        if len(ergebnis) >= 4:
            break
    return ergebnis


def zurueckstellen_ziele(text: str) -> list[str]:
    """Die Dinge, die der Satz zurückstellen will („info buttons“ → „info“)."""
    gruppen: list[list[str]] = []
    aufschub = bool(_AUFSCHUB.search(text or ""))
    if aufschub:
        gruppen += [_gruppe(_woerter(m.group(1))) for m in _OHNE.finditer(text or "")]
        gruppen += [list(reversed(_gruppe(list(reversed(_woerter(m.group(1)))))))
                    for m in _SPAETER.finditer(text or "")]
    gruppen += [_gruppe(_woerter(m.group(1))) for m in _WEG.finditer(text or "")]
    for m in _DRIN.finditer(text or ""):
        teil = next(g for g in m.groups() if g)
        gruppen.append(list(reversed(_gruppe(list(reversed(_woerter(teil)))))) if m.group(3) else _gruppe(_woerter(teil)))
    gruppen += [_gruppe(_woerter(m.group(1))) for m in _STREICHEN.finditer(text or "")]
    ziele: list[str] = []
    for gruppe in gruppen:
        genau = [w.strip("-") for w in gruppe if w not in _ALLGEMEIN]
        for wort in genau or gruppe:
            for teil in wort.split("-"):
                if len(teil) >= 3 and teil not in ziele and teil not in _ALLGEMEIN | _SATZSTOPP | _ARTIKEL:
                    ziele.append(teil)
    return ziele


def _stamm(wort: str) -> str:
    wort = wort.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return wort[:6] if len(wort) > 6 else wort


def _kriteriumstext(kriterium: dict[str, Any]) -> str:
    text = " ".join([kriterium.get("id", "").replace("_", " "), kriterium.get("beschreibung", ""),
                     *(kriterium.get("stichworte") or [])]).lower()
    return text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def aktiv(kriterium: dict[str, Any]) -> bool:
    return not (kriterium.get("zurueckgestellt") or kriterium.get("entfallen"))


def _passende(vertrag: dict[str, Any], ziele: list[str], plan: dict[str, Any] | None,
              nur_aktive: bool = True) -> list[str]:
    staemme = [_stamm(z) for z in ziele]
    ids = [k["id"] for k in vertrag.get("kriterien") or []
           if (aktiv(k) or not nur_aktive) and not k.get("entfallen")
           and any(s in _kriteriumstext(k) for s in staemme)]
    # Ein Schritt, der nach dem Zurückgestellten heißt („Info-Beschreibungen
    # ergänzen“), hängt ganz daran — auch sein Kriterium „Beschreibung erklärt …“.
    if ids:
        for stufe in (plan or {}).get("stufen") or []:
            titel = str(stufe.get("titel", "")).lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            if any(s in titel for s in staemme):
                ids += [i for i in stufe.get("kriterien") or [] if i not in ids]
    bekannt = {k["id"]: k for k in vertrag.get("kriterien") or []}
    return [i for i in ids if i in bekannt and (aktiv(bekannt[i]) or not nur_aktive) and not bekannt[i].get("entfallen")]


def zurueckstellen_erkennen(text: str, vertrag: dict[str, Any], plan: dict[str, Any] | None = None) -> list[str]:
    """IDs der offenen Kriterien, die der Satz zurückstellt — leer, wenn er nichts zurückstellt.

    „Die Karten ohne Rahmen“ stellt nichts zurück (kein Aufschub, kein
    passendes Kriterium); „erstmal ohne Info-Knöpfe“ schon.
    """
    ziele = zurueckstellen_ziele(text)
    return _passende(vertrag, ziele, plan) if ziele else []


def wiederaufnehmen_erkennen(text: str, vertrag: dict[str, Any], plan: dict[str, Any] | None = None) -> list[str]:
    """IDs zurückgestellter Kriterien, die der Satz ausdrücklich wieder aufnimmt."""
    zurueck = {k["id"] for k in zurueckgestellt(vertrag)}
    if not zurueck or not _WIEDER.search(text or ""):
        return []
    worte = [t for w in _woerter(text) if w not in _SATZSTOPP | _ARTIKEL | _ALLGEMEIN
             for t in w.split("-") if len(t) >= 3 and t not in _SATZSTOPP | _ARTIKEL | _ALLGEMEIN]
    return [i for i in _passende(vertrag, worte, plan, nur_aktive=False) if i in zurueck]


_ALLGEMEINER_REST = {"weiter", "ab", "drin", "behalte", "bleiben", "bleibt", "mach",
                     "lauffähig", "lauffaehig", "funktionsfähig", "funktioniert", "funktionieren", "läuft", "laeuft",
                     "laufen", "stabil", "fertig", "sauber", "ok", "okay", "dann", "erstmal", "erst", "vorerst",
                     "zunächst", "wir", "prüfen", "pruefen", "später", "spaeter", "testen", "ohne", "weg", "lass",
                     "lassen", "danach", "nachher", "info", "buttons", "button"}


def _rest_nach_zurueckstellen(text: str) -> str:
    """Was der Satz außer dem Zurückstellen noch verlangt — meist nichts („mach es lauffähig“)."""
    rest = _OHNE.sub(" ", text or "")
    rest = _WEG.sub(" ", rest)
    rest = _STREICHEN.sub(" ", rest)
    rest = _DRIN.sub(" ", rest)
    worte = [w for w in _inhaltsworte(rest) if w not in _ALLGEMEINER_REST and w not in _SATZSTOPP]
    return rest.strip() if len(worte) >= 2 else ""


def zurueckstellen(vertrag: dict[str, Any], ids: list[str], text: str) -> dict[str, Any]:
    """Markiert Kriterien als zurückgestellt — sie behalten ID und Wortlaut."""
    gewaehlt = set(ids)
    kriterien = []
    for kriterium in vertrag.get("kriterien") or []:
        eintrag = dict(kriterium)
        if eintrag["id"] in gewaehlt and aktiv(eintrag):
            eintrag["zurueckgestellt"] = {"text": (text or "")[:200]}
        kriterien.append(eintrag)
    return {**vertrag, "kriterien": kriterien}


def wiederaufnehmen(vertrag: dict[str, Any], ids: list[str]) -> dict[str, Any]:
    gewaehlt = set(ids)
    return {**vertrag, "kriterien": [
        {k: v for k, v in kriterium.items() if k != "zurueckgestellt"} if kriterium["id"] in gewaehlt else kriterium
        for kriterium in vertrag.get("kriterien") or []]}


def vertrag_bereinigen(linie: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Heilt Linien, in denen ein Zurückstellen früher als Ergänzung landete.

    Rückgabe: (Vertrag, Beschreibung der Korrekturen). Kriterien, die aus so
    einer „Ergänzung“ entstanden („keine Info-Knöpfe“, „App läuft“), entfallen;
    die gemeinten Kriterien werden zurückgestellt.
    """
    vertrag = linie.get("vertrag") or {}
    korrekturen: list[str] = []
    gesehen: set[str] = set()
    for nummer, zusatz in enumerate(linie.get("ergaenzungen") or [], 1):
        if not isinstance(zusatz, dict) or zusatz.get("art"):
            continue
        herkunft = f"ergaenzung_{nummer}"
        eigene = [k for k in vertrag.get("kriterien") or [] if k.get("herkunft") == herkunft and not k.get("entfallen")]

        def entfallen_lassen(ids: list[str], grund: str) -> None:
            nonlocal vertrag
            vertrag = {**vertrag, "kriterien": [{**k, "entfallen": {"text": grund}} if k["id"] in ids else k
                                                for k in vertrag.get("kriterien") or []]}

        # Derselbe Satz noch einmal geschickt: ein weiterer Versuch, keine neue Ergänzung.
        schluessel = wunsch_normalisieren(str(zusatz.get("text") or ""))
        if schluessel in gesehen:
            entfallen_lassen([k["id"] for k in eigene], "doppelt geschickte Nachricht")
            zusatz["art"] = "wiederholung"
            korrekturen.append(f"„{str(zusatz.get('text'))[:60]}“ war doppelt; entfallen: {', '.join(k['id'] for k in eigene)}")
            continue
        gesehen.add(schluessel)
        rest_s, anweisungen_s = steuerung(str(zusatz.get("text") or ""))
        plan = linie.get("plan") or {}
        ohne_eigene = {**vertrag, "kriterien": [k for k in vertrag.get("kriterien") or [] if k.get("herkunft") != herkunft]}
        zurueck_ids = zurueckstellen_erkennen(str(zusatz.get("text") or ""), ohne_eigene, plan)
        if any(a.startswith("schritt:") for a in anweisungen_s) and plan.get("stufen"):
            entfallen_lassen([k["id"] for k in eigene], "Verweis auf einen Schritt des Plans, keine Anforderung")
            if zurueck_ids:
                vertrag = zurueckstellen(vertrag, zurueck_ids, str(zusatz.get("text") or ""))
                korrekturen.append(f"zurückgenommen: {', '.join(zurueck_ids)}")
            zusatz["art"], zusatz["steuerung"] = "steuerung", sorted(anweisungen_s)
            korrekturen.append(f"„{str(zusatz.get('text'))[:60]}“ meinte einen Plan-Schritt")
            continue
        if "wiederholen" in anweisungen_s:
            # Kriterien, die nur die Wiederholung selbst beschreiben, entfallen; der Rest bleibt.
            weg = [k["id"] for k in eigene if re.search(r"erneut|wiederhol|nochmal|noch einmal|retry|neu starten",
                                                         f"{k['id']} {k.get('beschreibung', '')}", re.I)]
            if weg:
                entfallen_lassen(weg, "„versuch es erneut“ ist eine Anweisung an JOSHI")
                korrekturen.append(f"„{str(zusatz.get('text'))[:60]}“: entfallen {', '.join(weg)}")
        rest, anweisungen = steuerung(str(zusatz.get("text") or ""))
        anweisungen.discard("wiederholen")
        if anweisungen and not _inhaltsworte(_WIEDERHOLEN.sub(" ", rest)):
            entfallen = [k["id"] for k in vertrag.get("kriterien") or []
                         if k.get("herkunft") == herkunft and not k.get("entfallen")]
            vertrag = {**vertrag, "kriterien": [
                {**k, "entfallen": {"text": "stammte aus einer Anweisung an JOSHI, nicht aus einer Anforderung"}}
                if k["id"] in entfallen else k for k in vertrag.get("kriterien") or []]}
            zusatz["art"], zusatz["steuerung"] = "steuerung", sorted(anweisungen)
            korrekturen.append(f"„{str(zusatz.get('text'))[:80]}“ war eine Anweisung an JOSHI"
                               + (f"; entfallen: {', '.join(entfallen)}" if entfallen else ""))
            continue
        ohne_zusatz = {**vertrag, "kriterien": [k for k in vertrag.get("kriterien") or []
                                                if k.get("herkunft") != herkunft]}
        ids = zurueckstellen_erkennen(str(zusatz.get("text") or ""), ohne_zusatz, linie.get("plan"))
        if not ids:
            continue
        entfallen = [k["id"] for k in vertrag.get("kriterien") or [] if k.get("herkunft") == herkunft and not k.get("entfallen")]
        vertrag = {**vertrag, "kriterien": [
            {**k, "entfallen": {"text": "stammte aus einem Zurückstellen, nicht aus einer Ergänzung"}}
            if k["id"] in entfallen else k for k in vertrag.get("kriterien") or []]}
        vertrag = zurueckstellen(vertrag, ids, str(zusatz.get("text") or ""))
        zusatz["art"] = "zurueckstellen"
        zusatz["ids"] = ids
        korrekturen.append(f"„{str(zusatz.get('text'))[:80]}“ stellt {', '.join(ids)} zurück"
                           + (f"; entfallen: {', '.join(entfallen)}" if entfallen else ""))
    return vertrag, korrekturen


def aktiver_vertrag(vertrag: dict[str, Any]) -> dict[str, Any]:
    """Was jetzt zählt: ohne zurückgestellte und entfallene Kriterien."""
    return {**vertrag, "kriterien": [k for k in vertrag.get("kriterien") or [] if aktiv(k)]}


def zurueckgestellt(vertrag: dict[str, Any]) -> list[dict[str, Any]]:
    return [k for k in vertrag.get("kriterien") or [] if k.get("zurueckgestellt") and not k.get("entfallen")]


UEBERHOLT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ueberholt": {"type": "array", "items": {"type": "string"}}},
    "required": ["ueberholt"],
}


async def ueberholte_kriterien(zugang: Any, modell: str, vertrag: dict[str, Any], neu: str,
                               verbrauch: dict[str, int], schuetzen: set[str] | None = None) -> list[str]:
    """Welche bestehenden Kriterien ersetzt oder widerspricht der neue Wunsch?

    Gefunden am 30.09.2026: Nach „nur noch drei Knöpfe: Konfigurieren, Laden, PDF“
    blieben „Knopf Zurücksetzen sichtbar“ und „Zurücksetzen leert die Felder“ Pflicht —
    unerfüllbar nebeneinander, die korrekte v6 galt als unfertig.
    """
    kandidaten = [k for k in vertrag.get("kriterien") or [] if aktiv(k) and k["id"] not in (schuetzen or set())]
    if not kandidaten or not (neu or "").strip():
        return []
    liste = "\n".join(f"- {k['id']}: {k['beschreibung']}" for k in kandidaten)
    nachrichten = [
        {"role": "system", "content": (
            "Ein Nutzer ändert eine Anwendung schrittweise. Prüfe, welche der BISHERIGEN Anforderungen durch den "
            "NEUEN Wunsch ersetzt werden oder ihm widersprechen (etwa weil ein Knopf wegfallen soll, der vorher "
            "verlangt war). Nur echte Widersprüche oder ausdrückliche Ersetzungen — was weiterhin gilt, bleibt. "
            'Nur JSON: {"ueberholt": ["id", ...]} (leer, wenn nichts).')},
        {"role": "user", "content": f"BISHERIGE Anforderungen:\n{liste}\n\nNEUER Wunsch:\n{neu[:2000]}"}]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, UEBERHOLT_SCHEMA, temperatur=0.0, verbrauch=verbrauch)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 – im Zweifel bleibt alles bestehen
        return []
    daten = json_aus_antwort(roh)
    ids = daten.get("ueberholt") if isinstance(daten, dict) else []
    bekannt = {k["id"] for k in kandidaten}
    return [i for i in ids or [] if isinstance(i, str) and i in bekannt]


def ueberholt_markieren(vertrag: dict[str, Any], ids: list[str], text: str) -> dict[str, Any]:
    gewaehlt = set(ids)
    return {**vertrag, "kriterien": [
        {**k, "entfallen": {"text": f"ersetzt durch den späteren Wunsch: {text[:120]}"}} if k["id"] in gewaehlt else k
        for k in vertrag.get("kriterien") or []]}


def teilvertrag(vertrag: dict[str, Any], ids: list[str]) -> dict[str, Any]:
    """stage_contract ⊂ root_contract — nie ein neues Kriterium, nie eine Umformulierung."""
    gewuenscht = set(ids)
    return {**vertrag, "kriterien": [k for k in vertrag.get("kriterien") or [] if k["id"] in gewuenscht]}


def pflichtkriterien(vertrag: dict[str, Any]) -> list[dict[str, Any]]:
    return [k for k in vertrag.get("kriterien") or [] if k.get("pflicht", True) and aktiv(k)]


# ------------------------------------------------------------------ Wunsch
def gesamtwunsch(aenderung: dict[str, Any]) -> str:
    """Der Wunsch, wie ihn das Modell bei jedem Versuch bekommt: Root + Ergänzungen."""
    teile = [aenderung.get("wunsch", "").strip()]
    for nummer, zusatz in enumerate(aenderung.get("ergaenzungen") or [], 1):
        text = str(zusatz.get("text") if isinstance(zusatz, dict) else zusatz).strip()
        art = zusatz.get("art") if isinstance(zusatz, dict) else ""
        if text and art in {"zurueckstellen", "wiederaufnehmen", "steuerung"}:
            continue
        if text:
            teile.append(f"Ergänzung {nummer}: {text}")
    zurueck = zurueckgestellt(aenderung.get("vertrag") or {})
    if zurueck:
        teile.append("ZURÜCKGESTELLT — jetzt NICHT umsetzen und nicht entfernen, was davon schon da ist:\n"
                     + "\n".join(f"- {k['beschreibung']}" for k in zurueck))
    return "\n\n".join(t for t in teile if t)


def vorbefunde(aenderung: dict[str, Any], grenze: int = 1800) -> str:
    """Was die bisherigen Versuche gezeigt haben — damit der nächste es anders macht."""
    zeilen = []
    for versuch in (aenderung.get("versuche") or [])[-3:]:
        if versuch.get("ergebnis") == "laeuft":
            continue
        teile = [f"Versuch {versuch.get('versuch')}: {versuch.get('ergebnis_text') or versuch.get('ergebnis', '')}"]
        for signal in versuch.get("signale") or []:
            if signal.get("stufe") == "hart" or signal.get("art") == "abgeschnitten":
                teile.append(f"  – {signal.get('text')} ({signal.get('technik', '')[:160]})")
        # Was inzwischen entfallen oder zurückgestellt ist, soll das Modell nicht
        # weiter jagen (29.09.2026: „Workspace“ landete sonst als Text in der App).
        ruhend = {k.get("beschreibung", "") for k in (aenderung.get("vertrag") or {}).get("kriterien") or []
                  if not aktiv(k)}
        offen = [o for o in versuch.get("offen") or [] if o not in ruhend]
        if offen:
            teile.append("  – nicht nachgewiesen: " + "; ".join(str(o)[:120] for o in offen[:6]))
        zeilen.append("\n".join(teile))
    text = "\n".join(zeilen)
    return text[:grenze]


# ------------------------------------------------------- Komplexitäts-Router
# Schwere Systemanforderungen — erkannt am einzelnen Kriterium des Root-Vertrags,
# nicht am ganzen Wunschtext. Eng gefasst: „schnell“ allein ist keine
# Leistungsanforderung, „Undo“ allein kein Architekturumbau.
_SCHWER: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("leistung", re.compile(r"performance|performant|\bleistung\b|millisekund|\b\d+\s*ms\b|einfrier|ruckel|"
                            r"skalier|latenz|\bfps\b", re.I)),
    ("grosse_daten", re.compile(r"\b\d{1,3}(?:[.\s]\d{3})+\b|\b\d{4,}\b(?=\s*(?:verkettete\s+)?(?:zellen|zeilen|"
                                r"einträge|datensätze|elemente|objekte|punkte|formeln|knoten))|große(?:n)? "
                                r"(?:datenmengen|bereiche|tabellen)|riesig", re.I)),
    ("virtualisierung", re.compile(r"virtualis|nur (?:die )?sichtbaren|lazy[- ]?load|nachladen beim scrollen", re.I)),
    ("mehrbenutzer", re.compile(r"multiplayer|mehrbenutzer|mehrere(?:n)? (?:nutzer|benutzer|tabs|geräte)|zwei tabs|"
                                r"kollaborat|echtzeit", re.I)),
    ("synchronisation", re.compile(r"synchronis|konflikt(?:lösung|auflösung)|\bmerge\b|\bcrdt\b|offline|reconnect",
                                   re.I)),
    ("engine", re.compile(r"parser|\bengine\b|abhängigkeitsgraph|dependency|interpreter|evaluator|"
                          r"zyklus(?:erkennung)?|zirkelbezug|inkrementell", re.I)),
    ("architektur", re.compile(r"architektur|grundlegend umbauen|neu strukturier|zustandsmodell|datenmodell|"
                               r"state-management", re.I)),
)
# Bedienung allein ist kein Architekturumbau: acht Buttons oder
# Gestaltungswünsche müssen auf dem schnellen Pfad bleiben.  Abläufe über
# mehrere Zustände und nicht direkt prüfbare Anforderungen sind dagegen ein
# brauchbarer, bewusst enger Strukturindikator.
STRUKTURELL = {"ablauf", "nicht_pruefbar"}


def schwere_kategorien(kriterium: dict[str, Any]) -> set[str]:
    text = " ".join([kriterium.get("beschreibung", ""), kriterium.get("id", "").replace("_", " "),
                     *(kriterium.get("stichworte") or [])])
    kategorien = {name for name, muster in _SCHWER if muster.search(text)}
    if kriterium.get("nachweis") == "nicht_pruefbar":
        kategorien.add("mehrbenutzer" if re.search(r"tab|nutzer|benutzer|multiplayer|gerät", text, re.I)
                       else "synchronisation")
    return kategorien


@dataclass
class Komplexitaet:
    gestuft: bool
    gruende: list[str] = field(default_factory=list)
    kategorien: list[str] = field(default_factory=list)
    pflicht: int = 0
    schwer: int = 0
    verhalten: int = 0

    def als_dict(self) -> dict[str, Any]:
        return {"gestuft": self.gestuft, "gruende": self.gruende, "kategorien": self.kategorien,
                "pflicht": self.pflicht, "schwer": self.schwer, "verhalten": self.verhalten}


def komplexitaet(vertrag: dict[str, Any], *, basis: int = 0, grenzen: Any = None) -> Komplexitaet:
    """Pre-Flight: schneller Einmal-Weg oder direkt geprüfte Schritte?

    Entschieden wird am Root-Vertrag, bevor das große Modell rechnet:
    - mindestens 8 Pflichtkriterien, von denen mindestens 4 echte Zustands- /
      Mehrschritt-Abläufe verlangen — einfache Bedienung und Gestaltung bleiben schnell,
    - mindestens 6 Pflichtkriterien und mindestens ein schweres Systemkriterium,
    - mindestens zwei schwere Kriterien aus verschiedenen Bereichen
      (etwa Leistung und Mehrbenutzer),
    - eine große bestehende Anwendung und ein grundlegender Umbau.
    """
    ab = getattr(grenzen, "stufen_ab_kriterien", 6)
    pflicht = pflichtkriterien(vertrag)
    schwere = {k["id"]: schwere_kategorien(k) for k in pflicht}
    schwer = [i for i, kategorien in schwere.items() if kategorien]
    kategorien = sorted({k for kategorie in schwere.values() for k in kategorie})
    strukturell = [k for k in pflicht if k.get("nachweis") in STRUKTURELL or schwere.get(k["id"])]
    gruende: list[str] = []
    if len(pflicht) >= 8 and len(strukturell) >= 4:
        gruende.append(f"{len(pflicht)} Pflichtkriterien, {len(strukturell)} davon strukturell")
    if len(pflicht) >= ab and schwer:
        gruende.append(f"{len(pflicht)} Pflichtkriterien mit schweren Systemanforderungen")
    if len(schwer) >= 2 and len(kategorien) >= 2:
        gruende.append("mehrere Kernsysteme: " + ", ".join(kategorien))
    if basis >= 60_000 and len(pflicht) >= 4 and schwer:
        gruende.append(f"große Anwendung ({basis // 1000} Tsd. Zeichen) mit grundlegender Änderung")
    return Komplexitaet(bool(gruende), gruende, kategorien, len(pflicht), len(schwer), len(strukturell))


def war_zu_gross(aenderung: dict[str, Any]) -> bool:
    """Brauchte ein früherer Versuch mehr als einen Schritt?"""
    for versuch in aenderung.get("versuche") or []:
        if versuch.get("gestuft"):
            return True
        for signal in versuch.get("signale") or []:
            if signal.get("art") in {"abgeschnitten", "konflikt"} or signal.get("stufe") == "hart":
                return True
    return False


# ------------------------------------------------------------------ Stufenplan
STUFENPLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stufen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "auftrag": {"type": "string"},
                    "kriterien": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titel", "auftrag", "kriterien"],
            },
        },
    },
    "required": ["stufen"],
}

STUFENPLAN_SYSTEM = """Du zerlegst eine große Änderung an einer Webanwendung (eine einzige HTML-Datei) in wenige Schritte, die nacheinander umgesetzt und jeweils im Browser geprüft werden.

Antworte nur mit JSON:
- stufen: 2 bis {max_stufen} Schritte in sinnvoller Reihenfolge (Grundlagen zuerst), jeweils
  - titel: 2–5 Wörter
  - auftrag: was genau in diesem Schritt geändert wird (2–4 Sätze, konkret, ohne Code)
  - kriterien: die IDs der Abnahmekriterien, die nach diesem Schritt erfüllt sein sollen

Jeder Schritt muss für sich klein genug sein, dass er in einer Antwort mit wenigen Änderungsblöcken umsetzbar ist. Jede Kriterien-ID kommt in mindestens einem Schritt vor. Erfinde keine neuen Kriterien."""


def stufenplan_normalisieren(roh: Any, vertrag: dict[str, Any], max_stufen: int = 8) -> dict[str, Any]:
    """Prüft den Plan gegen den Root-Vertrag; fehlende Kriterien wandern in den letzten Schritt."""
    daten = json_aus_antwort(roh)
    daten = daten if isinstance(daten, dict) else {}
    bekannt = [k["id"] for k in vertrag.get("kriterien") or []]
    stufen: list[dict[str, Any]] = []
    for eintrag in daten.get("stufen") or []:
        if not isinstance(eintrag, dict):
            continue
        titel = str(eintrag.get("titel") or "").strip()[:60]
        auftrag = str(eintrag.get("auftrag") or "").strip()[:1200]
        ids = [i for i in (eintrag.get("kriterien") or []) if isinstance(i, str) and i in bekannt]
        if not auftrag:
            continue
        stufen.append({"titel": titel or f"Schritt {len(stufen) + 1}", "auftrag": auftrag,
                       "kriterien": list(dict.fromkeys(ids))})
    stufen = stufen[:max_stufen]
    if len(stufen) < 2:
        return stufenplan_ohne_modell(vertrag, max_stufen)
    verteilt = {i for s in stufen for i in s["kriterien"]}
    fehlend = [i for i in bekannt if i not in verteilt]
    if fehlend:
        stufen[-1]["kriterien"].extend(fehlend)
    return {"stufen": stufen, "quelle": "modell"}


def stufenplan_ohne_modell(vertrag: dict[str, Any], max_stufen: int = 8) -> dict[str, Any]:
    """Rückfall: Je zwei Kriterien bilden einen Schritt, in der Reihenfolge des Vertrags."""
    kriterien = vertrag.get("kriterien") or []
    if not kriterien:
        return {"stufen": [], "quelle": "leer"}
    je = max(2, -(-len(kriterien) // max_stufen))
    stufen = []
    for start in range(0, len(kriterien), je):
        gruppe = kriterien[start:start + je]
        stufen.append({
            "titel": gruppe[0]["beschreibung"][:40],
            "auftrag": "Setze in diesem Schritt nur das Folgende um: "
                       + " ".join(k["beschreibung"] for k in gruppe),
            "kriterien": [k["id"] for k in gruppe],
        })
    return {"stufen": stufen, "quelle": "regel"}


async def stufenplan_erzeugen(zugang: Any, modell: str, *, wunsch: str, vertrag: dict[str, Any],
                              groesse: int, verbrauch: dict[str, int], max_stufen: int = 8) -> dict[str, Any]:
    kriterien = "\n".join(f"- {k['id']}: {k['beschreibung']}" for k in vertrag.get("kriterien") or [])
    nachrichten = [
        {"role": "system", "content": STUFENPLAN_SYSTEM.replace("{max_stufen}", str(max_stufen))},
        {"role": "user", "content": f"Änderungswunsch:\n{wunsch[:6000]}\n\nAbnahmekriterien:\n{kriterien}\n\n"
                                    f"Die Anwendung ist derzeit {groesse:,} Zeichen groß.".replace(",", ".")},
    ]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, STUFENPLAN_SCHEMA, temperatur=0.1, verbrauch=verbrauch)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 – dann eben der Plan nach Regel
        roh = {}
    return stufenplan_normalisieren(roh, vertrag, max_stufen)


@dataclass
class Versuchsprotokoll:
    """Was ein Versuch hinterlässt — für die Linie und die technischen Details."""
    versuch: int
    job: str
    text: str
    gestuft: bool = False
    signale: list[dict[str, Any]] = field(default_factory=list)
    patch: dict[str, Any] = field(default_factory=dict)
    stufen: list[dict[str, Any]] = field(default_factory=list)
    ergebnis: str = "laeuft"
    ergebnis_text: str = ""
    kandidat: int = 0
    offen: list[str] = field(default_factory=list)
    abnahme: dict[str, int] = field(default_factory=dict)
    reparaturen: int = 0

    def als_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
