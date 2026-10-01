# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Projekt-Workspace: große Anwendungen als Dateien bearbeiten, als eine Datei ausliefern.

Gefunden am 27.09.2026 an der einer großen Fitness-App (72.000 Zeichen, davon
45.000 in einem einzigen <script>): Als eine Datei scheiterte jede größere
Änderung — lokal passte sie nicht ins Kontextfenster (16.384 Tokens), in der
Cloud fanden die SUCHEN-Teile ihre Stelle nicht (PATCH_CONFLICT 1 von 12), und
ein Modell wollte die ganze App neu schreiben.

Ab einer Größe, bei der eine Datei nicht mehr trägt, zerlegt JOSHI die
Anwendung verlustfrei in Projektdateien:

    index.html        Markup; jede Zeile <!-- JOSHI-DATEI js/03-karten.js --> bindet eine Datei ein
    css/NN-name.css   Teile der Styles, je etwa 8.000 Zeichen
    js/NN-name.js     Teile des Skripts, je etwa 8.000 Zeichen

Das Modell sieht eine Übersicht aller Dateien und den Inhalt der Dateien, die
es braucht, und gibt nur geänderte Dateien zurück. JOSHI setzt sie wieder zu
genau einer HTML-Datei zusammen: Jede Einbindung wird durch den Dateiinhalt
ersetzt. Die Teile eines <script> bilden also weiterhin EIN Skript — das
Zerlegen ändert nie, wie die Anwendung läuft (zerlegen → zusammensetzen ergibt
Zeichen für Zeichen das Original).

Die Dateien liegen intern im Datenordner von Mini LLM, ein Ordner je Produkt
und darin einer je Änderungsauftrag. Geprüft, versioniert und ausgeliefert
wird weiterhin die zusammengesetzte Datei.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.joshi.html_werk import aenderungsbloecke, bloecke_einzeln

# Ab dieser Größe arbeitet JOSHI im Projekt (dieselbe Schwelle, ab der eine
# Datei nach einem Patchkonflikt nicht mehr neu geschrieben wird).
PROJEKT_AB = 40_000
# Richtgröße einer Projektdatei: klein genug für eine vollständige Neufassung
# durch das Modell, groß genug für zusammenhängende Abschnitte.
ZIEL_ZEICHEN = 8000
# Kleine Blöcke bleiben in index.html.
MIN_BLOCK = 400

MARKE = "<!-- JOSHI-DATEI {name} -->\n"
_MARKE = re.compile(r"<!-- JOSHI-DATEI ([\w./-]+) -->\n?")
_BLOCK = re.compile(
    r"(?P<css_tag><style\b[^>]*>)(?P<css>.*?)</style\s*>"
    r"|(?P<js_tag><script\b(?P<attr>[^>]*)>)(?P<js>.*?)</script\s*>",
    re.S | re.I)
_PFAD = re.compile(r"^(?:index\.html|css/[\w.-]+\.css|js/[\w.-]+\.js)$")


class ProjektFehler(ValueError):
    """Die Projektdateien lassen sich nicht (mehr) zu einer Datei zusammensetzen."""


@dataclass
class Projekt:
    index: str
    dateien: dict[str, str] = field(default_factory=dict)   # Reihenfolge = Reihenfolge der Einbindung

    def einbindungen(self, index: str | None = None) -> list[str]:
        return _MARKE.findall(self.index if index is None else index)

    def fehler(self) -> list[str]:
        """Jede Datei genau einmal eingebunden, keine Einbindung ohne Datei."""
        probleme = []
        genannt = self.einbindungen()
        for name in sorted(set(genannt)):
            if genannt.count(name) > 1:
                probleme.append(f"{name} ist {genannt.count(name)}-mal eingebunden")
            if name not in self.dateien:
                probleme.append(f"index.html bindet {name} ein, die Datei fehlt")
        for name in self.dateien:
            if name not in genannt:
                probleme.append(f"{name} ist in index.html nicht mehr eingebunden")
        return probleme

    def zusammensetzen(self) -> str:
        probleme = self.fehler()
        if probleme:
            raise ProjektFehler("; ".join(probleme))
        return _MARKE.sub(lambda treffer: self.dateien[treffer.group(1)], self.index)

    def alle(self) -> dict[str, str]:
        return {"index.html": self.index, **self.dateien}

    def groesse(self) -> int:
        return len(self.index) + sum(len(t) for t in self.dateien.values())


