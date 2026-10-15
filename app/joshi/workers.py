# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Begrenzte Prüf-Worker; nur gemessene Browserdaten, keine Modellverbindungen.

Die Worker prüfen konkrete Eigenschaften und liefern entweder einen Beleg oder
einen gezielten Arbeitsauftrag. Fehlende Messwerte sind kein Produktfehler.
"""
from __future__ import annotations

import re
from typing import Any


def inhaltspruefung(kriterium: dict[str, Any], beweise: dict[str, Any]):
    text = str(kriterium.get("beschreibung") or "").lower()
    if not re.search(r"geschicht|lesetext|artikeltext", text):
        return None
    if not re.search(r"länger|laenger|mehrere absätze|mehr text", text):
        return None
    jetzt = beweise.get("leseinhalt") or {}
    vorher = (beweise.get("vorher") or {}).get("leseinhalt") or {}
    if not jetzt:
        return "unbeweisbar", "Textbereich wurde noch nicht im Browser vermessen", ""
    woerter, absaetze = int(jetzt.get("woerter") or 0), int(jetzt.get("absaetze") or 0)
    alt = int(vorher.get("woerter") or 0)
    if re.search(r"länger|laenger|mehr text", text) and not alt:
        return "unbeweisbar", f"{woerter} Wörter gemessen; Vergleichswert der Ausgangsfassung fehlt", ""
    genug = absaetze >= 3 and (woerter >= max(alt + 50, int(alt * 1.2)) if alt else woerter >= 150)
    return ("erfuellt" if genug else "fehlt",
            f"Lesetext: {woerter} Wörter in {absaetze} Absätzen; vorher {alt} Wörter. "
            "Gezielt den Lesetext erweitern, keine Prüfbegriffe als UI-Text ergänzen.", "text" if genug else "")


def layoutpruefung(kriterium: dict[str, Any], beweise: dict[str, Any]):
    text = str(kriterium.get("beschreibung") or "").lower()
    if kriterium.get("nachweis") != "gestaltung" or not re.search(r"geschicht|lesetext", text):
        return None
    if not re.search(r"breit|großen.*bereich|grossen.*bereich", text):
        return None
    werte = beweise.get("leseinhalt") or {}
    if not werte:
        return "unbeweisbar", "Der sichtbare Lesebereich wurde noch nicht vermessen", ""
    breite = int(werte.get("breite") or 0)
    return ("erfuellt" if breite >= 55 else "fehlt",
            f"Lesebereich {werte.get('element')}: {breite} % der Browserbreite; "
            "für einen breiten Lesebereich werden mindestens 55 % benötigt.", "stil" if breite >= 55 else "")


def knopfpruefung(kriterium: dict[str, Any], beweise: dict[str, Any]):
    text = str(kriterium.get("beschreibung") or "").lower()
    if not re.search(r"\bki[- ]knopf|\bki[- ]button", text) or not re.search(r"schlicht|einfach.*gestalt", text):
        return None
    knoepfe = [b for b in (beweise.get("gestaltung") or {}).get("bedienelemente") or []
               if re.search(r"\bki\b", str(b.get("name") or ""), re.I)]
    if len(knoepfe) != 1:
        return "unbeweisbar", "KI-Knopf nicht eindeutig als einzelnes Bedienelement vermessen", ""
    b = knoepfe[0]
    schlicht = not b.get("verlauf") and not b.get("schatten") and int(b.get("kinder") or 0) <= 1
    return ("erfuellt" if schlicht else "fehlt",
            f"KI-Knopf gemessen: Hintergrundbild={bool(b.get('verlauf'))}, "
            f"Schatten={bool(b.get('schatten'))}, Kindelemente={b.get('kinder', 0)}",
            "stil" if schlicht else "")


def szenario_pruefen(szenario: dict[str, Any], kriterium: dict[str, Any],
                     gliederung: dict[str, Any]) -> bool:
    """Ein Zeitbudget verlangt weder eine erfundene Uhr noch bloß einen schnellen Klick."""
    text = str(kriterium.get("beschreibung") or "").lower()
    if not re.search(r"(?:lese|aktions|geschichte).*zeit|minuten.*(?:durchlaufen|geschichte)|geschichte.*minuten", text):
        return True
    # Ein initial sichtbarer Countdown belegt keine vollständige Lese-/Aktionszeit.
    # Dafür braucht es eine eigene vollständige Ablaufmessung mit Zeitmodell.
    return False


def reparaturauftrag(bericht: dict[str, Any], vertrag: dict[str, Any]) -> str:
    """Nur offene Anforderungen, konkrete Messwerte, keine ungezielte Neuschreibung."""
    offen = [e for e in bericht.get("ergebnisse") or []
             if e.get("pflicht") and e.get("status") in {"FAIL", "NOT_PROVEN"}]
    if not offen:
        return ""
    zeilen = ["Gezielter Reparatur-Worker: Erhalte alle bereits belegten Funktionen."]
    for e in offen:
        zeilen.append(f"- {e.get('id')}: {e.get('beschreibung')}\n  Browserbeleg: {e.get('begruendung', '')}")
    zeilen.append("Ändere die Funktion bzw. das Layout, nicht die Formulierung der Prüfanweisung. "
                  "Ein Zeitbudget verlangt keinen Countdown mit exakt diesem Startwert. "
                  "Keine vollständige Neugestaltung für eine einzelne offene Anforderung.")
    return "\n".join(zeilen)
