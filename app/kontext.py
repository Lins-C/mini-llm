# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Wie viel Dokument passt in eine Anfrage — gemessen am echten Kontextfenster.

Bisher galt eine feste Grenze von 18.000 Zeichen, egal ob das Modell 8.000 oder
eine Million Tokens verträgt. Ein eingefügter Text mit 26.482 Zeichen — rund
7.500 Tokens, viermal in das lokale 32k-Fenster passend — wurde deshalb in fünf
Abschnitte zerlegt und nacheinander mit je einem eigenen Modellaufruf
ausgewertet. Sechs Aufrufe statt einem.

Hier wird das Budget aus dem tatsächlichen Fenster abgeleitet:
- lokal aus dem Regler der Ollama-App (derzeit 32.768 Tokens),
- in der Cloud aus einer bewusst gesetzten Obergrenze pro Anfrage.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

# Deutsch braucht mehr Tokens je Zeichen als Englisch. Drei Zeichen je Token
# ist vorsichtig genug, dass nichts still abgeschnitten wird.
ZEICHEN_JE_TOKEN = 3.0
# Platz für Systemtexte, Verlauf, Frage und die Antwort selbst.
RESERVE_TOKENS = 8192
# Cloud-Modelle melden bis zu einer Million Tokens. So viel pro Anfrage zu
# schicken, macht jede Antwort langsam und teuer; 128k reichen für 350 Seiten Text.
CLOUD_KONTEXT = int(os.getenv("CLOUD_CONTEXT_TOKENS", "131072"))
# Ohne Einstellung startet Ollama mit einem kleinen Fenster. Lieber vorsichtig
# rechnen als ein Dokument unbemerkt kürzen.
LOKAL_RUECKFALL = 8192
OLLAMA_EINSTELLUNGEN = Path.home() / "Library/Application Support/Ollama/db.sqlite"

_zwischenspeicher: dict[str, tuple[float, int]] = {}


def ist_cloud_modell(name: str) -> bool:
    """glm-5.3-flash:cloud, gpt-oss:120b-cloud — gerechnet wird auf dem Server."""
    name = (name or "").strip().lower()
    return name.endswith(":cloud") or name.endswith("-cloud") or ":cloud-" in name


def lokales_kontextfenster() -> int:
    """Das Fenster, mit dem der lokale Ollama-Dienst tatsächlich arbeitet.

    Reihenfolge: ausdrückliche Umgebungsvariable, dann der Regler der
    Ollama-App, dann ein vorsichtiger Rückfall. Der Regler wird höchstens
    einmal pro Minute gelesen — eine Änderung wirkt ohne Neustart.
    """
    for variable in ("CHAT_NUM_CTX", "OLLAMA_CONTEXT_LENGTH"):
        wert = os.getenv(variable, "").strip()
        if wert.isdigit() and int(wert) >= 2048:
            return int(wert)
    jetzt = time.monotonic()
    gemerkt = _zwischenspeicher.get("lokal")
    if gemerkt and jetzt - gemerkt[0] < 60:
        return gemerkt[1]
    fenster = LOKAL_RUECKFALL
    try:
        verbindung = sqlite3.connect(f"file:{OLLAMA_EINSTELLUNGEN}?mode=ro", uri=True, timeout=1)
        try:
            zeile = verbindung.execute("select context_length from settings limit 1").fetchone()
        finally:
            verbindung.close()
        if zeile and isinstance(zeile[0], int) and zeile[0] >= 2048:
            fenster = zeile[0]
    except (sqlite3.Error, OSError):
        pass
    _zwischenspeicher["lokal"] = (jetzt, fenster)
    return fenster


def kontext_tokens(modell: str) -> int:
    return CLOUD_KONTEXT if ist_cloud_modell(modell) else lokales_kontextfenster()


def material_budget(modell: str) -> int:
    """So viele Zeichen Dokumenttext dürfen direkt in eine Anfrage."""
    return max(6000, int((kontext_tokens(modell) - RESERVE_TOKENS) * ZEICHEN_JE_TOKEN))


def parallelitaet(modell: str) -> int:
    """Wie viele Abschnittsanalysen gleichzeitig laufen dürfen.

    Cloud-Modelle rechnen auf fremden Servern — vier Anfragen gleichzeitig
    verkürzen die Wartezeit auf ein Viertel. Lokal teilt sich alles einen
    Speicher von 16 GB: Gleichzeitige Anfragen würden sich nur anstellen oder
    das Modell aus dem Speicher drängen.
    """
    return 4 if ist_cloud_modell(modell) else 1


def bloecke_bilden(
    abschnitte: list[tuple[str, str]],
    budget: int,
) -> list[list[tuple[str, str]]]:
    """Fasst aufeinanderfolgende Abschnitte zu möglichst wenigen Blöcken zusammen.

    Gespeichert bleiben die Dokumente in feinen Abschnitten — gut für die
    Suche nach der passenden Stelle. Verarbeitet werden sie in Blöcken, die
    das Fenster ausnutzen: Aus 85 Einzelaufrufen für 200 Seiten werden wenige.
    """
    bloecke: list[list[tuple[str, str]]] = []
    aktuell: list[tuple[str, str]] = []
    groesse = 0
    for label, text in abschnitte:
        if aktuell and groesse + len(text) > budget:
            bloecke.append(aktuell)
            aktuell, groesse = [], 0
        aktuell.append((label, text))
        groesse += len(text)
    if aktuell:
        bloecke.append(aktuell)
    return bloecke