# ------------------------------------------------------------------ Zerlegen
def _string_ende(text: str, i: int, quote: str) -> int:
    j = i + 1
    while j < len(text):
        z = text[j]
        if z == "\\":
            j += 2
            continue
        if z == quote or z == "\n":
            return j + 1
        j += 1
    return j


def _regex_ende(text: str, i: int) -> int:
    j, klasse = i + 1, False
    while j < len(text):
        z = text[j]
        if z == "\\":
            j += 2
            continue
        if z == "\n":
            return j
        if klasse:
            klasse = z != "]"
        elif z == "[":
            klasse = True
        elif z == "/":
            return j + 1
        j += 1
    return j


def _zeilenenden_js(text: str) -> list[tuple[int, int]]:
    """(Position nach dem Zeilenende, Klammertiefe) für Zeilen, die im Code enden.

    Kennt Kommentare, Strings, Template-Literale mit ${…} und Regex-Literale
    gut genug, um sinnvolle Schnittstellen zu finden. Liegt die Erkennung
    einmal daneben, leidet nur die Lesbarkeit eines Schnitts — nie das
    Ergebnis, denn zusammengesetzt wird immer Zeichen für Zeichen.
    """
    enden: list[tuple[int, int]] = []
    tiefe, i, n = 0, 0, len(text)
    vorlagen: list[int] = []
    in_vorlage = False
    letztes = ""
    while i < n:
        z = text[i]
        if in_vorlage:
            if z == "\\":
                i += 2
            elif z == "`":
                in_vorlage, letztes = False, "`"
                i += 1
            elif text.startswith("${", i):
                vorlagen.append(tiefe)
                in_vorlage, letztes = False, "{"
                i += 2
            else:
                i += 1
            continue
        if z == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if z == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if z in "'\"":
            i, letztes = _string_ende(text, i, z), z
            continue
        if z == "`":
            in_vorlage = True
            i += 1
            continue
        if z == "/" and (not letztes or letztes in "(,=:[!&|?{};+-*%<>~^"):
            i, letztes = _regex_ende(text, i), "/"
            continue
        if z in "{[(":
            tiefe += 1
        elif z in "}])":
            if z == "}" and vorlagen and vorlagen[-1] == tiefe:
                vorlagen.pop()
                in_vorlage = True
                i += 1
                continue
            tiefe = max(0, tiefe - 1)
        elif z == "\n":
            enden.append((i + 1, tiefe))
        if not z.isspace():
            letztes = z
        i += 1
    return enden


def _zeilenenden_css(text: str) -> list[tuple[int, int]]:
    enden: list[tuple[int, int]] = []
    tiefe, i, n = 0, 0, len(text)
    while i < n:
        z = text[i]
        if z == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if z in "'\"":
            i = _string_ende(text, i, z)
            continue
        if z == "{":
            tiefe += 1
        elif z == "}":
            tiefe = max(0, tiefe - 1)
        elif z == "\n":
            enden.append((i + 1, tiefe))
        i += 1
    return enden


_ABSCHNITT = re.compile(r"\s*(?://|/\*|$)|\s*(?:export\s+)?(?:async\s+)?(?:function|const|let|var|class)\b|"
                        r"\s*(?:document|window)\.|\s*@media|\s*[.#:\w\[*][^{;]*\{", re.I)


def _schoen(text: str, pos: int) -> float:
    """Wie gut eignet sich die Stelle als Dateigrenze? Leerzeilen und Abschnittsanfänge zuerst."""
    zeile = text[pos:text.find("\n", pos) if text.find("\n", pos) >= 0 else len(text)]
    wert = 1.0 if not zeile.strip() else 0.8 if re.match(r"\s*(?://|/\*)", zeile) else \
        0.5 if _ABSCHNITT.match(zeile) else 0.0
    davor = text[max(0, pos - 3):pos]
    if davor.endswith("\n\n") or re.search(r"\}\s*;?\s*\n$", text[max(0, pos - 4):pos]):
        wert += 0.4
    return wert


