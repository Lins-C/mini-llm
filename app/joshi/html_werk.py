# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""HTML-Werkstatt: alles, was JOSHI deterministisch mit HTML tut.

Das Modell liefert Text. Hier wird daraus ein vollständiges Dokument, hier
werden Änderungsblöcke angewendet, Bilder eingesetzt und die Laufzeit-Hülle
(Sicherheitsrichtlinie + Vorrede) angelegt. Kein Modellaufruf, keine Heuristik
über die Absicht des Nutzers.
"""
from __future__ import annotations

import html as html_modul
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LAUFZEIT_JS = (Path(__file__).with_name("laufzeit.js")).read_text(encoding="utf-8")

# Gleiche Richtlinie wie die Chat-Vorschau: kein Netz, keine Fremdframes,
# Bilder nur eingebettet. Die Anwendung läuft damit überall gleich — in der
# Vorschau, in der Prüfung und beim Empfänger.
SICHERHEITSRICHTLINIE = "; ".join((
    "default-src 'none'",
    "style-src 'unsafe-inline'",
    "script-src 'unsafe-inline'",
    "img-src data: blob:",
    "media-src data: blob:",
    "font-src data:",
    "connect-src 'none'",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
))

MAX_HTML_ZEICHEN = 600_000
ASSET_VERWEIS = re.compile(r"joshi:(bild-\d{1,3})\b")
_ANFANG = re.compile(r"<!doctype\s+html\b[^>]*>|<html\b[^>]*>", re.IGNORECASE)
_ENDE = re.compile(r"</html\s*>", re.IGNORECASE)
_ZAUN = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\n?|```")
_FRAGMENT_START = re.compile(r"<(?:style|div|main|section|header|body|head|meta|title|form|h1|script|link)\b", re.IGNORECASE)


@dataclass
class Auszug:
    html: str
    vollstaendig: bool
    hinweise: list[str] = field(default_factory=list)


def html_aus_antwort(text: str, titel: str = "JOSHI-Produkt") -> Auszug:
    """Holt das HTML-Dokument aus einer Modellantwort.

    Modelle umrahmen die Datei gern mit Markdown-Zäunen oder einem Satz davor.
    Kleine Modelle liefern manchmal nur Fragmente; die werden in ein
    vollständiges Grundgerüst gesetzt, statt den Auftrag scheitern zu lassen.
    """
    roh = (text or "").replace("\r\n", "\n")
    anfang = _ANFANG.search(roh)
    if anfang:
        rest = roh[anfang.start():]
        enden = list(_ENDE.finditer(rest))
        if enden:
            return Auszug(rest[:enden[-1].end()].strip(), True)
        return Auszug(_ZAUN.sub("", rest).rstrip(), False, ["Die Datei endet ohne </html>."])
    ohne_zaun = _ZAUN.sub("", roh).strip()
    fragment = _FRAGMENT_START.search(ohne_zaun)
    if not fragment:
        return Auszug("", False, ["Die Antwort enthält kein HTML."])
    koerper = ohne_zaun[fragment.start():].strip()
    geschlossen = bool(re.search(r"</[a-zA-Z][a-zA-Z0-9]*\s*>\s*$", koerper))
    dokument = (
        "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html_modul.escape(titel)}</title>\n</head>\n<body>\n{koerper}\n</body>\n</html>"
    )
    return Auszug(dokument, geschlossen, ["Das Modell lieferte nur ein Fragment; es wurde in ein Grundgerüst gesetzt."])


def titel_aus_html(dokument: str) -> str:
    treffer = re.search(r"<title[^>]*>(.*?)</title>", dokument or "", re.IGNORECASE | re.DOTALL)
    if treffer:
        return html_modul.unescape(re.sub(r"\s+", " ", treffer.group(1))).strip()[:80]
    treffer = re.search(r"<h1[^>]*>(.*?)</h1>", dokument or "", re.IGNORECASE | re.DOTALL)
    if treffer:
        return html_modul.unescape(re.sub(r"<[^>]+>|\s+", " ", treffer.group(1))).strip()[:80]
    return ""


def json_aus_antwort(roh: Any) -> Any:
    """Strukturierte Antworten kommen nicht immer als reines JSON.

    Gemessen am 19.09.: ein Cloud-Modell lieferte trotz Schemavorgabe
    ```json … ``` — das Verständnis fiel still auf einen Notbehelf zurück.
    """
    if not isinstance(roh, str):
        return roh
    text = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", roh.strip())
    for kandidat in (text, text[text.find("{"):text.rfind("}") + 1] if "{" in text else ""):
        if not kandidat:
            continue
        try:
            return json.loads(kandidat)
        except json.JSONDecodeError:
            continue
    return {}


# --------------------------------------------------------------- Änderungen
_BLOCK = re.compile(
    r"<{5,9}\s*(?:SUCHEN|SEARCH|ALT)\s*\n(.*?)\n?={5,9}\s*\n(.*?)\n?>{5,9}\s*(?:ERSETZEN|REPLACE|NEU)",
    re.DOTALL | re.IGNORECASE,
)


def aenderungsbloecke(text: str) -> list[tuple[str, str]]:
    return [(alt, neu) for alt, neu in _BLOCK.findall(text or "")]


def _flexibel(suchen: str) -> re.Pattern[str] | None:
    teile = [re.escape(teil) for teil in suchen.split()]
    if not teile:
        return None
    return re.compile(r"\s*".join(teile))


# Eine Zeile, die nur aus einer Trennmarke besteht, gehört nie in eine Datei.
MARKE = re.compile(r"^[ \t]*(?:<{7,9}|={7,9}|>{7,9})(?:[ \t]+(?:SUCHEN|ERSETZEN|SEARCH|REPLACE|ALT|NEU))?[ \t]*$",
                   re.MULTILINE | re.IGNORECASE)


def marken_zeilen(text: str) -> list[int]:
    """Zeilennummern (ab 1) mit übrig gebliebenen Trennmarken wie `=======`."""
    return [text.count("\n", 0, treffer.start()) + 1 for treffer in MARKE.finditer(text or "")]


def bloecke_einzeln(dokument: str, bloecke: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
    """Wendet SUCHEN/ERSETZEN-Blöcke an. Rückgabe: (neues HTML, nicht passende Blöcke).

    Erst wortgetreu, dann mit beliebigem Leerraum — Modelle geben Einrückungen
    selten exakt wieder. Ein Block, der nirgends passt, wird zurückgegeben
    statt geraten.

    Ein Block, dessen ERSETZEN-Teil selbst eine Trennmarke enthält, ist
    kaputt und wird nie angewendet. Gefunden am 27.09.2026: Ein Modell
    lieferte einen Block mit zwei `=======`; eingefügt stand die Marke mitten
    im JavaScript („Unexpected token '==='“), und zwei Reparaturen fanden sie
    nicht.
    """
    offen: list[tuple[str, str]] = []
    for alt, neu in bloecke:
        if not alt.strip() or MARKE.search(neu) or MARKE.search(alt):
            offen.append((alt, neu))
            continue
        if alt in dokument:
            dokument = dokument.replace(alt, neu, 1)
            continue
        muster = _flexibel(alt)
        treffer = muster.search(dokument) if muster else None
        if treffer:
            dokument = dokument[:treffer.start()] + neu + dokument[treffer.end():]
            continue
        offen.append((alt, neu))
    return dokument, offen


def bloecke_anwenden(dokument: str, bloecke: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Wie bloecke_einzeln, meldet aber nur die SUCHEN-Teile (für Befunde)."""
    dokument, offen = bloecke_einzeln(dokument, bloecke)
    return dokument, [alt.strip()[:300] if alt.strip() else "(leerer SUCHEN-Teil)" for alt, _ in offen]


