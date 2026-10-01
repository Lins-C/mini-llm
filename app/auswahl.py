# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Markierte Inhalte für Skills aufbereiten.

Einen Skill auf eine markierte KI-Ausgabe anzuwenden heißt: den Inhalt
verstehen und in die Form des Skills bringen. Bei HTML-Code hieß „bearbeiten"
für das Modell bisher „HTML zurückgeben" — die Erklärung einer Lernseite kam
als leicht umformulierte Lernseite zurück, die Analyse als abgeschnittener
Seitenkopf. Hier wird aus dem Code herausgelöst, was die Seite zeigt und tut,
in der Reihenfolge von oben nach unten. Das geschieht ohne Modell und damit
für jedes Modell gleich.

Bei einer Programmseite wie dem Dienstplan-Generator steckt das Wesentliche im
Skript: zwölf Mitarbeitende mit Rolle, Wohngruppe und Stundenkonto, die Regel
„nur Fachkräfte allein", die Gewichtung beim Einteilen. Ein Auszug nur aus
sichtbarem Text und Farben ließ davon nichts übrig. Deshalb kommen Datentabellen
mit Auszählung, die Kommentare des Autors und — bei echter Programmlogik — ein
Auszug der Logik ohne Markup dazu.
"""
from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser

MARKIERUNG = re.compile(
    r"(--- START MARKIERTER INHALT(?: \([^)]*\))? ---\n)(.*?)(\n--- ENDE MARKIERTER INHALT ---)",
    re.S,
)
HTML_ZAUN = re.compile(r"```(?:html|htm|xhtml)\s*\n(.*?)```", re.S | re.I)
CODE_ZAUN = re.compile(r"```([\w+#.-]*)\s*\n(.*?)```", re.S)

# Diese Skills geben den Inhalt in derselben Form zurück. Für sie bleibt der
# Code, wie er ist — eine übersetzte Seite ist wieder eine Seite.
UMFORMENDE_SKILLS = {"translation"}

MAX_AUSZUG = 24_000
# Ab so viel eigener Logik ist eine Seite ein Programm. Dann gehört ein Auszug
# der Logik dazu — ohne ihn fehlen einem Bericht die Regeln des Programms.
PROGRAMM_MINDESTLOGIK = 1500
LOGIK_GRENZE = 9000


class _Leser(HTMLParser):
    """Sammelt sichtbare Inhalte, Skripte und Stile in Dokumentreihenfolge."""

    SAMMELND = {
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "button", "label",
        "td", "th", "blockquote", "figcaption", "summary", "option", "dt", "dd",
        "div", "title", "caption", "legend",
    }
    UEBERSCHRIFT = {f"h{n}": "#" * n for n in range(1, 7)}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stapel: list[list] = []
        self.zeilen: list[str] = []
        self.titel = ""
        self.skripte: list[str] = []
        self.stile: list[str] = []
        self._roh: str | None = None
        self._roh_puffer: list[str] = []

    # -- Skript und Stil werden roh gesammelt ---------------------------
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._roh = tag
            self._roh_puffer = []
            return
        if tag == "br" and self.stapel:
            self.stapel[-1][1].append(" ")
        if tag in self.SAMMELND:
            self.stapel.append([tag, []])

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._roh == tag:
            (self.skripte if tag == "script" else self.stile).append("".join(self._roh_puffer))
            self._roh = None
            return
        if tag not in self.SAMMELND:
            # Ein Symbol in einem <span> klebt sonst am folgenden Wort:
            # „🧠Was sind KI-Skills?". Der Browser trennt beides per CSS.
            if tag == "span" and self.stapel:
                self.stapel[-1][1].append(" ")
            return
        # Nicht geschlossene Kinder schließen, wenn ihr Elternteil endet.
        while self.stapel:
            name, puffer = self.stapel.pop()
            self._ausgeben(name, puffer)
            if name == tag:
                break

    def handle_data(self, data):
        if self._roh:
            self._roh_puffer.append(data)
        elif self.stapel:
            self.stapel[-1][1].append(data)

    def close(self):
        super().close()
        while self.stapel:
            name, puffer = self.stapel.pop()
            self._ausgeben(name, puffer)

    def _ausgeben(self, name: str, puffer: list[str]) -> None:
        text = re.sub(r"\s+", " ", "".join(puffer)).strip()
        # Zeilen nur aus Symbolen („＋ ＝" zwischen Ablaufschritten) tragen nichts.
        if not text or not re.search(r"\w", text):
            return
        if name == "title":
            self.titel = text
            return
        if name in self.UEBERSCHRIFT:
            self.zeilen.append(f"{self.UEBERSCHRIFT[name]} {text}")
        elif name in {"li", "option", "dd"}:
            self.zeilen.append(f"- {text}")
        elif name == "button":
            self.zeilen.append(f"[Schaltfläche: {text}]")
        else:
            self.zeilen.append(text)


def _quizdaten(skript: str) -> list[str]:
    """Fragen mit Antworten aus Datenstrukturen wie {f:"…", o:["…"], a:1}."""
    eintraege: list[str] = []
    objekt = re.compile(
        r"\{\s*\w+\s*:\s*([\"'])(.+?)\1\s*,\s*\w+\s*:\s*\[(.*?)\]\s*,\s*\w+\s*:\s*(\d+)\s*\}",
        re.S,
    )
    reihe = re.compile(r"\[\s*([\"'])(.+?)\1\s*,((?:\s*([\"']).*?\4\s*,)+)\s*(\d+)\s*\]", re.S)
    for treffer in objekt.finditer(skript):
        optionen = re.findall(r"([\"'])(.*?)\1", treffer.group(3))
        texte = [text for _, text in optionen]
        index = int(treffer.group(4))
        richtig = texte[index] if 0 <= index < len(texte) else "?"
        eintraege.append(f"{treffer.group(2)} — Antworten: {' | '.join(texte)} (richtig: {richtig})")
    if eintraege:
        return eintraege
    for treffer in reihe.finditer(skript):
        optionen = [text for _, text in re.findall(r"([\"'])(.*?)\1", treffer.group(3))]
        index = int(treffer.group(5))
        richtig = optionen[index] if 0 <= index < len(optionen) else "?"
        eintraege.append(f"{treffer.group(2)} — Antworten: {' | '.join(optionen)} (richtig: {richtig})")
    return eintraege


# -- Datenstrukturen im Skript ------------------------------------------

ZEICHENKETTE = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`", re.S)
DEKLARATION = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\[")
FELD = re.compile(
    r"""([A-Za-z_$][\w$]*|"[^"\n]*"|'[^'\n]*')\s*:\s*"""
    r"""("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|-?\d+(?:\.\d+)?|true|false|null)"""
)
PRIMITIV = re.compile(r"""\"((?:[^"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'|(-?\d+(?:\.\d+)?)""")


