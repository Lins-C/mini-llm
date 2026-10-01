# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Welche Dateien aus dem Asset-/Eingabeordner braucht dieser Auftrag — und wofür?

Grundsatz: Dateien werden **nicht** automatisch an das Modell geschickt. Eine
neue Datei im Ordner ist nur *verfügbar*. Erst ein Auftrag entscheidet, was
er braucht:

1. ausdrücklich genannt — `@logo.png`, `logo.png` oder eindeutig „das Logo“,
2. eindeutig verlangt — „nutze das vorhandene Bild“, „aus der CSV“,
   „daraus“ / „aus den Dateien“,
3. sonst nichts. „Baue einen Taschenrechner“ bekommt keine einzige Datei,
   auch wenn 25 im Ordner liegen.

Jede verwendete Datei bekommt eine Rolle:

  context       nur zum Verstehen (Anforderungen als PDF) — nicht ins Produkt
  data          Datenquelle des Produkts (CSV, Excel, JSON)
  asset         sichtbarer Teil des Produkts (Logo, Icon, Foto)
  project_file  bleibt eine eigene Datei im Projekt (Video, sehr große Daten)
  output        von JOSHI erzeugt (nur im Workspace)

Die Entscheidung ist deterministisch — ohne Modellaufruf, ohne Verzögerung.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from app.joshi.dateien import Datei, pruefsumme

ROLLEN = ("context", "data", "asset", "project_file", "output")
ROLLENTEXT = {"context": "Kontext", "data": "Datenquelle", "asset": "Asset", "project_file": "Projektdatei",
              "output": "Ergebnis"}

# Ein eingebettetes Bild über dieser Größe (nach dem Verkleinern) oder Daten
# über dieser Größe bleiben besser eigene Dateien.
GROSSE_DATEN = 2 * 1024 * 1024
GROSSES_BILD = 6 * 1024 * 1024

_BEZUG = {
    "bild": re.compile(r"\b(?:bild(?:er|es)?|foto(?:s)?|icon|app-icon|favicon|logo|grafik(?:en)?|illustration|"
                       r"hintergrundbild|hero(?:-?bild)?|produktbild(?:er)?|abbildung(?:en)?|image)\b", re.I),
    "daten": re.compile(r"\b(?:csv|excel|xlsx|tabelle(?:n)?|daten(?:quelle|satz|sätze)?|json|kundenliste|"
                        r"preisliste|liste der)\b", re.I),
    "dokument": re.compile(r"\b(?:pdf|dokument(?:e|en)?|anforderung(?:en)?|unterlagen|beschreibung|word-datei|"
                           r"docx|agb|handbuch|konzept)\b", re.I),
    "medien": re.compile(r"\b(?:video(?:s)?|audio|musik|film|clip)\b", re.I),
}
_ALLE = re.compile(r"\b(?:daraus|aus den dateien|alle(?:n)? dateien|den dateien|dem ordner|den eingaben|"
                   r"den assets|diese(?:n)? dateien|meine(?:n)? dateien|das material|dem material)\b", re.I)
_MEHRERE_BILDER = re.compile(r"\b(?:bilder|fotos|grafiken|abbildungen|produktbilder|illustrationen|images|"
                             r"alle bilder)\b", re.I)
_VORLAGE = re.compile(r"\b(?:vorlage|inspiration|als referenz|im stil|stil wie|design wie|nachbauen|orientier)", re.I)
_DOKUMENT_ALS_ASSET = re.compile(
    r"(?:in der anwendung (?:verfügbar|abrufbar|anzeigen)|zum download|herunterlad|verlink|einbinden|"
    r"öffnen können|mitliefern|beilegen)", re.I)


@dataclass
class Auswahl:
    datei: Datei
    rolle: str
    grund: str
    daten: bytes = b""
    sha256: str = ""

    def snapshot(self) -> dict[str, Any]:
        return {"name": self.datei.name, "art": self.datei.art, "rolle": self.rolle, "grund": self.grund,
                "groesse": self.datei.groesse, "geaendert": round(self.datei.geaendert, 3),
                "sha256": self.sha256, "zeit": int(time.time()), "quelle": "Asset-/Eingabeordner"}