def _schnitte(text: str, enden: list[tuple[int, int]], ziel: int) -> list[str]:
    """Teilt an Zeilenenden der flachsten Tiefe, die Teile um die Zielgröße ergibt."""
    if len(text) <= ziel * 1.4 or not enden:
        return [text]
    beste: list[str] = [text]
    for tiefe in sorted({t for _, t in enden})[:3]:
        kandidaten = [p for p, t in enden if t <= tiefe and 0 < p < len(text)]
        teile, start = [], 0
        while start < len(text):
            if len(text) - start <= ziel * 1.4:
                teile.append(text[start:])
                break
            fenster = [p for p in kandidaten if start + ziel * 0.5 <= p <= start + ziel * 1.4]
            if fenster:
                schnitt = max(fenster, key=lambda p: _schoen(text, p) * 4000 - abs((p - start) - ziel))
            else:
                weiter = [p for p in kandidaten if p > start + ziel * 0.5]
                if not weiter:
                    teile.append(text[start:])
                    break
                schnitt = weiter[0]
            teile.append(text[start:schnitt])
            start = schnitt
        if max(len(t) for t in teile) < max(len(t) for t in beste):
            beste = teile
        if max(len(t) for t in beste) <= ziel * 1.6:
            break
    return beste


_ASCII = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def _slug(text: str) -> str:
    text = "".join(_ASCII.get(z, z) for z in (text or "").lower())
    slug = ""
    for wort in re.findall(r"[a-z0-9]+", text):
        if slug and len(slug) + 1 + len(wort) > 24:
            break
        slug = f"{slug}-{wort}" if slug else wort[:24]
    return slug


def _name_fuer(inhalt: str, art: str) -> str:
    """Ein sprechender Name: erster Abschnittskommentar, sonst erste Deklaration oder Regel."""
    for zeile in inhalt.splitlines()[:40]:
        kommentar = re.match(r"\s*(?://+|/\*+)\s*[-=*#~ ]*([A-Za-zÄÖÜäöüß][^*=\-#~]{2,40})", zeile)
        if kommentar and _slug(kommentar.group(1)):
            return _slug(kommentar.group(1))
    if art == "js":
        treffer = re.search(r"(?:function\s*\*?\s*|(?:const|let|var|class)\s+)([A-Za-z_$][\w$]*)", inhalt)
    else:
        treffer = re.search(r"^\s*([.#@]?[A-Za-z][\w-]*)", inhalt, re.M)
    return _slug(treffer.group(1)) if treffer and _slug(treffer.group(1)) else ("skript" if art == "js" else "stil")


def _inline_js(attribute: str) -> bool:
    if re.search(r"\bsrc\s*=", attribute, re.I):
        return False
    typ = re.search(r"\btype\s*=\s*[\"']?([\w/+-]+)", attribute, re.I)
    return not typ or typ.group(1).lower() in {"text/javascript", "application/javascript", "module"}


def zerlegen(html: str, ziel: int = ZIEL_ZEICHEN) -> Projekt:
    """Eine HTML-Datei → Projekt. zusammensetzen() ergibt Zeichen für Zeichen das Original."""
    teile: list[str] = []
    dateien: dict[str, str] = {}
    zaehler = {"css": 0, "js": 0}
    position = 0
    for block in _BLOCK.finditer(html):
        art = "css" if block.group("css_tag") else "js"
        inhalt = block.group(art)
        if art == "js" and not _inline_js(block.group("attr") or ""):
            continue
        if len(inhalt.strip()) < MIN_BLOCK:
            continue
        enden = _zeilenenden_css(inhalt) if art == "css" else _zeilenenden_js(inhalt)
        teile.append(html[position:block.start(art)])
        for stueck in _schnitte(inhalt, enden, ziel):
            zaehler[art] += 1
            name = f"{art}/{zaehler[art]:02d}-{_name_fuer(stueck, art)}.{art}"
            dateien[name] = stueck
            teile.append(MARKE.format(name=name))
        position = block.end(art)
    teile.append(html[position:])
    projekt = Projekt("".join(teile), dateien)
    if projekt.zusammensetzen() != html:     # pragma: no cover – Sicherheitsnetz
        return Projekt(html, {})
    return projekt


