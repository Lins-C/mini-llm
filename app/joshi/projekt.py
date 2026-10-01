# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Workspace-Projekte: nur wenn nötig, immer dokumentiert.

SINGLE FILE FIRST — INBOUND WHEN USEFUL — WORKSPACE ONLY WHEN NECESSARY.

Ein JOSHI-Produkt ist zuerst eine einzige, weitergebbare HTML-Datei. Ein
Projektordner entsteht erst, wenn die Aufgabe es wirklich verlangt: viele oder
große Assets, Mediendateien, große Datenmengen, eine ausdrücklich mehrteilige
Struktur — oder ein Prototyp, der zu einem Projekt herangewachsen ist. Die
Entscheidung folgt der realen Struktur, nicht der Zahl der Tokens.

Ein Projekt im Workspace enthält nur, was es braucht:

    <projekt>/
      index.html          die Anwendung (Bilder als relative Verweise auf assets/)
      assets/             nur wenn Bilder oder Mediendateien dazugehören
      data/               nur wenn Datenquellen dazugehören
      JOSHI_PROJECT.md    technische und inhaltliche Dokumentation (von JOSHI gepflegt)
      README.md           kurzer Einstieg (einmal angelegt, danach dem Nutzer überlassen)

Eingabedateien werden als Kopie des Build-Snapshots übernommen — nie das
Original im Asset-/Eingabeordner weiterverwendet.
"""
from __future__ import annotations

import datetime
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.joshi.dateien import Wurzel
from app.joshi.eingaben import ROLLENTEXT, Auswahl
from app.joshi.html_werk import SICHERHEITSRICHTLINIE, asset_verweise, export_dokument

MB = 1024 * 1024

_STRUKTUR: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mehrteilig", re.compile(r"mehrteilig|mehrere(?:n)? (?:seiten|teile|ansichten|module|bereiche)|"
                              r"\bmodul(?:e|en)\b", re.I)),
    ("Verwaltung", re.compile(r"verwaltungs(?:system|oberfläche)|\badmin(?:bereich|-bereich)?\b|\bbackend\b|"
                              r"mit verwaltung", re.I)),
    ("Dokumentation", re.compile(r"\bdokumentation\b|\bhandbuch\b", re.I)),
    ("Weiterentwicklung", re.compile(r"weiterentwickel|projektstruktur|separate(?:n)? dateien|eigene dateien", re.I)),
    ("großes System", re.compile(r"vollständig(?:e|en|es)? (?:system|verwaltung|webshop|shop|plattform|"
                                 r"produktkatalog)|größere(?:n)? (?:anwendung|projekt)", re.I)),
    ("Datenimport", re.compile(r"datenimport|csv-import|import(?:funktion)? für|mehrere (?:dokumente|dateien)", re.I)),
)
_MENGE = re.compile(r"\b(\d{1,3}(?:[.\s]\d{3})+|\d{2,})\s*(?:produkt|artikel)?(?:bilder|fotos|dateien|dokumente|"
                    r"seiten|videos)\b", re.I)


@dataclass
class Bedarf:
    noetig: bool
    punkte: int
    gruende: list[str] = field(default_factory=list)

    def als_dict(self) -> dict[str, Any]:
        return {"noetig": self.noetig, "punkte": self.punkte, "gruende": self.gruende}


def bedarf(text: str, auswahl: list[Auswahl], *, bestehend_zeichen: int = 0,
           anhaenge: list[dict[str, Any]] | None = None) -> Bedarf:
    """Braucht dieses Vorhaben einen Projekt-Workspace — oder passt es in eine Datei?

    Uploads gehören zur Entscheidung genauso wie Dateien aus dem Asset-Ordner.
    Die frühere Prüfung sah nur den bereits gelesenen Eingabeordner; dadurch
    konnte ein Auftrag mit vielen direkt angehängten Bildern fälschlich als
    Einzeldatei starten.
    """
    punkte = 0
    gruende: list[str] = []
    bilder = [a for a in auswahl if a.datei.art == "bild" and a.rolle == "asset"]
    bildbytes = sum(a.datei.groesse for a in bilder)
    daten = sum(a.datei.groesse for a in auswahl if a.rolle == "data")
    projektdateien = [a for a in auswahl if a.rolle == "project_file"]
    anhaenge = anhaenge or []
    anhang_bilder = [a for a in anhaenge if a.get("art") == "bild"]
    anhang_bytes = sum(int(a.get("groesse") or 0) for a in anhaenge)
    anhang_medien = [a for a in anhaenge if a.get("art") == "medien"]
    if anhang_medien:
        punkte += 3
        gruende.append(f"{len(anhang_medien)} angehängte Mediendatei(en) sollten eigene Dateien bleiben")
    if len(anhang_bilder) > 12 or sum(int(a.get("groesse") or 0) for a in anhang_bilder) > 8 * MB:
        punkte += 3
        gruende.append(f"{len(anhang_bilder)} angehängte Bilder")
    elif len(anhang_bilder) >= 4:
        punkte += 1
        gruende.append(f"{len(anhang_bilder)} angehängte Bilder")
    if len(anhaenge) >= 5:
        punkte += 1
        gruende.append(f"{len(anhaenge)} angehängte Dateien")
    if anhang_bytes > 20 * MB:
        punkte += 2
        gruende.append(f"angehängte Dateien mit zusammen {anhang_bytes / MB:.1f} MB")
    if projektdateien:
        punkte += 3
        gruende.append(f"{len(projektdateien)} große oder Mediendatei(en) sollten eigene Dateien bleiben")
    if len(bilder) > 12 or bildbytes > 8 * MB:
        punkte += 3
        gruende.append(f"{len(bilder)} Bilder mit zusammen {bildbytes / MB:.1f} MB")
    elif len(bilder) >= 4:
        punkte += 1
        gruende.append(f"{len(bilder)} Bilder")
    if daten > 300 * 1024:
        punkte += 1
        gruende.append(f"Daten mit {daten / MB:.1f} MB")
    if len(auswahl) >= 5:
        punkte += 1
        gruende.append(f"{len(auswahl)} Eingabedateien")
    menge = _MENGE.search(text or "")
    if menge and int(re.sub(r"\D", "", menge.group(1)) or 0) >= 20:
        punkte += 3
        gruende.append(f"„{menge.group(0)}“")
    treffer = [name for name, muster in _STRUKTUR if muster.search(text or "")]
    if treffer:
        punkte += 2 * len(treffer)
        gruende.append("Projektstruktur verlangt: " + ", ".join(treffer))
    if bestehend_zeichen > 120_000:
        punkte += 2
        gruende.append(f"die Anwendung hat schon {bestehend_zeichen // 1000} Tsd. Zeichen")
    return Bedarf(punkte >= 3, punkte, gruende)


EMPFEHLUNG_NEU = ("Dieses Vorhaben wird größer als eine typische JOSHI-Einzelanwendung. "
                  "Ein Projekt-Workspace würde die weitere Entwicklung erleichtern.")
EMPFEHLUNG_BESTEHEND = ("Dieses Produkt ist inzwischen umfangreich genug, dass ein Workspace sinnvoll wäre. "
                        "Es kann in einen Workspace überführt werden.")


# ------------------------------------------------------------------ Schreiben
def _slug(text: str) -> str:
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    text = "".join(ersatz.get(z, z) for z in (text or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or "joshi-projekt"


def _dateiname(name: str) -> str:
    stamm, _, endung = (name or "datei").rpartition(".")
    stamm = _slug(stamm or name)
    endung = re.sub(r"[^a-z0-9]", "", endung.lower())[:6]
    return f"{stamm}.{endung}" if endung else stamm


def ordner_waehlen(wurzel: Wurzel, titel: str, vorhanden: str = "") -> str:
    """Ein eigener Ordner je Produkt — nie ein fremder, schon vorhandener."""
    if vorhanden:
        return vorhanden
    basis = _slug(titel)
    name, nummer = basis, 2
    while wurzel.existiert(name):
        name, nummer = f"{basis}-{nummer}", nummer + 1
    return name


def _eindeutig(name: str, belegt: set[str]) -> str:
    stamm, punkt, endung = name.rpartition(".")
    kandidat, nummer = name, 2
    while kandidat in belegt:
        kandidat = f"{stamm}-{nummer}{punkt}{endung}" if punkt else f"{name}-{nummer}"
        nummer += 1
    belegt.add(kandidat)
    return kandidat


WORKSPACE_RICHTLINIE = (SICHERHEITSRICHTLINIE
                        .replace("img-src data: blob:", "img-src data: blob: 'self' file:")
                        .replace("media-src data: blob:", "media-src data: blob: 'self' file:"))


def _datum(zeit: float | None = None) -> str:
    return datetime.datetime.fromtimestamp(zeit or time.time()).strftime("%d.%m.%Y %H:%M")


def dokumentation(*, produkt: dict[str, Any], version: dict[str, Any], versionen: list[dict[str, Any]],
                  dateien: dict[str, list[str]], eingaben: list[dict[str, Any]], html: str,
                  notizen: str = "") -> str:
    """JOSHI_PROJECT.md — aus dem aktuellen Stand fortgeschrieben, eigene Notizen bleiben."""
    verstaendnis = produkt.get("verstaendnis") or {}
    pruefung = version.get("pruefung") or {}
    zeilen = [f"# {produkt.get('titel') or 'JOSHI-Projekt'}", "",
              "> Von JOSHI gepflegt. Eigene Notizen gehören unter „## Notizen“ — dieser Abschnitt bleibt "
              "bei jeder Aktualisierung erhalten.", ""]
    zeilen += ["## Zweck", verstaendnis.get("zweck") or produkt.get("auftrag", "")[:600] or "–", ""]
    erste = versionen[0] if versionen else version
    zeilen += ["## Ursprung", f"Entstanden aus dem Auftrag: „{(produkt.get('auftrag') or '').strip()[:800]}“",
               f"Erste Version: {_datum(erste.get('erstellt'))}", ""]
    zeilen += ["## Aktueller Funktionsumfang"]
    zeilen += [f"- {f}" for f in verstaendnis.get("funktionen") or []] or ["- siehe Verlauf"]
    zeilen += [""]
    zeilen += ["## Architektur", "- `index.html` — die Anwendung: eine Datei, läuft ohne Server und ohne Netz im Browser"]
    for ordner, inhalt in sorted(dateien.items()):
        if inhalt:
            zeilen.append(f"- `{ordner}/` — {len(inhalt)} Datei(en)")
    zeilen += ["- `JOSHI_PROJECT.md` — diese Dokumentation", "- `README.md` — kurzer Einstieg", ""]
    daten = [e for e in eingaben if e.get("rolle") in {"data", "project_file"} and e.get("art") == "daten"]
    zeilen += ["## Daten"]
    zeilen += [f"- `data/{e['datei']}` aus {e['name']}" if e.get("datei") else f"- {e['name']} (im Produkt eingebettet)"
               for e in daten] or ["- keine eigenen Datendateien; Werte stehen in der Anwendung"]
    zeilen += [""]
    zeilen += ["## Eingaben"]
    for e in eingaben:
        stand = f"Build-Snapshot vom {_datum(e.get('zeit'))}"
        if e.get("sha256"):
            groesse = f"{int(e.get('groesse') or 0):,}".replace(",", ".")
            stand += f", SHA-256 {str(e['sha256'])[:12]}…, {groesse} Bytes"
        zusatz = " — nicht Bestandteil des finalen Produkts" if e.get("rolle") == "context" else ""
        if e.get("hinweis"):
            zusatz += f" — {e['hinweis']}"
        zeilen.append(f"- {e['name']}\n  Rolle: {ROLLENTEXT.get(e.get('rolle', ''), e.get('rolle', ''))}"
                      f"{zusatz}\n  Quelle: {e.get('quelle') or 'Asset-/Eingabeordner'}\n  Stand: {stand}")
    if not eingaben:
        zeilen.append("- keine Dateien aus dem Asset-/Eingabeordner")
    zeilen += [""]
    zeilen += ["## Assets"]
    zeilen += [f"- `{ordner}/{name}`" for ordner in ("assets", "medien") for name in dateien.get(ordner, [])] \
        or ["- keine externen Assets"]
    zeilen += [""]
    faehigkeiten = []
    if "JOSHI.export" in html:
        faehigkeiten.append("`window.JOSHI.export` — PDF/Word/Bild über JOSHI (nur in JOSHI; in der Datei selbst "
                            "druckt PDF über den Browser)")
    zeilen += ["## JOSHI Capabilities"] + ([f"- {f}" for f in faehigkeiten] or ["- keine Host-Fähigkeiten"]) + [""]
    zeilen += ["## Persistenz",
               "- Eingaben und Listen speichert die Anwendung im Browser (localStorage).",
               "- In JOSHI merkt sich die Vorschau den Stand; `index.html` enthält den Stand beim Export.", ""]
    zeilen += ["## Export / Share",
               "- `index.html` direkt öffnen oder weitergeben (Bilder liegen in `assets/` daneben)",
               "- in JOSHI: HTML mit Stand, PDF, Word, PNG/JPG, E-Mail-Entwurf", ""]
    zeilen += ["## Version / Stand",
               f"- JOSHI-Produkt `{produkt.get('id', '')}`, Version {version.get('nummer')} vom "
               f"{_datum(version.get('erstellt'))}",
               f"- Prüfung: {pruefung.get('kurz') or '–'}", ""]
    offen = [b.get("text", "") for b in pruefung.get("befunde") or [] if b.get("art") in {"warnung", "luecke"}]
    zeilen += ["## Offene Punkte"] + ([f"- {o}" for o in offen[:8]] or ["- keine bekannten"]) + [""]
    zeilen += ["## Verlauf"]
    zeilen += [f"- v{v['nummer']} ({_datum(v.get('erstellt'))}): {str(v.get('aenderung') or '')[:160]}"
               for v in versionen if not v.get("abgelehnt")]
    zeilen += ["", "## Notizen", notizen.strip() or "", ""]
    return "\n".join(zeilen)


def readme(produkt: dict[str, Any], dateien: dict[str, list[str]]) -> str:
    zweck = (produkt.get("verstaendnis") or {}).get("zweck") or produkt.get("auftrag", "")[:300]
    zeilen = [f"# {produkt.get('titel') or 'JOSHI-Projekt'}", "", zweck, "",
              "## Starten", "`index.html` im Browser öffnen — kein Server, keine Installation, kein Netz nötig.", "",
              "## Wichtige Dateien", "- `index.html` — die Anwendung"]
    if dateien.get("assets"):
        zeilen.append("- `assets/` — Bilder der Anwendung")
    if dateien.get("data"):
        zeilen.append("- `data/` — Datenquellen (Kopie aus dem Asset-/Eingabeordner)")
    zeilen += ["- `JOSHI_PROJECT.md` — ausführliche Dokumentation", "",
               "## Weiterentwickeln", "In JOSHI weiter beschreiben, was sich ändern soll; JOSHI prüft jede neue "
               "Version und aktualisiert dieses Projekt.", ""]
    return "\n".join(zeilen)


def _notizen(alt: str) -> str:
    teile = re.split(r"^## Notizen\s*$", alt or "", maxsplit=1, flags=re.M)
    return teile[1].strip() if len(teile) == 2 else ""


def schreiben(wurzel: Wurzel, *, produkt: dict[str, Any], version: dict[str, Any],
              versionen: list[dict[str, Any]], bilder: list[dict[str, Any]],
              bild_bytes: Callable[[str], bytes | None], auswahl: list[Auswahl],
              meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Legt ein Projekt an oder schreibt es fort. Rückgabe: Metadaten fürs Produkt."""
    meta = dict(meta or {})
    ordner = ordner_waehlen(wurzel, produkt.get("titel", ""), meta.get("ordner", ""))
    html = version["html"]
    geschrieben: dict[str, list[str]] = {k: list(v) for k, v in (meta.get("dateien") or {}).items()}
    belegt = {f"{o}/{n}" for o, namen in geschrieben.items() for n in namen}

    def ablegen(bereich: str, name: str, daten: bytes, ersetzen: bool = False) -> str:
        datei = _dateiname(name)
        if not ersetzen and f"{bereich}/{datei}" in belegt:
            datei = _eindeutig(datei, {n for n in geschrieben.get(bereich, [])})
        wurzel.schreiben(f"{ordner}/{bereich}/{datei}", daten)
        geschrieben.setdefault(bereich, [])
        if datei not in geschrieben[bereich]:
            geschrieben[bereich].append(datei)
        belegt.add(f"{bereich}/{datei}")
        return datei

    # Bilder, die die Anwendung wirklich zeigt: aus JOSHIs Ablage (stabil).
    verweise: dict[str, str] = dict(meta.get("bilder") or {})
    namen = {b["name"]: b for b in bilder}
    for verweis in asset_verweise(html):
        if verweis in verweise or verweis not in namen:
            continue
        daten = bild_bytes(verweis)
        if daten is None:
            continue
        verweise[verweis] = "assets/" + ablegen("assets", namen[verweis].get("datei") or verweis, daten)
    eingaben = {e["name"]: e for e in meta.get("eingaben") or []}
    for eintrag in auswahl:
        schnappschuss = eintrag.snapshot()
        if eintrag.rolle in {"data", "project_file"} and eintrag.daten:
            bereich = {"daten": "data", "medien": "medien", "bild": "assets"}.get(eintrag.datei.art, "data")
            schnappschuss["datei"] = ablegen(bereich, eintrag.datei.name, eintrag.daten, ersetzen=True)
        eingaben[eintrag.datei.name] = schnappschuss
    index = export_dokument(html, zustand=produkt.get("zustand"), assets=verweise,
                            meta={"joshi": 1, "titel": produkt.get("titel"), "produkt": produkt.get("id"),
                                  "version": version.get("nummer")},
                            richtlinie=WORKSPACE_RICHTLINIE)
    wurzel.schreiben(f"{ordner}/index.html", index)
    alt = ""
    if wurzel.existiert(f"{ordner}/JOSHI_PROJECT.md"):
        alt = wurzel.lesen(f"{ordner}/JOSHI_PROJECT.md").decode("utf-8", "replace")
    wurzel.schreiben(f"{ordner}/JOSHI_PROJECT.md", dokumentation(
        produkt=produkt, version=version, versionen=versionen, dateien=geschrieben,
        eingaben=list(eingaben.values()), html=html, notizen=_notizen(alt)))
    if not wurzel.existiert(f"{ordner}/README.md"):
        wurzel.schreiben(f"{ordner}/README.md", readme(produkt, geschrieben))
    return {**meta, "ordner": ordner, "wurzel": str(wurzel.pfad), "angelegt": meta.get("angelegt") or int(time.time()),
            "aktualisiert": int(time.time()), "version": version.get("nummer"), "dateien": geschrieben,
            "bilder": verweise, "eingaben": list(eingaben.values())}