def _klammer_ende(text: str, start: int) -> int:
    """Position hinter der Klammer, die die Klammer bei ``start`` schließt."""
    paare = {"[": "]", "{": "}", "(": ")"}
    stapel: list[str] = []
    stelle = start
    while stelle < len(text):
        zeichen = text[stelle]
        if zeichen in "\"'`":
            treffer = ZEICHENKETTE.match(text, stelle)
            if treffer:
                stelle = treffer.end()
                continue
        if zeichen in paare:
            stapel.append(paare[zeichen])
        elif stapel and zeichen == stapel[-1]:
            stapel.pop()
            if not stapel:
                return stelle + 1
        stelle += 1
    return -1


def _wert(roh: str) -> str:
    if roh[:1] in "\"'":
        return roh[1:-1].replace('\\"', '"').replace("\\'", "'")
    return roh


def _objekte(inhalt: str) -> list[dict[str, str]]:
    objekte: list[dict[str, str]] = []
    stelle = 0
    while True:
        start = inhalt.find("{", stelle)
        if start < 0:
            break
        ende = _klammer_ende(inhalt, start)
        if ende < 0:
            break
        felder: dict[str, str] = {}
        for schluessel, wert in FELD.findall(inhalt[start + 1:ende - 1]):
            felder.setdefault(schluessel.strip("\"'"), _wert(wert))
        if felder:
            objekte.append(felder)
        stelle = ende
    return objekte