# ------------------------------------------------------------------ Übersicht
_JS_NAMEN = re.compile(r"^[ \t]{0,8}(?:export\s+)?(?:async\s+)?(?:function\s*\*?\s*([A-Za-z_$][\w$]*)|"
                       r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*))", re.M)
_CSS_REGELN = re.compile(r"^[ \t]{0,4}([^\s{}/@][^{}]{0,60}?)\s*\{", re.M)


def gliederung(name: str, inhalt: str, grenze: int = 12) -> str:
    """Wenige Stichworte je Datei: Funktionen, Selektoren oder ids."""
    if name.endswith(".js"):
        # Nur die flachste Ebene der Datei — keine lokalen Variablen in Funktionen.
        treffer = [(len(m.group(0)) - len(m.group(0).lstrip()), next(g for g in m.groups() if g))
                   for m in _JS_NAMEN.finditer(inhalt)]
        flach = min((e for e, _ in treffer), default=0)
        namen = [n for e, n in treffer if e == flach]
    elif name.endswith(".css"):
        namen = [s.strip() for s in _CSS_REGELN.findall(inhalt)]
        namen += [m.strip() for m in re.findall(r"(@media[^{]{0,60})\{", inhalt)]
    else:
        namen = ["#" + i for i in re.findall(r"\bid=[\"']([\w-]+)", inhalt)]
    namen = list(dict.fromkeys(n for n in namen if n))
    rest = len(namen) - grenze
    return ", ".join(namen[:grenze]) + (f" … (+{rest})" if rest > 0 else "")


def uebersicht(projekt: Projekt) -> str:
    zeilen = []
    for name, inhalt in projekt.alle().items():
        groesse = f"{len(inhalt):,}".replace(",", ".")
        zeilen.append(f"- {name} ({groesse} Zeichen): {gliederung(name, inhalt) or '–'}")
    return "\n".join(zeilen)


_STAMM = re.compile(r"[a-zäöüß0-9]{3,}")
_ALLTAG = {"und", "oder", "die", "der", "das", "den", "dem", "des", "ein", "eine", "einen", "mit", "für", "auf",
           "bei", "wird", "werden", "soll", "sollen", "muss", "nach", "dieser", "diesem", "schritt", "jetzt",
           "nur", "alle", "jede", "jeder", "sich", "wie", "was", "ist", "sind", "nicht", "auch", "noch"}


def rangfolge(projekt: Projekt, aufgabe: str) -> list[str]:
    """Dateien nach Nähe zur Aufgabe — Rückfall, wenn das Modell nicht wählt."""
    worte = {w[:6] for w in _STAMM.findall((aufgabe or "").lower()) if w not in _ALLTAG}
    wertung = []
    for nummer, (name, inhalt) in enumerate(projekt.alle().items()):
        klein = inhalt.lower()
        treffer = sum(1 for w in worte if w in klein)
        wertung.append((-treffer, nummer, name))
    return [name for _, _, name in sorted(wertung)]


def auswahl_begrenzen(projekt: Projekt, gewuenscht: list[str], budget: int) -> list[str]:
    """Gewünschte Dateien in Reihenfolge, solange das Budget reicht; index.html ist Rückfall."""
    alle = projekt.alle()
    reihe = [n for n in dict.fromkeys([*gewuenscht, "index.html"]) if n in alle]
    gewaehlt, summe = [], 0
    for name in reihe:
        if summe + len(alle[name]) <= budget:
            gewaehlt.append(name)
            summe += len(alle[name])
    return gewaehlt


# ------------------------------------------------------------------ Antwort
_KOPF = re.compile(r"^[ \t]*={3,}[ \t]*(DATEI|ÄNDERN|AENDERN|ÄNDERUNG)[ \t]*:?[ \t]*(\S+?)[ \t]*={3,}[ \t]*$",
                   re.M | re.I)