def _wort(text: str, name: str) -> bool:
    return bool(re.search(rf"(?<![\w.@-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE))


def verweise(text: str, dateien: list[Datei]) -> dict[str, str]:
    """Ausdrücklich genannte Dateien: `@name`, `name.ext` oder ein eindeutiger Stamm."""
    gefunden: dict[str, str] = {}
    for datei in dateien:
        stamm = datei.name.rsplit(".", 1)[0]
        if re.search(rf"@{re.escape(datei.name)}(?![\w-])", text, re.IGNORECASE) or \
                re.search(rf"@{re.escape(stamm)}(?![\w.-])", text, re.IGNORECASE):
            gefunden[datei.name] = "@-Verweis"
        elif _wort(text, datei.name):
            gefunden[datei.name] = "im Auftrag genannt"
    # Der Stamm allein („das Logo“ für logo.png) nur, wenn er eindeutig ist.
    for datei in dateien:
        stamm = datei.name.rsplit(".", 1)[0].lower()
        if datei.name in gefunden or len(stamm) < 4:
            continue
        gleiche = [d for d in dateien if d.name.rsplit(".", 1)[0].lower() == stamm]
        if len(gleiche) == 1 and _wort(text, stamm):
            gefunden[datei.name] = "im Auftrag genannt"
    return gefunden


def rolle_bestimmen(datei: Datei, text: str) -> str:
    if datei.art == "medien":
        return "project_file"
    if datei.art == "bild":
        if datei.groesse > GROSSES_BILD:
            return "project_file"
        return "context" if _VORLAGE.search(text) and not re.search(r"\b(?:logo|icon|einbinden|verwende|nutze)\b",
                                                                     text, re.I) else "asset"
    if datei.art == "daten":
        return "project_file" if datei.groesse > GROSSE_DATEN else "data"
    if datei.art == "dokument":
        return "asset" if _DOKUMENT_ALS_ASSET.search(text) else "context"
    return "context"


def auswaehlen(text: str, dateien: list[Datei], deaktiviert: set[str] | None = None) -> list[Auswahl]:
    """Die Dateien, die dieser Auftrag braucht — sonst keine."""
    verfuegbar = [d for d in dateien if d.name not in (deaktiviert or set())]
    if not verfuegbar or not (text or "").strip():
        return []
    gruende = verweise(text, verfuegbar)
    # Ausdrücklich genannte Dateien gelten immer — auch wenn sie abgeschaltet
    # waren: Wer „@logo.png“ schreibt, meint diese Datei.
    for name, grund in verweise(text, dateien).items():
        gruende.setdefault(name, grund)
    if _ALLE.search(text):
        for datei in verfuegbar:
            gruende.setdefault(datei.name, "„daraus“ / alle Eingaben")
    else:
        # Ist eine Datei einer Art ausdrücklich genannt („das Logo“), zieht ein
        # allgemeines Wort derselben Art nicht noch alle anderen hinein.
        genannt = {d.art for d in dateien if d.name in gruende}
        for art, muster in _BEZUG.items():
            if art in genannt or not muster.search(text):
                continue
            passende = [d for d in verfuegbar if d.art == art and d.name not in gruende]
            if art == "bild" and len(passende) > 1 and not _MEHRERE_BILDER.search(text):
                # „das Bild als Icon“: eines ist gemeint. Bevorzugt die Datei,
                # deren Name zum Auftrag passt (icon, logo, hero …), sonst die neueste.
                worte = {w.lower() for w in re.findall(r"[a-zäöüß]{3,}", text.lower())}
                nach_name = [d for d in passende
                             if worte & set(re.split(r"[-_. ]+", d.name.lower().rsplit(".", 1)[0]))]
                passende = nach_name[:1] or sorted(passende, key=lambda d: -d.geaendert)[:1]
            for datei in passende:
                gruende[datei.name] = f"vom Auftrag verlangt ({art})"
    auswahl = []
    for datei in dateien:
        if datei.name in gruende:
            auswahl.append(Auswahl(datei, rolle_bestimmen(datei, text), gruende[datei.name]))
    return auswahl


def einlesen(auswahl: list[Auswahl], lesen: Any) -> list[Auswahl]:
    """Liest die ausgewählten Dateien einmal — das ist der Build-Snapshot.

    Was danach im Ordner passiert, ändert dieses Produkt nicht mehr.
    """
    for eintrag in auswahl:
        eintrag.daten = lesen(eintrag.datei.name)
        eintrag.sha256 = pruefsumme(eintrag.daten)
    return auswahl


def rollen_text(auswahl: list[Auswahl]) -> str:
    """Kurzer Hinweis für das Modell, wie es die Eingaben verwenden soll."""
    if not auswahl:
        return ""
    zeilen = ["Eingaben aus dem Asset-/Eingabeordner und ihre Rolle:"]
    for eintrag in auswahl:
        hinweis = {
            "context": "nur zum Verstehen — nicht in die Anwendung kopieren",
            "data": "Datenquelle — die Daten in die Anwendung übernehmen",
            "asset": "sichtbarer Teil der Anwendung — einbinden",
            "project_file": "bleibt eine eigene Projektdatei — nicht einbetten, nur darauf verweisen",
        }.get(eintrag.rolle, "")
        zeilen.append(f"- {eintrag.datei.name}: {ROLLENTEXT.get(eintrag.rolle, eintrag.rolle)} ({hinweis})")
    return "\n".join(zeilen)