def _auszaehlung(objekte: list[dict[str, str]]) -> list[str]:
    """Wie oft ein Wert vorkommt — damit niemand „sechs Fachkräfte" schätzt."""
    zeilen: list[str] = []
    for schluessel in objekte[0]:
        werte = [objekt[schluessel] for objekt in objekte if schluessel in objekt]
        if len(werte) < 0.8 * len(objekte):
            continue
        haeufig = Counter(werte)
        wahrheitswerte = set(haeufig) <= {"true", "false"}
        if wahrheitswerte or 1 < len(haeufig) <= 6 and len(haeufig) < len(werte):
            zeilen.append(
                f"{schluessel}: " + ", ".join(f"{wert} ×{anzahl}" for wert, anzahl in haeufig.most_common())
            )
    return zeilen


def _daten(skript: str, quiz_gefunden: bool) -> tuple[list[str], list[tuple[int, int, str]]]:
    """Datenstrukturen als Tabellen statt als Code.

    Gibt zusätzlich die Fundstellen zurück, damit die Programmlogik dieselben
    Daten nicht noch einmal als Code zeigt.
    """
    teile: list[str] = []
    fundstellen: list[tuple[int, int, str]] = []
    for treffer in DEKLARATION.finditer(skript):
        start = treffer.end() - 1
        ende = _klammer_ende(skript, start)
        if ende < 0:
            continue
        name = treffer.group(1)
        inhalt = skript[start + 1:ende - 1]
        if "{" in inhalt:
            objekte = [objekt for objekt in _objekte(inhalt) if len(objekt) >= 2]
            if len(objekte) < 2:
                continue
            fundstellen.append((start, ende, name))
            if quiz_gefunden:
                # Fragen und Antworten stehen schon im Quizteil.
                continue
            zeilen = [
                f"{nummer}. " + " · ".join(f"{schluessel}: {wert}" for schluessel, wert in objekt.items())
                for nummer, objekt in enumerate(objekte[:40], 1)
            ]
            if len(objekte) > 40:
                zeilen.append(f"… und {len(objekte) - 40} weitere")
            zaehlung = _auszaehlung(objekte)
            teile.append(
                f"DATEN IM SKRIPT – {name} ({len(objekte)} Einträge):\n" + "\n".join(zeilen)
                + ("\nAuszählung: " + " | ".join(zaehlung) if zaehlung else "")
            )
        else:
            werte = [next((teil for teil in gruppe if teil), "") for gruppe in PRIMITIV.findall(inhalt)]
            werte = [wert for wert in werte if wert]
            if len(werte) < 2 or sum(map(len, werte)) > 800:
                continue
            fundstellen.append((start, ende, name))
            teile.append(f"DATEN IM SKRIPT – {name}: " + " | ".join(werte))
        if len(teile) >= 6:
            break
    return teile, fundstellen


KOMMENTAR = re.compile(r"/\*(.*?)\*/|(?:^|(?<=[\s;{}(),]))//[ \t]?([^\n]*)", re.S | re.M)


def _kommentare(skript: str) -> list[str]:
    """Was der Autor über seinen Code geschrieben hat — oft die Regeln selbst."""
    gefunden: list[str] = []
    for treffer in KOMMENTAR.finditer(skript):
        text = treffer.group(1) if treffer.group(1) is not None else treffer.group(2)
        text = re.sub(r"\n\s*\*+", " ", text or "")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"^[\s*=\-–—#]+|[\s*=\-–—#]+$", "", text).strip()
        if len(text) < 4 or not re.search(r"[A-Za-zÄÖÜäöüß]{3,}", text) or text in gefunden:
            continue
        gefunden.append(text[:300])
        if len(gefunden) >= 40:
            break
    return gefunden