def _gequetscht(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def ersetzung_vorhanden(dokument: str, neu: str) -> bool:
    """Steckt der ERSETZEN-Teil eines Blocks schon im Dokument?

    So lässt sich nach einem Nachtrag prüfen, ob eine zunächst nicht passende
    Änderung am Ende wirklich angekommen ist — unabhängig davon, wie das
    Modell sie zerlegt hat. Leerraum zählt nicht.
    """
    ziel = _gequetscht(neu)
    return not ziel or ziel in _gequetscht(dokument)


@dataclass
class Patchbericht:
    """Was aus einer Antwort mit Änderungsblöcken wurde.

    komplett       alle Blöcke angewendet (gegebenenfalls nach einem Nachtrag)
    teilweise      einige Blöcke passten nicht — noch keine fertige Änderung
    konflikt       auch der Nachtrag brachte nicht alle Änderungen an
    abgeschnitten  die Antwort endete am Ausgabelimit — nichts wird angewendet
    neu_geschrieben die ganze Datei wurde neu geliefert
    """
    status: str = "komplett"
    bloecke: int = 0
    angewendet: int = 0
    konflikte: list[str] = field(default_factory=list)
    nachtrag: bool = False
    grund: str = "stop"

    def als_dict(self) -> dict[str, Any]:
        return {"status": self.status, "bloecke": self.bloecke, "angewendet": self.angewendet,
                "konflikte": len(self.konflikte), "fehlende": [k[:160] for k in self.konflikte[:6]],
                "nachtrag": self.nachtrag, "grund": self.grund}


# -------------------------------------------------------------------- Bilder
def asset_verweise(dokument: str) -> list[str]:
    return sorted(set(ASSET_VERWEIS.findall(dokument or "")))


def assets_einsetzen(dokument: str, assets: dict[str, str]) -> str:
    """Ersetzt joshi:bild-N durch die eingebettete Data-URI."""
    def ersetzen(treffer: re.Match[str]) -> str:
        return assets.get(treffer.group(1), treffer.group(0))
    return ASSET_VERWEIS.sub(ersetzen, dokument)


# ------------------------------------------------------------ Laufzeit-Hülle
def _json_im_skript(wert: Any) -> str:
    return json.dumps(wert, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _einfuegestelle(dokument: str) -> tuple[int, bool]:
    """Wo die Laufzeit hingehört: direkt hinter <head> (oder notfalls davor)."""
    for muster, ohne_kopf in ((r"<head\b[^>]*>", False), (r"<html\b[^>]*>", True), (r"<!doctype[^>]*>", False)):
        treffer = re.search(muster, dokument, re.IGNORECASE)
        if treffer:
            return treffer.end(), ohne_kopf
    return 0, False


def _einsetzen(dokument: str, kopf: str) -> str:
    stelle, ohne_kopf = _einfuegestelle(dokument)
    if ohne_kopf:
        kopf = "<head>" + kopf + "</head>"
    return dokument[:stelle] + kopf + dokument[stelle:]


def originalzeile(dokument: str, gemeldet: int) -> int:
    """Rechnet eine Zeilennummer aus dem Laufzeit-Dokument auf das Original um.

    Die Laufzeit schiebt alle folgenden Zeilen nach unten; das Modell soll bei
    einer Reparatur aber die Zeile seiner eigenen Datei genannt bekommen.
    """
    if gemeldet <= 0:
        return gemeldet
    stelle, _ = _einfuegestelle(dokument)
    einfuegezeile = dokument[:stelle].count("\n") + 1
    versatz = LAUFZEIT_JS.count("\n")
    if gemeldet > einfuegezeile + versatz:
        return gemeldet - versatz
    return gemeldet if gemeldet < einfuegezeile else 0


def laufzeit_dokument(
    dokument: str,
    *,
    modus: str,
    zustand: dict[str, Any] | None = None,
    schluessel: str = "",
    assets: dict[str, str] | None = None,
    zusatz_kopf: str = "",
    richtlinie: str = SICHERHEITSRICHTLINIE,
) -> str:
    """Setzt Sicherheitsrichtlinie, Konfiguration und Laufzeit vor alles andere."""
    konfiguration = {"modus": modus, "zustand": zustand or {}, "schluessel": schluessel}
    kopf = (
        f'<meta http-equiv="Content-Security-Policy" content="{richtlinie}">'
        f"{zusatz_kopf}"
        f"<script>window.__JOSHI__={_json_im_skript(konfiguration)};</script>"
        f"<script>{LAUFZEIT_JS}</script>"
    )
    from app.joshi import bibliotheken

    return _einsetzen(assets_einsetzen(bibliotheken.einsetzen(dokument), assets or {}), kopf)


def export_dokument(
    dokument: str,
    *,
    zustand: dict[str, Any] | None,
    meta: dict[str, Any],
    assets: dict[str, str] | None = None,
    richtlinie: str = SICHERHEITSRICHTLINIE,
) -> str:
    """Portables Produkt: App + aktueller Zustand + JOSHI-Metadaten in einer Datei.

    Im Workspace verweisen Bilder relativ auf `assets/`; dafür darf `richtlinie`
    zusätzlich Bilder aus der eigenen Datei-Herkunft erlauben — Netz bleibt gesperrt.
    """
    daten = f'<script type="application/json" id="joshi-daten">{_json_im_skript({**meta, "zustand": zustand or {}})}</script>'
    generator = '<meta name="generator" content="JOSHI · Mini LLM">'
    return laufzeit_dokument(
        dokument,
        modus="export",
        zustand=zustand,
        schluessel=str(meta.get("schluessel") or meta.get("produkt") or ""),
        assets=assets,
        zusatz_kopf=generator + daten,
        richtlinie=richtlinie,
    )


# ------------------------------------------------------- Abschnitt exportieren
_SKRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>|<script\b[^>]*/?>", re.DOTALL | re.IGNORECASE)
_EREIGNIS = re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
MAX_ABSCHNITT = 1_000_000


def abschnitt_dokument(html: str, css: str = "", titel: str = "") -> str:
    """Baut aus einem Ausschnitt der laufenden Anwendung ein Druckdokument.

    Der Ausschnitt kommt aus dem Sandkasten und wird wie fremder Inhalt
    behandelt: Skripte und Ereignis-Attribute fliegen raus, es bleibt reine
    Darstellung. Gerendert wird mit derselben strengen Richtlinie wie sonst.
    """
    sauber = _EREIGNIS.sub("", _SKRIPT.sub("", (html or "")[:MAX_ABSCHNITT]))
    stile = _SKRIPT.sub("", (css or "")[:MAX_ABSCHNITT])
    name = html_modul.escape((titel or "Dokument")[:120])
    return (
        "<!DOCTYPE html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">"
        f'<meta http-equiv="Content-Security-Policy" content="{SICHERHEITSRICHTLINIE}">'
        f"<title>{name}</title>"
        "<style>html,body{margin:0;padding:0;background:#fff}"
        "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;padding:24px}"
        "@media print{body{padding:0}}</style>"
        f"<style>{stile}</style></head><body>{sauber}</body></html>"
    )


# ---------------------------------------------------------- Statische Prüfung
_EXTERN_SKRIPT = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']?\s*(?:https?:)?//([^\"'\s>]+)", re.IGNORECASE)
_EXTERN_STIL = re.compile(r"<link\b[^>]*\bhref\s*=\s*[\"']?\s*(?:https?:)?//([^\"'\s>]+)", re.IGNORECASE)
_EXTERN_IMPORT = re.compile(r"@import\s+(?:url\()?[\"']?(?:https?:)?//([^\"')\s]+)", re.IGNORECASE)
_NETZ = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(", re.IGNORECASE)
_DIALOG = re.compile(r"\b(?:alert|confirm|prompt)\s*\(")


@dataclass
class Befund:
    art: str          # fehler | warnung | info
    text: str         # für Menschen
    technik: str = ""  # für das Modell und die technischen Details

    def als_dict(self) -> dict[str, str]:
        return {"art": self.art, "text": self.text, "technik": self.technik}


def code_ausschnitt(dokument: str, zeile: int, umfeld: int = 5) -> str:
    """Nummerierter Ausschnitt um eine Zeile — damit eine Reparatur die Stelle findet."""
    zeilen = (dokument or "").split("\n")
    if zeile <= 0 or zeile > len(zeilen):
        return ""
    von, bis = max(1, zeile - umfeld), min(len(zeilen), zeile + umfeld)
    return "\n".join(f"{'>>' if n == zeile else '  '}{n:5d}| {zeilen[n - 1][:180]}" for n in range(von, bis + 1))


def statische_befunde(dokument: str) -> list[Befund]:
    befunde: list[Befund] = []
    if not dokument.strip():
        return [Befund("fehler", "Es wurde kein HTML erzeugt.", "Leere Antwort")]
    marken = marken_zeilen(dokument)
    if marken:
        befunde.append(Befund(
            "fehler", "In der Datei stehen Reste von Änderungsmarkierungen.",
            f"Zeile(n) {', '.join(map(str, marken[:5]))} bestehen nur aus einer Trennmarke wie ======= — "
            "entfernen und den Code dort korrekt zusammenfügen.\n" + code_ausschnitt(dokument, marken[0], 3)))
    if len(dokument) > MAX_HTML_ZEICHEN:
        befunde.append(Befund("fehler", "Die Anwendung ist zu groß.",
                              f"{len(dokument)} Zeichen; höchstens {MAX_HTML_ZEICHEN}."))
    if not re.search(r"<body\b", dokument, re.IGNORECASE):
        befunde.append(Befund("warnung", "Dem Dokument fehlt ein <body>.", "Kein <body>-Element"))
    for muster, was in ((_EXTERN_SKRIPT, "Skript"), (_EXTERN_STIL, "Stylesheet"), (_EXTERN_IMPORT, "Stylesheet")):
        for adresse in muster.findall(dokument)[:3]:
            befunde.append(Befund(
                "fehler",
                f"Die Anwendung lädt ein {was} aus dem Internet. JOSHI-Produkte müssen ohne Netz funktionieren.",
                f"Externes {was} //{adresse[:120]} wird blockiert. Ersetze es durch eigenen Code in der Datei "
                "(Diagramme mit <svg> oder <canvas> selbst zeichnen).",
            ))
    if _NETZ.search(dokument):
        befunde.append(Befund("warnung", "Die Anwendung versucht Netzwerkzugriffe; die sind gesperrt.",
                              "fetch/XMLHttpRequest ist blockiert (connect-src 'none')."))
    if _DIALOG.search(re.sub(r"<style\b.*?</style>", "", dokument, flags=re.DOTALL | re.IGNORECASE)):
        befunde.append(Befund("info", "Meldungsfenster (alert) werden im Seiteninhalt angezeigt.",
                              "alert/confirm/prompt verwendet"))
    return befunde