_ENDE = re.compile(r"^[ \t]*={3,}[ \t]*ENDE(?:[ \t]+DATEI)?[ \t]*={3,}[ \t]*$", re.M | re.I)
_ZAUN = re.compile(r"^[ \t]*```[\w-]*[ \t]*$", re.M)
_PLATZHALTER = re.compile(
    r"^[ \t]*(?://|/\*|<!--)[ \t]*(?:\.{3}|…)?[^\n]{0,50}?\b(?:unverändert|unveraendert|bleibt (?:gleich|wie|so)|"
    r"wie bisher|rest(?:liche[rns]?)? (?:des|der|bleibt|unverändert|code)|existing (?:code|styles?)|unchanged|"
    r"remaining (?:code|styles?)|same as before)\b[^\n]{0,50}$"
    r"|^[ \t]*(?://|/\*|<!--)?[ \t]*(?:\.{3}|…)[ \t]*(?:\*/|-->)?[ \t]*$", re.M | re.I)
_ENTFERNEN = re.compile(r"entfern|lösch|loesch|weglass|streich|ohne\b|raus|abbau|aufräum|kürz|vereinfach", re.I)


@dataclass
class Antwort:
    """Was aus einer Modellantwort im Projekt wurde."""
    projekt: Projekt
    geaendert: list[str] = field(default_factory=list)
    neu: list[str] = field(default_factory=list)
    probleme: list[str] = field(default_factory=list)
    offen: dict[str, list[tuple[str, str]]] = field(default_factory=dict)   # Datei → nicht passende Blöcke

    @property
    def leer(self) -> bool:
        return not (self.geaendert or self.neu or self.probleme or self.offen)


def abschnitte(text: str) -> list[tuple[str, str, str]]:
    """(Art, Pfad, Inhalt) je Dateiabschnitt der Antwort."""
    koepfe = list(_KOPF.finditer(text or ""))
    ergebnis = []
    for nummer, kopf in enumerate(koepfe):
        ende = koepfe[nummer + 1].start() if nummer + 1 < len(koepfe) else len(text)
        inhalt = text[kopf.end():ende]
        schluss = _ENDE.search(inhalt)
        if schluss:
            inhalt = inhalt[:schluss.start()]
        inhalt = inhalt[1:] if inhalt.startswith("\n") else inhalt
        zaeune = list(_ZAUN.finditer(inhalt))
        if zaeune and not inhalt[:zaeune[0].start()].strip():
            inhalt = inhalt[zaeune[0].end() + 1:]
            letzter = list(_ZAUN.finditer(inhalt))
            if letzter and not inhalt[letzter[-1].end():].strip():
                inhalt = inhalt[:letzter[-1].start()]
        art = "datei" if kopf.group(1).upper() == "DATEI" else "aendern"
        pfad = kopf.group(2).strip()
        # Ein einzelnes ./ ist ein harmloses relatives Präfix. Mehrfache
        # Punkte/Schrägstriche werden nicht „bereinigt“, sondern später als
        # ungültiger Pfad abgewiesen.
        if pfad.startswith("./"):
            pfad = pfad[2:]
        ergebnis.append((art, pfad, inhalt))
    return ergebnis


def _einbinden(index: str, name: str) -> str:
    """Neue Datei ans Ende der gleichartigen Einbindungen — oder in einen neuen Block."""
    art = "css" if name.endswith(".css") else "js"
    gleich = [m for m in _MARKE.finditer(index) if m.group(1).endswith("." + art)]
    marke = MARKE.format(name=name)
    if gleich:
        stelle = gleich[-1].end()
        return index[:stelle] + marke + index[stelle:]
    if art == "css":
        block = f"<style>\n{marke}</style>\n"
        treffer = re.search(r"</head\s*>", index, re.I)
    else:
        block = f"<script>\n{marke}</script>\n"
        treffer = re.search(r"</body\s*>", index, re.I)
    stelle = treffer.start() if treffer else len(index)
    return index[:stelle] + block + index[stelle:]


