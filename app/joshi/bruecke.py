# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die Brücke zwischen Chat und JOSHI.

Chat → JOSHI: Aus einer Chat-Antwort (und der Frage davor) wird ein Auftrag.
Nur diese beiden Nachrichten und die dazu hochgeladenen Dokumente reisen mit,
nicht der ganze Verlauf.

JOSHI → Chat: Der Chat bekommt eine kompakte Produktübergabe — Zweck,
Funktionen, aktueller Stand, Versionen —, niemals das rohe HTML.
"""
from __future__ import annotations

import re
from typing import Any

from app.joshi.html_werk import html_aus_antwort

MAX_CHAT_TEXT = 12000
MAX_UEBERGABE = 4500


def chat_kontext(antwort: str, frage: str, chat_titel: str) -> str:
    teile = []
    if chat_titel:
        teile.append(f"Chat: {chat_titel.strip()[:120]}")
    if frage.strip():
        teile.append(f"Frage im Chat:\n{frage.strip()[:3000]}")
    if antwort.strip():
        text = antwort.strip()
        if len(text) > MAX_CHAT_TEXT:
            text = text[:MAX_CHAT_TEXT // 2] + "\n[… gekürzt …]\n" + text[-MAX_CHAT_TEXT // 2:]
        teile.append(f"Antwort im Chat:\n{text}")
    return "\n\n".join(teile)


def html_im_chat(antwort: str) -> str:
    """Enthält die Chat-Antwort schon eine vollständige Anwendung?"""
    if not re.search(r"<!doctype\s+html|<html\b", antwort or "", re.IGNORECASE):
        return ""
    auszug = html_aus_antwort(antwort)
    return auszug.html if auszug.vollstaendig and len(auszug.html) > 400 else ""


def auftrag_aus_chat(frage: str, antwort: str) -> str:
    anfang = re.sub(r"\s+", " ", frage or "").strip()[:300]
    if anfang:
        return f"Setze das Konzept aus dem Chat als benutzbare Anwendung um. Ausgangsfrage: {anfang}"
    return "Setze das Konzept aus dem Chat als benutzbare Anwendung um."


def aenderung_aus_chat(frage: str, antwort: str) -> str:
    """Vorschläge aus einem Chat über ein Produkt werden zum Änderungswunsch."""
    text = antwort.strip()
    if len(text) > 6000:
        text = text[:6000] + "\n[… gekürzt …]"
    wunsch = "Setze diese Vorschläge aus dem Chat in der Anwendung um:\n\n" + text
    if frage.strip():
        wunsch = f"Frage im Chat: {frage.strip()[:500]}\n\n" + wunsch
    return wunsch


def uebergabe(produkt: dict[str, Any], versionen: list[dict[str, Any]], gliederung: dict[str, Any]) -> str:
    """Kompakte Produktbeschreibung für den Chat (Markdown, ohne HTML)."""
    verstaendnis = produkt.get("verstaendnis") or {}
    nummer = produkt.get("version") or 0
    zeilen = [f"**JOSHI-Produkt: {produkt.get('titel')}** · Version {nummer}"]
    if verstaendnis.get("zweck"):
        zeilen.append(f"**Zweck:** {verstaendnis['zweck']}")
    auftrag = re.sub(r"\s+", " ", produkt.get("auftrag") or "")[:500]
    zeilen.append(f"**Ursprünglicher Auftrag:** {auftrag}")
    funktionen = verstaendnis.get("funktionen") or []
    if funktionen:
        zeilen.append("**Funktionen:**\n" + "\n".join(f"- {f}" for f in funktionen[:8]))
    ueberschriften = [u for u in gliederung.get("ueberschriften", []) if u][:8]
    if ueberschriften:
        zeilen.append("**Aufbau:** " + " · ".join(ueberschriften))
    knoepfe = [k for k in gliederung.get("knoepfe", []) if k][:10]
    if knoepfe:
        zeilen.append("**Bedienelemente:** " + ", ".join(knoepfe))
    felder = [f for f in gliederung.get("felder", []) if f.get("label")][:14]
    if felder:
        zeilen.append("**Aktueller Stand der Eingaben:**\n" + "\n".join(
            f"- {f['label']}: {f.get('wert') or '–'}" for f in felder))
    anzahl = gliederung.get("anzahl") or {}
    extras = [f"{anzahl[k]} {name}" for k, name in (("tabellen", "Tabelle(n)"), ("diagramme", "Diagramm(e)"),
                                                     ("bilder", "Bild(er)")) if anzahl.get(k)]
    if extras:
        zeilen.append("**Enthält:** " + ", ".join(extras))
    markdown = str(gliederung.get("markdown") or "").strip()
    if markdown:
        zeilen.append("**Sichtbarer Inhalt (Auszug):**\n" + markdown[:1400] + ("\n…" if len(markdown) > 1400 else ""))
    if versionen:
        verlauf = "; ".join(
            f"v{v['nummer']}: " + re.sub(r"\s+", " ", v.get("aenderung") or "")[:80] for v in versionen[-6:])
        zeilen.append(f"**Versionen:** {verlauf}")
    zeilen.append("_Die Anwendung selbst liegt in JOSHI; hier steht nur diese Beschreibung. "
                  "Änderungen setzt JOSHI um („Im Chat besprechen“ ⇄ „Mit JOSHI umsetzen“)._")
    text = "\n\n".join(zeilen)
    return text[:MAX_UEBERGABE]