MARKUP = re.compile(r"</?[a-zA-Z][^>]*>")


def _programmlogik(skript: str, fundstellen: list[tuple[int, int, str]]) -> str:
    """Die Logik des Skripts — ohne Daten, Kommentare und Markup-Bausteine."""
    teile: list[str] = []
    letzte = 0
    for start, ende, name in sorted(fundstellen):
        teile.append(skript[letzte:start])
        teile.append(f"[/* Daten „{name}“ – siehe DATEN IM SKRIPT */]")
        letzte = ende
    teile.append(skript[letzte:])
    code = "".join(teile)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"(^|[\s;{}(),])//[^\n]*", r"\1", code, flags=re.M)
    # HTML in Zeichenketten ist Markup, keine Logik — und genau das, was ein
    # Modell sonst als Seite zurückgibt.
    code = ZEICHENKETTE.sub(
        lambda m: m.group(0)[0] + "…HTML…" + m.group(0)[-1] if MARKUP.search(m.group(0)) else m.group(0),
        code,
    )
    zeilen = [zeile.rstrip() for zeile in code.splitlines() if zeile.strip()]
    text = "\n".join(zeilen).strip()
    if len(text) > LOGIK_GRENZE:
        text = text[:LOGIK_GRENZE].rsplit("\n", 1)[0] + "\n… (gekürzt)"
    return text


CODEZEICHEN = re.compile(r"[{}();=<>]|=>|px\b|rgba?\(|var\(|getElement|querySelector|\\n")
# „use strict", „tbody tr", „.slot.sel" — Selektoren und Direktiven, kein Text.
SELEKTORARTIG = re.compile(r"[a-z0-9 .#>:_\-\[\]=\"']+")


def _textstellen(skript: str) -> list[str]:
    """Für Menschen geschriebene Zeichenketten aus einem Skript, in Reihenfolge."""
    gesehen: set[str] = set()
    ergebnis: list[str] = []
    for _, text in re.findall(r"([\"'`])((?:(?!\1).){8,300}?)\1", skript):
        text = text.strip()
        if len(text.split()) < 2 or CODEZEICHEN.search(text) or text in gesehen:
            continue
        if SELEKTORARTIG.fullmatch(text) and len(text.split()) <= 3:
            continue
        gesehen.add(text)
        ergebnis.append(text)
    return ergebnis


def _gestaltung(stile: str) -> list[str]:
    zeilen: list[str] = []
    farben = [farbe.lower() for farbe in re.findall(r"#[0-9a-fA-F]{3,8}\b", stile)]
    if farben:
        haeufig = [farbe for farbe, _ in Counter(farben).most_common(8)]
        zeilen.append("Farben: " + ", ".join(haeufig))
    merkmale = []
    if "backdrop-filter" in stile:
        merkmale.append("Glas-Effekt (backdrop-filter, durchscheinende Flächen)")
    if "gradient(" in stile:
        merkmale.append("Farbverläufe")
    animationen = re.findall(r"@keyframes\s+([\w-]+)", stile)
    if animationen:
        merkmale.append("Animationen: " + ", ".join(dict.fromkeys(animationen)))
    if "@media" in stile:
        merkmale.append("passt sich an Bildschirmgrößen an (@media)")
    if "@media print" in stile:
        merkmale.append("eigene Druckansicht")
    if merkmale:
        zeilen.append("Merkmale: " + "; ".join(merkmale))
    umbrueche = sorted({
        int(breite) for breite in re.findall(r"@media[^{]*?\((?:max|min)-width\s*:\s*(\d+)px", stile)
    })
    if umbrueche:
        zeilen.append("Umbruch für schmale Bildschirme bei: " + ", ".join(f"{b} px" for b in umbrueche))
    raster = list(dict.fromkeys(
        re.sub(r"\s+", " ", spalten).strip()
        for spalten in re.findall(r"grid-template-columns\s*:\s*([^;}]+)", stile)
    ))
    if raster:
        zeilen.append("Raster (Spalten): " + "; ".join(raster[:4]))
    return zeilen