def anwenden(projekt: Projekt, text: str, *, gesehen: list[str], aufgabe: str = "") -> Antwort:
    """Wendet die Dateiabschnitte einer Antwort an. Unsicheres wird gemeldet, nie geraten."""
    index, dateien = projekt.index, dict(projekt.dateien)
    ergebnis = Antwort(projekt)
    darf_kuerzen = bool(_ENTFERNEN.search(aufgabe or ""))
    for art, pfad, inhalt in abschnitte(text):
        if not _PFAD.match(pfad):
            ergebnis.probleme.append(f"„{pfad}“ ist kein erlaubter Projektpfad (index.html, css/…css, js/…js)")
            continue
        alt = index if pfad == "index.html" else dateien.get(pfad)
        if alt is not None and pfad not in gesehen:
            ergebnis.probleme.append(f"{pfad} wurde geändert, ohne dass das Modell sie gesehen hat")
            continue
        if art == "aendern":
            if alt is None:
                ergebnis.probleme.append(f"{pfad} gibt es nicht — Änderungsblöcke brauchen eine vorhandene Datei")
                continue
            bloecke = aenderungsbloecke(inhalt)
            if not bloecke:
                ergebnis.probleme.append(f"Für {pfad} kamen keine lesbaren Änderungsblöcke")
                continue
            neu, offen = bloecke_einzeln(alt, bloecke)
            if offen:
                ergebnis.offen[pfad] = offen
        else:
            neu = inhalt
            if alt is not None:
                platzhalter = [z.strip() for z in _PLATZHALTER.findall(neu)] if _PLATZHALTER.search(neu) else []
                vorher = len(_PLATZHALTER.findall(alt))
                if len(_PLATZHALTER.findall(neu)) > vorher:
                    ergebnis.probleme.append(f"{pfad} enthält Auslassungen statt Code („{(platzhalter or ['…'])[0][:60]}“)")
                    continue
                if len(alt) > 1500 and len(neu) < 0.6 * len(alt) and not darf_kuerzen:
                    ergebnis.probleme.append(f"{pfad} schrumpfte von {len(alt)} auf {len(neu)} Zeichen — "
                                             "vermutlich unvollständig ausgegeben")
                    continue
        if neu == alt:
            continue
        if pfad == "index.html":
            index = neu
        else:
            dateien[pfad] = neu
            if alt is None:
                index = _einbinden(index, pfad)
                ergebnis.neu.append(pfad)
                continue
        ergebnis.geaendert.append(pfad)
    ergebnis.projekt = Projekt(index, dateien)
    ergebnis.probleme.extend(ergebnis.projekt.fehler())
    return ergebnis


# ------------------------------------------------------------------ Ordner
def ordner(daten: Path, produkt: dict[str, Any]) -> Path:
    titel = _slug(produkt.get("titel", "")) or "projekt"
    kennung = re.sub(r"[^a-zA-Z0-9_-]", "", str(produkt.get("id", "")))[:80]
    if not kennung:
        raise ProjektFehler("Produkt-ID fehlt oder ist ungültig")
    return daten / "joshi-projekte" / f"{titel}-{kennung}"