def als_quellen(abschnitte: list[tuple[str, str]]) -> str:
    import json

    return "\n\n".join(
        f"<quelle name={json.dumps(label, ensure_ascii=False)}>\n{text}\n</quelle>"
        for label, text in abschnitte
    )


def kontext_optionen(modell: str) -> dict[str, int]:
    """num_ctx für lokale Modelle immer mitschicken.

    Gemessen: Ohne num_ctx lud Ollama das Modell mit 4.096 Tokens — der Regler
    der App gilt nicht für API-Aufrufe. Ein Text mit 26.482 Zeichen kam mit nur
    2.050 Tokens an; abgeschnitten war der Anfang, also die Frage des Nutzers.
    Das Modell folgte einer Anweisung am Textende und schrieb HTML. Mit
    num_ctx=32768 kamen alle 7.438 Tokens an, und die Antwort stimmte.

    Alle lokalen Aufrufe dieser App schicken denselben Wert — das heißt
    zugleich: kein Neuladen beim Wechsel zwischen Chat, Brief und Agent.
    """
    if ist_cloud_modell(modell):
        return {}
    return {"num_ctx": lokales_kontextfenster()}


# --- Welcher Weg für welches Material --------------------------------------
import re  # noqa: E402

INVENTAR = re.compile(r"(?i)\b(zip|archiv|inhalt|dateiliste|auflisten|enthalten|steckt)\b")
GESAMT = re.compile(
    r"(?i)\b(?:gesamt(?:e|en|er|es)?|vollständig|komplett|alle[nrsm]?|"
    r"chronologisch|zusammenfass\w*|vergleich\w*|gegenüberstell\w*|"
    r"zusammen(?:fassen|fassung)?|analysier\w*|transkrib\w*|extrahier\w*|"
    r"abschreib\w*|wortgetreu|originalgetreu|quelltext)\b"
)
VERNEINT = re.compile(r"(?i)\b(?:keine|nicht)\s+(?:kurze\s+)?zusammenfass\w*\b")


def ist_gesamtauftrag(frage: str) -> bool:
    """Braucht die Frage das ganze Dokument — oder nur die passenden Stellen?"""
    frage = frage or ""
    return bool(INVENTAR.search(frage) or GESAMT.search(VERNEINT.sub("", frage)))


def plane_material(
    kontexte: list[dict],
    frage: str,
    modell: str,
    rangliste,
    vorrang: set[str] | None = None,
) -> tuple[str, list[list[tuple[str, str]]], dict]:
    """Entscheidet, wie gespeicherte Dokumente in die Anfrage kommen.

    Rückgabe (weg, bloecke, kennzahlen):
      „direkt"  — genau ein Block, der ohne Umweg in die Anfrage geht,
      „bloecke" — mehrere Blöcke, je eine Analyse, danach die Antwort,
      „leer"    — kein Material.

    Reihenfolge der Versuche:
      1. Alles passt ins Fenster → vollständig, ohne einen Zusatzaufruf.
      2. Die neuen Dokumente passen → vollständig, ältere nach Relevanz.
      3. Gezielte Frage → die passendsten Stellen, so viele hineinpassen.
      4. Gesamtauftrag über zu viel Text → wenige große Blöcke.
    """
    from app.intelligence import context_source_text, split_text

    budget = material_budget(modell)
    vorrang = {str(eintrag) for eintrag in (vorrang or set())}
    eindeutig: list[dict] = []
    gesehen: set[str] = set()
    for kontext in kontexte or []:
        schluessel = str(kontext.get("id") or "") or f"{kontext.get('name')}#{len(eindeutig)}"
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        eindeutig.append(kontext)
    if not eindeutig:
        return "leer", [], {"budget": budget}

    vorne = [k for k in eindeutig if str(k.get("id") or "") in vorrang]
    hinten = [k for k in eindeutig if k not in vorne]

    def ganz(liste: list[dict]) -> list[tuple[str, str]]:
        return [
            (str(k.get("name") or "Dokument"), text)
            for k in liste
            if (text := context_source_text(k))
        ]

    alle = ganz(vorne + hinten)
    gesamt = sum(len(text) for _, text in alle)
    kennzahlen = {"budget": budget, "zeichen": gesamt, "dokumente": len(alle)}
    if alle and gesamt <= budget:
        return "direkt", [alle], {**kennzahlen, "weg": "vollständig"}

    neu = ganz(vorne)
    neu_zeichen = sum(len(text) for _, text in neu)
    if neu and neu_zeichen <= budget:
        rest = rangliste(hinten, frage, budget_chars=budget - neu_zeichen) if hinten else []
        return "direkt", [neu + list(rest)], {
            **kennzahlen, "weg": "neue Dokumente vollständig, ältere nach Relevanz",
        }

    if not ist_gesamtauftrag(frage):
        auswahl = rangliste(eindeutig, frage, priority_ids=vorrang, budget_chars=budget)
        return "direkt", [list(auswahl)], {**kennzahlen, "weg": "passendste Stellen"}

    abschnitte: list[tuple[str, str]] = []
    for name, text in ganz(vorne or eindeutig):
        teile = split_text(text, size=budget, overlap=400)
        abschnitte += [
            (f"{name} – Block {nummer}/{len(teile)}", teil)
            for nummer, teil in enumerate(teile, 1)
        ]
    bloecke = bloecke_bilden(abschnitte, budget)
    return "bloecke", bloecke, {**kennzahlen, "weg": "Blockanalyse", "bloecke": len(bloecke)}