def _funktionen(skript: str) -> list[str]:
    zeilen: list[str] = []
    namen = re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", skript)
    namen += re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\([^)]*\)|[\w$]+)\s*=>", skript)
    if namen:
        zeilen.append("Skriptfunktionen: " + ", ".join(dict.fromkeys(namen)))
    ereignisse = re.findall(r"addEventListener\(\s*[\"'](\w+)[\"']", skript)
    ereignisse += re.findall(r"\.on(click|change|input|submit)\s*=", skript)
    if ereignisse:
        zeilen.append("Reagiert auf: " + ", ".join(dict.fromkeys(ereignisse)))
    if "localStorage" in skript:
        zeilen.append("Speichert Daten im Browser (localStorage)")
    if "window.print" in skript:
        zeilen.append("Kann die Seite drucken bzw. als PDF ausgeben")
    return zeilen


def ist_html(text: str) -> bool:
    kopf = text.lstrip()[:400].lower()
    if kopf.startswith(("<!doctype html", "<html")):
        return True
    return len(re.findall(r"</?[a-z][a-z0-9]*[\s>]", text[:20_000], re.I)) >= 12


def html_auszug(html: str) -> str:
    """Was eine HTML-Seite zeigt und tut — lesbar, ohne HTML und CSS."""
    leser = _Leser()
    try:
        leser.feed(html)
        leser.close()
    except Exception:                                        # noqa: BLE001
        pass
    skript = "\n".join(leser.skripte)
    stile = "\n".join(leser.stile)
    teile = [
        f"QUELLE: HTML-Seite{' „' + leser.titel + '“' if leser.titel else ''} "
        f"(Quelltext mit {len(html):,} Zeichen)".replace(",", "."),
    ]
    if leser.zeilen:
        teile.append("INHALT DER SEITE (von oben nach unten):\n" + "\n".join(leser.zeilen))
    quiz = _quizdaten(skript)
    daten, fundstellen = _daten(skript, bool(quiz))
    if quiz:
        teile.append(
            f"DATEN IM SKRIPT ({len(quiz)} Einträge):\n"
            + "\n".join(f"{nummer}. {eintrag}" for nummer, eintrag in enumerate(quiz, 1))
        )
    teile.extend(daten)
    if not quiz:
        texte = _textstellen(skript)
        if texte:
            teile.append("TEXTE IM SKRIPT (z. B. Meldungen):\n" + "\n".join(f"- {t}" for t in texte[:60]))
    kommentare = _kommentare(skript)
    if kommentare:
        teile.append(
            "HINWEISE IM QUELLTEXT (Kommentare des Autors, in Reihenfolge):\n"
            + "\n".join(f"- {kommentar}" for kommentar in kommentare)
        )
    gestaltung = _gestaltung(stile)
    if gestaltung:
        teile.append("GESTALTUNG:\n" + "\n".join(f"- {zeile}" for zeile in gestaltung))
    funktionen = _funktionen(skript)
    if funktionen:
        teile.append("FUNKTIONEN:\n" + "\n".join(f"- {zeile}" for zeile in funktionen))
    logik = _programmlogik(skript, fundstellen)
    if len(logik) >= PROGRAMM_MINDESTLOGIK:
        teile.append(
            "PROGRAMMLOGIK (JavaScript-Auszug, nur damit du Regeln und Abläufe "
            "verstehst — nicht ausgeben; Markup ist durch …HTML… ersetzt):\n" + logik
        )
    auszug = "\n\n".join(teile)
    if len(auszug) > MAX_AUSZUG:
        auszug = auszug[:MAX_AUSZUG] + "\n… (gekürzt)"
    return auszug