def auftrag_ordner(daten: Path, produkt: dict[str, Any], auftrag_id: str) -> Path:
    """Interner Arbeitsordner eines Auftrags; bleibt vom Export-Workspace getrennt."""
    kennung = str(auftrag_id or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", kennung):
        raise ProjektFehler("Auftrags-ID ist ungültig")
    return ordner(daten, produkt) / "auftraege" / kennung


def _sicherer_pfad(ziel: Path, name: str) -> Path:
    if not _PFAD.fullmatch(name):
        raise ProjektFehler(f"Ungültiger Projektpfad: {name!r}")
    wurzel = ziel.resolve()
    datei = ziel / name
    try:
        datei.parent.resolve().relative_to(wurzel)
        if datei.exists() or datei.is_symlink():
            datei.resolve().relative_to(wurzel)
    except (OSError, ValueError):
        raise ProjektFehler(f"Projektpfad verlässt den Arbeitsordner: {name!r}") from None
    return datei


def _atomar_schreiben(datei: Path, text: str) -> None:
    datei.parent.mkdir(parents=True, exist_ok=True)
    # Noch einmal nach mkdir prüfen: Ein bereits vorhandener Symlink im
    # Arbeitsordner darf nicht nach außen umleiten.
    fd, temporaer = tempfile.mkstemp(prefix=".joshi-", dir=datei.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporaer, datei)
    finally:
        try:
            os.unlink(temporaer)
        except FileNotFoundError:
            pass


def schreiben(ziel: Path, projekt: Projekt, **meta: Any) -> None:
    """Schreibt die Projektdateien; Dateien, die es nicht mehr gibt, verschwinden."""
    probleme = projekt.fehler()
    if probleme:
        raise ProjektFehler("; ".join(probleme))
    ziel.mkdir(parents=True, exist_ok=True)
    alt = _manifest(ziel).get("dateien") or []
    for name in alt:
        if not isinstance(name, str) or name == "index.html" or not _PFAD.fullmatch(name):
            continue
        datei = _sicherer_pfad(ziel, name)
        if name not in projekt.dateien and datei.is_file():
            datei.unlink()
    for name, inhalt in projekt.alle().items():
        datei = _sicherer_pfad(ziel, name)
        _atomar_schreiben(datei, inhalt)
    _atomar_schreiben(ziel / "manifest.json", json.dumps({
        "dateien": list(projekt.dateien), "zeichen": projekt.groesse(), "geschrieben": int(time.time()), **meta,
    }, ensure_ascii=False, indent=1))


def dokumentation_schreiben(ziel: Path, text: str) -> None:
    """Schreibt die Auftragsnotiz nur in dessen internen Projektordner."""
    ziel.mkdir(parents=True, exist_ok=True)
    _atomar_schreiben(ziel / "PROJEKT.md", text)


def _manifest(ziel: Path) -> dict[str, Any]:
    try:
        gelesen = json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))
        return gelesen if isinstance(gelesen, dict) else {}
    except (OSError, ValueError):
        return {}


def laden(ziel: Path, html: str) -> Projekt | None:
    """Das Projekt aus dem Ordner — nur wenn es genau diese Anwendung ergibt."""
    manifest = _manifest(ziel)
    try:
        namen = manifest.get("dateien") or []
        if not isinstance(namen, list) or len(namen) > 500 or any(
                not isinstance(name, str) or name == "index.html" or not _PFAD.fullmatch(name) for name in namen):
            return None
        index = _sicherer_pfad(ziel, "index.html").read_text(encoding="utf-8")
        dateien = {_name: _sicherer_pfad(ziel, _name).read_text(encoding="utf-8") for _name in namen}
        projekt = Projekt(index, dateien)
        return projekt if projekt.zusammensetzen() == html else None
    except (OSError, ProjektFehler, ValueError):
        return None


def beschreibung(produkt: dict[str, Any], projekt: Projekt, *, grund: str, auftrag: str = "",
                 version: int | None = None, zurueckgestellt: list[str] | None = None) -> str:
    """PROJEKT.md — wofür der Ordner da ist und was darin liegt."""
    jetzt = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    zeilen = [f"# {produkt.get('titel') or 'JOSHI-Projekt'}", "",
              "Von JOSHI angelegt und gepflegt. Die Anwendung ist zu groß, um sie als eine Datei zuverlässig "
              "zu ändern; JOSHI bearbeitet sie deshalb in diesen Projektdateien und setzt sie zum Prüfen und "
              "Ausliefern wieder zu einer einzigen HTML-Datei zusammen.", "",
              f"- Grund: {grund}", f"- Stand: {jetzt}" + (f", aktive Version {version}" if version else ""),
              f"- Größe zusammengesetzt: {projekt.groesse():,} Zeichen in {len(projekt.dateien) + 1} Dateien"
              .replace(",", "."), ""]
    if auftrag:
        zeilen += ["## Laufender Auftrag", auftrag.strip()[:1200], ""]
    if zurueckgestellt:
        zeilen += ["## Zurückgestellt"] + [f"- {z}" for z in zurueckgestellt] + [""]
    zeilen += ["## Dateien", uebersicht(projekt), "",
               "## Aufbau", "`index.html` enthält das Markup. Jede Zeile `<!-- JOSHI-DATEI name -->` wird beim "
               "Zusammensetzen durch den Inhalt dieser Datei ersetzt. Die js-Dateien eines `<script>` bilden "
               "zusammen ein einziges Skript; eine Datei kann mitten in einem Block beginnen oder enden.", ""]
    return "\n".join(zeilen)
