# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Welcher Chatverlauf in eine Anfrage kommt — und in welcher Form.

Beobachtet im MediFlow-Chat (glm-5.3-flash, sieben Runden an einer HTML-Seite):
Beim letzten Schritt sah das Modell 32.000 Zeichen Verlauf. Jede HTML-Fassung
war auf ihre letzten 12.000 Zeichen gekürzt — ohne <style>, ohne Glas-Effekt —,
und der erste Auftrag („vista Glass Optik") fehlte ganz. Das Modell erfand
daraufhin ein neues Design mit weißen Karten.

Drei Regeln beheben das:
1. Die jüngste Fassung eines Artefakts (HTML-Seite, längerer Codeblock) bleibt
   ganz. Ältere Fassungen desselben Artefakts werden durch einen Hinweis
   ersetzt — sie sind überholt und kosten nur Platz.
2. Der erste Auftrag des Chats bleibt immer dabei. Dort stehen die
   Anforderungen, auf die sich jedes spätere „mach noch …" bezieht.
3. Gekürzt wird in der Mitte, nicht vorn: Anfang und Ende einer Nachricht
   bleiben lesbar. Das Budget folgt dem Kontextfenster des Modells.
"""
from __future__ import annotations

import re
from typing import Any

from app.kontext import RESERVE_TOKENS, ZEICHEN_JE_TOKEN, ist_cloud_modell, kontext_tokens

CODEBLOCK = re.compile(r"```([\w+#.-]*)[ \t]*\n(.*?)```", re.S)
# Kleine Schnipsel gehören zur Antwort, sie sind keine eigene Fassung einer Datei.
ARTEFAKT_MINDESTLAENGE = 1500
# Der erste Auftrag trägt die Anforderungen; mehr als das braucht es von ihm nicht.
ERSTER_AUFTRAG_GRENZE = 4000
# Die jüngste Fassung darf den Verlauf nicht allein belegen — die letzten
# Wortwechsel erklären, was jetzt an ihr geändert werden soll.
ARTEFAKT_ANTEIL = 0.7
VERLAUF_ANTEIL = 0.45
VERLAUF_MINIMUM = 8_000
VERLAUF_MAXIMUM = 100_000
# Kommt ein Dokument dazu, braucht es den Platz im Fenster — lokal knapp, in
# der Cloud mit mehr Luft.
VERLAUF_MIT_DOKUMENT = 20_000
VERLAUF_MIT_DOKUMENT_CLOUD = 60_000

STOPPWOERTER = {
    "aber", "auch", "bitte", "dann", "dass", "deine", "einen", "einer",
    "eine", "haben", "kannst", "machen", "oder", "soll", "über", "wieder",
}


def _zahl(wert: int) -> str:
    return f"{wert:,}".replace(",", ".")


def artefakt_art(sprache: str, code: str) -> str:
    """Welche Datei ein Codeblock ist — leer bei einem bloßen Schnipsel."""
    if len(code) < ARTEFAKT_MINDESTLAENGE:
        return ""
    kopf = code.lstrip()[:300].lower()
    if kopf.startswith(("<!doctype html", "<html")):
        return "html"
    sprache = (sprache or "").lower()
    if sprache in {"html", "htm", "xhtml"}:
        # Ein langer HTML-Ausschnitt ohne Dokumentrahmen ist keine ganze Seite
        # und darf eine ältere ganze Seite nicht verdrängen.
        return "html-ausschnitt"
    return sprache or "code"


def ueberholte_fassungen_ersetzen(nachrichten: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ersetzt ältere Fassungen desselben Artefakts durch einen kurzen Hinweis."""
    gesehen: set[str] = set()
    ergebnis = [dict(eintrag) for eintrag in nachrichten]
    for eintrag in reversed(ergebnis):
        if eintrag.get("role") != "assistant":
            continue
        inhalt = str(eintrag.get("content") or "")
        bloecke = list(CODEBLOCK.finditer(inhalt))
        if not bloecke:
            continue
        teile: list[str] = []
        ende = len(inhalt)
        for treffer in reversed(bloecke):
            art = artefakt_art(treffer.group(1), treffer.group(2))
            ersatz = treffer.group(0)
            if art and art in gesehen:
                name = "HTML-Seite" if art == "html" else f"{art}-Datei"
                ersatz = (
                    f"[Ältere Fassung dieser {name} ({_zahl(len(treffer.group(2)))} Zeichen) "
                    "ausgelassen — überholt durch die neuere Fassung weiter unten im Verlauf.]"
                )
            elif art:
                gesehen.add(art)
            teile.append(inhalt[treffer.end():ende])
            teile.append(ersatz)
            ende = treffer.start()
        teile.append(inhalt[:ende])
        eintrag["content"] = "".join(reversed(teile))
    return ergebnis


def kuerzen(text: str, grenze: int) -> str:
    """Kürzt in der Mitte: Anfang und Ende bleiben lesbar."""
    if grenze <= 0:
        return ""
    if len(text) <= grenze:
        return text
    nutzbar = max(0, grenze - 60)
    kopf = int(nutzbar * 0.6)
    schwanz = nutzbar - kopf
    ausgelassen = len(text) - kopf - schwanz
    return (
        text[:kopf]
        + f"\n\n[… {_zahl(ausgelassen)} Zeichen ausgelassen …]\n\n"
        + (text[-schwanz:] if schwanz else "")
    )


def verlauf_budget(modell: str, mit_dokument: bool = False) -> int:
    """So viele Zeichen Verlauf passen neben Auftrag und Antwort ins Fenster."""
    tokens = kontext_tokens(modell)
    budget = int(max(0, tokens - RESERVE_TOKENS) * ZEICHEN_JE_TOKEN * VERLAUF_ANTEIL)
    budget = max(VERLAUF_MINIMUM, min(VERLAUF_MAXIMUM, budget))
    if mit_dokument:
        budget = min(
            budget,
            VERLAUF_MIT_DOKUMENT_CLOUD if ist_cloud_modell(modell) else VERLAUF_MIT_DOKUMENT,
        )
    return budget


def _relevante_aeltere(aeltere: list[dict[str, Any]], prompt: str) -> list[int]:
    begriffe = {
        wort for wort in re.findall(r"[\wäöüß-]{4,}", prompt.lower())
        if wort not in STOPPWOERTER
    }
    bewertet: list[tuple[int, int]] = []
    for index, eintrag in enumerate(aeltere):
        inhalt = str(eintrag.get("content") or "").lower()
        punkte = sum(min(4, inhalt.count(begriff)) for begriff in begriffe)
        if punkte:
            bewertet.append((punkte, index))
    return [index for _, index in sorted(bewertet, key=lambda e: (-e[0], -e[1]))[:2]]


def _juengstes_artefakt(liste: list[dict[str, Any]], auswahl: set[int]) -> int | None:
    for index in sorted(auswahl, reverse=True):
        eintrag = liste[index]
        if eintrag.get("role") != "assistant":
            continue
        if any(artefakt_art(t.group(1), t.group(2)) for t in CODEBLOCK.finditer(str(eintrag.get("content") or ""))):
            return index
    return None


def verlauf_auswaehlen(
    nachrichten: list[dict[str, Any]],
    prompt: str,
    *,
    budget: int,
    juengste: int = 8,
) -> list[dict[str, Any]]:
    """Wählt aus dem Verlauf, was das Modell für diese Anfrage braucht."""
    if not nachrichten:
        return []
    liste = ueberholte_fassungen_ersetzen(nachrichten)
    anzahl = len(liste)
    aelter_ende = max(0, anzahl - juengste)
    auswahl = set(range(aelter_ende, anzahl))
    for index in _relevante_aeltere(liste[:aelter_ende], prompt):
        auswahl.add(index)
        if liste[index].get("role") == "user" and index + 1 < aelter_ende:
            auswahl.add(index + 1)
        elif index > 0 and liste[index].get("role") == "assistant":
            auswahl.add(index - 1)
    erster = next((i for i, e in enumerate(liste) if e.get("role") == "user"), None)
    erster_ist_alt = erster is not None and erster < aelter_ende
    if erster is not None:
        auswahl.add(erster)

    # Zuteilung: erst der alte erste Auftrag (knapp), dann die Nachricht mit der
    # jüngsten ganzen Fassung, danach alles Übrige von neu nach alt.
    reihenfolge = sorted(auswahl, reverse=True)
    artefakt = _juengstes_artefakt(liste, auswahl)
    if artefakt is not None:
        reihenfolge.remove(artefakt)
        reihenfolge.insert(0, artefakt)
    if erster_ist_alt:
        reihenfolge.remove(erster)
        reihenfolge.insert(0, erster)

    rest = budget
    inhalte: dict[int, str] = {}
    for index in reihenfolge:
        text = str(liste[index].get("content") or "")
        grenze = rest
        if index == erster and erster_ist_alt:
            grenze = min(rest, ERSTER_AUFTRAG_GRENZE)
        elif index == artefakt:
            grenze = min(rest, int(budget * ARTEFAKT_ANTEIL))
        if grenze < 300:
            continue
        gekuerzt = kuerzen(text, grenze)
        if gekuerzt.strip():
            inhalte[index] = gekuerzt
            rest -= len(gekuerzt)
    return [
        {"role": liste[index]["role"], "content": inhalte[index]}
        for index in sorted(inhalte)
    ]


TITEL = re.compile(r"<title>(.*?)</title>", re.I | re.S)


def _kurzinhalt(text: str, grenze: int = 180) -> str:
    """Eine Nachricht in einer Zeile. Erzeugte Dateien stehen vorn — sonst fiel
    „[HTML-Datei „Dackel Run“]" hinter dem Einleitungssatz der Kürzung zum Opfer."""
    marken: list[str] = []

    def ersatz(treffer: re.Match) -> str:
        sprache, code = treffer.group(1), treffer.group(2)
        art = artefakt_art(sprache, code)
        if not art:
            return " [Code-Ausschnitt] "
        if art == "html":
            titel = TITEL.search(code)
            titeltext = re.sub(r"\s+", " ", titel.group(1)).strip()[:60] if titel else ""
            marken.append(f"[HTML-Datei{' „' + titeltext + '“' if titeltext else ''}, {_zahl(len(code))} Zeichen]")
        else:
            marken.append(f"[{art}-Code, {_zahl(len(code))} Zeichen]")
        return " "

    flach = CODEBLOCK.sub(ersatz, text or "")
    flach = re.sub(r"\[Ältere Fassung dieser ([^\]]*?) \([\d.]+ Zeichen\)[^\]]*\]", r"[ältere \1]", flach)
    flach = re.sub(r"[#*_>`|]+", " ", flach)
    flach = re.sub(r"\s+", " ", flach).strip()
    if len(flach) > grenze:
        flach = flach[: grenze - 1].rstrip() + "…"
    return " ".join([*marken, flach]).strip()


def verlauf_kurzfassung(
    alle: list[dict[str, Any]],
    ausgewaehlt: list[dict[str, Any]],
    grenze: int = 3500,
) -> str:
    """Der ganze Gesprächsverlauf in Kurzform — nur wenn die Auswahl etwas weglässt.

    ministral-3:8b beantwortete „worum ging es zu Beginn des Chats?" allein aus
    zwei angehängten Dateien. Das Mario- und das Dackel-Spiel davor standen nur
    gekürzt oder gar nicht mehr in der Anfrage.
    """
    if len(alle) < 4:
        return ""
    im_wortlaut = {str(eintrag.get("content") or "") for eintrag in ausgewaehlt}
    weggelassen = len(ausgewaehlt) < len(alle) or any(
        str(eintrag.get("content") or "") not in im_wortlaut for eintrag in alle
    )
    if not weggelassen:
        return ""
    zeilen: list[str] = []
    vorher = ("", "")
    for nummer, eintrag in enumerate(alle, 1):
        rolle = "Nutzer" if eintrag.get("role") == "user" else "Assistent"
        inhalt = _kurzinhalt(str(eintrag.get("content") or ""))
        if (rolle, inhalt) == vorher and zeilen:
            # Derselbe Auftrag nach einem Fehler erneut gesendet: eine Zeile.
            zeilen[-1] = re.sub(r"^(\d+)\.(?:–\d+\.)? ", rf"\g<1>.–{nummer}. ", zeilen[-1], count=1)
            continue
        zeilen.append(f"{nummer}. {rolle}: {inhalt}")
        vorher = (rolle, inhalt)
    if len("\n".join(zeilen)) > grenze:
        # Anfang und jüngste Schritte bleiben, die Mitte weicht.
        kopf = zeilen[:3]
        rest = grenze - len("\n".join(kopf)) - 40
        schwanz: list[str] = []
        for zeile in reversed(zeilen[3:]):
            if rest - len(zeile) - 1 < 0:
                break
            schwanz.insert(0, zeile)
            rest -= len(zeile) + 1
        ausgelassen = len(zeilen) - len(kopf) - len(schwanz)
        zeilen = kopf + ([f"… ({ausgelassen} weitere Nachrichten)"] if ausgelassen else []) + schwanz
    return (
        "GESPRÄCHSVERLAUF DIESES CHATS IN KURZFORM (älteste Nachricht zuerst). Die "
        "jüngsten Nachrichten folgen im Wortlaut. Fragen danach, worum es im Chat "
        "ging oder wo ihr gerade steht, beantwortest du aus diesem Verlauf:\n"
        + "\n".join(zeilen)
    )