HINWEIS_HTML = (
    "MARKIERTER INHALT WAR HTML-CODE: Der Quelltext einer HTML-Seite wurde für "
    "dich in Inhalt, Skriptdaten, Kommentare, Gestaltung und Funktionen zerlegt — "
    "in der Reihenfolge von oben nach unten. Bei einem Programm folgt ein Auszug "
    "der Programmlogik, nur damit du Regeln und Abläufe verstehst. Gib keinen "
    "HTML-, CSS- oder JavaScript-Code aus, auch nicht auszugsweise. Übernimm "
    "Anzahlen und Werte aus den DATEN und ihrer Auszählung, statt sie zu schätzen. "
    "Wende den Skill auf das an, was die Seite zeigt, vermittelt und tut: Ein Brief "
    "vermittelt diesen Inhalt dem Empfänger und nennt das Thema im Betreff. Ein "
    "Protokoll geht die Seite von oben nach unten durch. Eine Erklärung erklärt "
    "Inhalt und Funktionsweise. Ein Bericht, eine Analyse, eine Zusammenfassung "
    "oder eine Präsentation behandeln die Seite als Gegenstand."
)
HINWEIS_CODE = (
    "MARKIERTER INHALT ENTHÄLT PROGRAMMCODE ({sprache}): Gib den Code nicht "
    "unverändert oder leicht abgewandelt zurück. Wende den Skill auf das an, was "
    "der Code tut und bewirkt, und gib das Ergebnis in der Form des Skills aus."
)


def markierten_inhalt_aufbereiten(prompt: str, skills: list[str]) -> tuple[str, str]:
    """Bereitet den markierten Block eines Skill-Auftrags auf.

    Gibt den neuen Auftrag und einen Systemhinweis zurück. Ohne markierten
    Block, ohne Code oder bei rein umformenden Skills bleibt alles unverändert.
    """
    treffer = MARKIERUNG.search(prompt or "")
    if not treffer or not skills or set(skills) <= UMFORMENDE_SKILLS:
        return prompt, ""
    inhalt = treffer.group(2)
    hinweis = ""
    if HTML_ZAUN.search(inhalt):
        neu = HTML_ZAUN.sub(lambda m: html_auszug(m.group(1)), inhalt)
        hinweis = HINWEIS_HTML
    elif ist_html(inhalt):
        neu = html_auszug(inhalt)
        hinweis = HINWEIS_HTML
    else:
        neu = inhalt
        sprachen = [
            sprache or "unbenannt" for sprache, code in CODE_ZAUN.findall(inhalt)
            if len(code.strip().splitlines()) >= 4
        ]
        if sprachen:
            hinweis = HINWEIS_CODE.format(sprache=", ".join(dict.fromkeys(sprachen)))
    if neu == inhalt:
        return prompt, hinweis
    return prompt[:treffer.start(2)] + neu + prompt[treffer.end(2):], hinweis


def auftragstext(prompt: str) -> str:
    """Der Auftrag ohne den markierten Block.

    Weichen wie „der Nutzer will eine HTML-Datei" dürfen nur den Auftrag lesen,
    nie den markierten Inhalt: Eine markierte Seite mit dem Knopf „Plan
    generieren" galt sonst selbst als Wunsch nach einer neuen HTML-Datei.
    """
    return MARKIERUNG.sub("", prompt or "").strip()


ECHOANFANG = re.compile(
    r"^\s*(?:```\s*(?:html?|xhtml|css|javascript|js|jsx|tsx?|vue|svelte|php|xml)\b"
    r"|<!doctype\s+html|<html\b|<head\b|<style\b|<script\b|<body\b)",
    re.I,
)


def ist_codeecho(text: str) -> bool:
    """Beginnt eine Skill-Antwort mit Code statt mit dem Ergebnis?"""
    anfang = (text or "")[:600]
    return bool(ECHOANFANG.search(anfang)) or "<!doctype html" in anfang.lower()
