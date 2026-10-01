# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Daten aus dem Netz: JOSHI recherchiert, das Modell setzt nur ein.

Gefunden am 29.09.2026 am PC-Konfigurator: „Aktualisiere die Preise“ kann ein
Modell nicht aus dem Gedächtnis. Es erfindet Zahlen. Deshalb gehört die
Recherche fest in den Ablauf:

    ERKENNEN   — der Wunsch verlangt aktuelle Preise (bedarf)
    POSITIONEN — welche Produkte stehen mit welchem Preis in der App (positionen_lesen, Modell liest nur ab)
    SUCHEN     — je Produkt breit über DuckDuckGo, bevorzugt Preisvergleiche
                 (geizhals, idealo) und bei Hardware mindfactory
    AUSWERTEN  — Euro-Beträge aus Kurztexten und geladenen Seiten, plausibel
                 zum bisherigen Preis; der günstigste plausible gewinnt, mit Quelle
    EINSETZEN  — das Modell bekommt die Tabelle und darf nur diese Werte nutzen
    PRÜFEN     — die neue Version muss die recherchierten Preise wirklich enthalten

Nicht gefundene Preise bleiben, wie sie sind — geraten wird nie.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from app.joshi.html_werk import json_aus_antwort

# ------------------------------------------------------------------ Erkennen
_PREIS = re.compile(r"\bpreis\w*|\bkost\w*|\b€|\beuro\b|\bmarktpreis\w*|\bpreislage\b", re.I)
_AKTUELL = re.compile(r"aktuali\w*|aktuell\w*|tatsächlich\w*|tatsaechlich\w*|echte[nrs]?\b|reale[nrs]?\b|heutige[nrs]?\b|"
                      r"\bheute\b|marktüblich\w*|recherch\w*|internet|\bweb\b|online|abgleich\w*|nachschlag\w*|"
                      r"stimm\w* (?:nicht|noch)|veraltet\w*|up.?to.?date|anpass\w*", re.I)

HARDWARE = re.compile(r"\b(?:cpu|gpu|prozessor|grafikkarte|mainboard|motherboard|ram|arbeitsspeicher|ssd|nvme|"
                      r"netzteil|gehäuse|kühler|ryzen|intel|core i\d|geforce|rtx|radeon|rx ?\d|ddr\d|pc)\b", re.I)
BEVORZUGT_HARDWARE = ("mindfactory.de", "geizhals.de", "idealo.de")
BEVORZUGT_ALLGEMEIN = ("idealo.de", "geizhals.de")
# Seiten, die zu Preisen oft nur Werbung, Tests oder Foren liefern.
MEIDEN = ("youtube.com", "reddit.com", "wikipedia.org", "facebook.com", "instagram.com", "tiktok.com",
          "computerbase.de/forum", "pcgameshardware.de/forum")


def bedarf(text: str) -> str:
    """„preise“, wenn der Wunsch aktuelle Preise aus dem Netz verlangt — sonst leer."""
    text = text or ""
    return "preise" if _PREIS.search(text) and _AKTUELL.search(text) else ""


# ------------------------------------------------------------------ Positionen
POSITIONEN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "positionen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kategorie": {"type": "string"},
                    "preis": {"type": "number"},
                },
                "required": ["name", "preis"],
            },
        },
    },
    "required": ["positionen"],
}

POSITIONEN_SYSTEM = """Du liest aus dem Code einer Webanwendung ab, welche Produkte mit welchem Preis darin stehen. Nichts erfinden, nichts schätzen.

Antworte nur mit JSON: {"positionen": [{"name": "...", "kategorie": "...", "preis": 199.0}, ...]}
- name: die genaue Produktbezeichnung, wie sie im Code steht (Hersteller und Modell, z. B. "AMD Ryzen 5 7600")
- kategorie: kurz (z. B. "CPU", "Grafikkarte")
- preis: der Preis in Euro als Zahl, wie er im Code steht
Nur echte, kaufbare Produkte mit konkretem Namen — keine Platzhalter wie "Midi-Tower Standard", keine Summen, keine Beispielrechnungen. Höchstens 40 Einträge, die wichtigsten zuerst."""

_ALLGEMEIN = re.compile(r"^(?:standard|basis|budget|einsteiger|mittel|midi|mini|tower|gehäuse|kühler|netzteil|"
                        r"\d+\s*(?:gb|tb|w|mm)\b.*)$", re.I)


# „Midi-Tower Standard“, „Tower-Kühler Basis“: Platzhalter, keine kaufbaren Produkte.
_GENERISCH = {"standard", "basis", "generisch", "beliebig", "einfach", "allgemein", "normal", "günstig", "budget",
              "beispiel", "no", "name", "noname"}


def positionen_normalisieren(roh: Any, grenze: int = 40) -> list[dict[str, Any]]:
    daten = json_aus_antwort(roh)
    eintraege = (daten or {}).get("positionen") if isinstance(daten, dict) else None
    ergebnis: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    for eintrag in eintraege or []:
        if not isinstance(eintrag, dict):
            continue
        name = re.sub(r"\s+", " ", str(eintrag.get("name") or "")).strip()[:120]
        try:
            preis = float(eintrag.get("preis"))
        except (TypeError, ValueError):
            continue
        # Nur Namen, nach denen man suchen kann: mindestens ein Wort mit Ziffer
        # oder zwei Wörter, keine reinen Gattungsbegriffe.
        if len(name) < 4 or preis <= 0 or preis > 50_000 or name.lower() in gesehen:
            continue
        generisch = set(re.findall(r"[a-zäöüß]+", name.lower())) & _GENERISCH
        if _ALLGEMEIN.match(name) or not (re.search(r"\d", name) or len(name.split()) >= 2) \
                or (generisch and not re.search(r"\d", name)):
            continue
        gesehen.add(name.lower())
        ergebnis.append({"name": name, "kategorie": str(eintrag.get("kategorie") or "")[:40], "preis": preis})
        if len(ergebnis) >= grenze:
            break
    return ergebnis


async def positionen_lesen(zugang: Any, modell: str, html: str, verbrauch: dict[str, int]) -> list[dict[str, Any]]:
    nachrichten = [{"role": "system", "content": POSITIONEN_SYSTEM},
                   {"role": "user", "content": f"Code der Anwendung:\n<datei>\n{html[:90_000]}\n</datei>"}]
    try:
        roh = await zugang.strukturiert(modell, nachrichten, POSITIONEN_SCHEMA, temperatur=0.0, verbrauch=verbrauch)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 – ohne Positionen keine Recherche
        roh = {}
    return positionen_normalisieren(roh)


# ------------------------------------------------------------------ Preise finden
_BETRAG = re.compile(
    r"(?:(?:ab|für|nur|preis:?|je)\s*)?"
    r"(?:€\s*(?P<a>\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)"
    r"|(?P<b>\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:\.\d{3})+|\d+)\s*(?:€|eur\b|euro\b))",
    re.I)


def betraege(text: str) -> list[float]:
    """Alle Euro-Beträge im Text („ab 179,00 €“, „€ 1.049“, „199 EUR“)."""
    werte = []
    for treffer in _BETRAG.finditer(text or ""):
        roh = (treffer.group("a") or treffer.group("b") or "").replace(" ", "")
        if not roh:
            continue
        if "," in roh:
            roh = roh.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", roh):
            roh = roh.replace(".", "")
        try:
            wert = float(roh)
        except ValueError:
            continue
        if 1 <= wert <= 50_000:
            werte.append(wert)
    return werte


def _kern(name: str) -> list[str]:
    """Die unterscheidenden Teile eines Produktnamens („ryzen“, „7600“ statt „amd“)."""
    teile = re.findall(r"[a-z0-9]+", (name or "").lower())
    unwichtig = {"amd", "intel", "nvidia", "the", "und", "mit", "gb", "tb", "boxed", "tray", "edition"}
    return [t for t in teile if t not in unwichtig and (len(t) >= 3 or t.isdigit())]


# Zusätze, die ein anderes Produkt bezeichnen: „RTX 4060 Ti“ ist keine „RTX 4060“,
# „990 EVO Plus“ keine „990 EVO“, „7600X“ kein „7600“.
VARIANTEN = {"ti", "super", "plus", "pro", "xt", "xtx", "x3d", "max", "ultra", "mini", "lite", "se", "gre"}


# 29.09.2026: „Ryzen 7 8700G für 858,99 €“ kam von einer Komplett-PC-Seite.
_SYSTEM = re.compile(r"komplettsystem|komplett-pc|gaming-pc|\bpc\b[- ]?(?:system|business)|business\s*\d|"
                     r"notebook|laptop|\bterra\b|\bomen\b|\bbundle\b|aufrüstkit|aufruestkit|mini-pc|workstation|"
                     r"/komplettsystem|desktop-pc", re.I)


def fremde_variante(text: str, name: str) -> bool:
    """Nennt ein kurzer Text (Titel, URL) eine Variante, die der Name nicht hat („Plus“, „Ti“)?"""
    eigene = set(re.findall(r"[a-z0-9]+", name.lower()))
    return bool((set(re.findall(r"[a-z0-9]+", (text or "").lower())) & VARIANTEN) - eigene)


def passt_zum_produkt(text: str, name: str, varianten: bool = True) -> bool:
    kern = _kern(name)
    if not kern:
        return False
    woerter = re.findall(r"[a-z0-9]+", (text or "").lower())
    menge = set(woerter)
    zahlen = [t for t in kern if any(z.isdigit() for z in t)]
    if zahlen and not all(z in menge for z in zahlen):
        return False
    if sum(t in menge for t in kern) < max(1, (len(kern) + 1) // 2):
        return False
    if not varianten:
        # Lange Seiten nennen „RTX 5070“ und „RTX 5070 Ti“ nebeneinander: Hier
        # genügt, dass das Produkt überhaupt vorkommt.
        return any(woerter[n] in zahlen and (n + 1 >= len(woerter) or woerter[n + 1] not in VARIANTEN
                                              or woerter[n + 1] in set(re.findall(r"[a-z0-9]+", name.lower())))
                   for n in range(len(woerter))) if zahlen else True
    eigene = set(re.findall(r"[a-z0-9]+", name.lower()))
    # Direkt hinter der Modellnummer darf kein fremder Zusatz stehen.
    for nummer, wort in enumerate(woerter[:-1]):
        if wort in zahlen and woerter[nummer + 1] in VARIANTEN and woerter[nummer + 1] not in eigene:
            return False
    return True


def plausibel(wert: float, alt: float) -> bool:
    """Ein neuer Preis darf sich vom alten stark, aber nicht absurd unterscheiden."""
    return alt <= 0 or 0.45 * alt <= wert <= 2.5 * alt


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


@dataclass
class Fund:
    name: str
    alt: float
    neu: float | None = None
    quelle: str = ""
    url: str = ""
    kandidaten: list[dict[str, Any]] = field(default_factory=list)
    unsicher: bool = False

    def als_dict(self) -> dict[str, Any]:
        return {"name": self.name, "alt": self.alt, "neu": self.neu, "quelle": self.quelle, "url": self.url,
                "unsicher": self.unsicher,
                "kandidaten": self.kandidaten[:6]}


def auswaehlen(fund: Fund, bevorzugt: tuple[str, ...]) -> Fund:
    """Der günstigste plausible Preis — bei Gleichstand eine bevorzugte Quelle."""
    gute = [k for k in fund.kandidaten if plausibel(k["preis"], fund.alt)]
    if not gute:
        return fund
    rang = {host: n for n, host in enumerate(bevorzugt)}
    # Preisvergleiche und Wunschhändler zuerst; Suchlisten von Shops („/s?k=“,
    # „search“) zeigen oft Nachbarmodelle (RTX 4060 Ti statt 4060) — nur als Rückfall.
    vorrang = [k for k in gute if k["quelle"] in rang]
    sauber = [k for k in gute if not re.search(r"/s\?|[?&](?:k|q|query|search)=|/search", k["url"])]
    pool = vorrang or sauber or gute
    beste = min(pool, key=lambda k: (k["preis"], rang.get(k["quelle"], 99)))
    # Ein einzelner Beleg mit großem Sprung (weiße Sonderedition für 727 € statt
    # einer RTX 4060 für 300 €) ist zu unsicher: dann bleibt der alte Preis.
    bestaetigt = sum(abs(k["preis"] - beste["preis"]) <= 0.15 * beste["preis"] for k in gute) >= 2
    # Ohne bisherigen Preis gibt es keinen Vergleich — dann müssen zwei Belege übereinstimmen
    # (29.09.2026: „Deepcool Assassin IV für 9 €“ aus einem einzelnen Treffer).
    if not bestaetigt and (fund.alt <= 0 or abs(beste["preis"] - fund.alt) > 0.4 * fund.alt):
        fund.unsicher = True
        return fund
    fund.neu, fund.quelle, fund.url = round(beste["preis"], 2), beste["quelle"], beste["url"]
    return fund


def aus_treffern(fund: Fund, treffer: list[dict[str, str]], seiten: bool = False) -> None:
    """Sammelt Preiskandidaten aus Suchtreffern (Kurztext) oder geladenen Seiten (Text)."""
    for eintrag in treffer:
        url = str(eintrag.get("url") or "")
        host = _host(url)
        if not host or any(m in url for m in MEIDEN):
            continue
        # Kurztexte von Preisvergleichen reihen mehrere Produkte aneinander — ein
        # Preis zählt dort nur aus dem Titel des passenden Treffers
        # („Samsung SSD 990 EVO 1TB ab € 189,00“).
        titel = str(eintrag.get("title") or "")
        if fremde_variante(f"{titel} {urlparse(url).path}", fund.name):
            continue
        if _SYSTEM.search(f"{titel} {urlparse(url).path}") and not _SYSTEM.search(fund.name):
            continue
        if not seiten:
            if not passt_zum_produkt(titel, fund.name):
                continue
            bereiche = [titel]
        else:
            text = f"{titel} {eintrag.get('content') or ''}"
            if not passt_zum_produkt(titel, fund.name) and not passt_zum_produkt(text[:3000], fund.name):
                continue
            # Nur Beträge in der Nähe des Produktnamens — sonst gewinnt Zubehör.
            bereiche = [titel] + [b for b in _umgebung(text, fund.name) if passt_zum_produkt(b, fund.name)]
        werte = [w for b in bereiche for w in betraege(b)]
        for wert in werte[:6]:
            fund.kandidaten.append({"preis": wert, "quelle": host, "url": url})


def _umgebung(text: str, name: str, weite: int = 300) -> list[str]:
    klein = text.lower()
    kern = [t for t in _kern(name) if any(z.isdigit() for z in t)] or _kern(name)[:1]
    stellen = [m.start() for t in kern for m in re.finditer(re.escape(t), klein)][:8]
    return [text[max(0, s - weite):s + weite] for s in stellen]


def suchanfragen(name: str, hardware: bool) -> list[str]:
    bevorzugt = BEVORZUGT_HARDWARE if hardware else BEVORZUGT_ALLGEMEIN
    anfragen = [f"{name} Preis", f"{name} ab €"]
    anfragen += [f"site:{host} {name}" for host in bevorzugt[:2]]
    return anfragen


def _ddg(anfrage: str) -> list[dict[str, str]]:
    from ddgs import DDGS

    try:
        ergebnisse = DDGS().text(anfrage, region="de-de", safesearch="moderate", max_results=6) or []
    except Exception:  # noqa: BLE001 – eine gescheiterte Suche ist nur ein fehlender Treffer
        return []
    return [{"title": str(e.get("title") or ""), "url": str(e.get("href") or e.get("url") or ""),
             "snippet": str(e.get("body") or "")} for e in ergebnisse]


async def recherchieren(positionen: list[dict[str, Any]], *,
                        melden: Callable[[int, int, str], Any] | None = None,
                        suche: Callable[[str], list[dict[str, str]]] = _ddg,
                        seiten_laden: Callable[[list[dict[str, str]]], Any] | None = None,
                        parallel: int = 4) -> list[Fund]:
    """Sucht je Position Preise. `suche` und `seiten_laden` sind für Tests austauschbar."""
    hardware = sum(bool(HARDWARE.search(f"{p['name']} {p.get('kategorie', '')}")) for p in positionen) * 2 >= len(positionen)
    bevorzugt = BEVORZUGT_HARDWARE if hardware else BEVORZUGT_ALLGEMEIN
    grenze = asyncio.Semaphore(parallel)
    erledigt = 0

    async def eine(position: dict[str, Any]) -> Fund:
        nonlocal erledigt
        fund = Fund(position["name"], float(position.get("preis") or 0))
        async with grenze:
            treffer: list[dict[str, str]] = []
            for anfrage in suchanfragen(fund.name, hardware):
                treffer += await asyncio.to_thread(suche, anfrage)
            aus_treffern(fund, treffer)
            if not any(plausibel(k["preis"], fund.alt) for k in fund.kandidaten) and seiten_laden:
                # Kurztexte ohne Preis: die besten Seiten laden und dort suchen.
                wichtig = sorted({t["url"]: t for t in treffer if t.get("url")}.values(),
                                 key=lambda t: (0 if _host(t["url"]) in bevorzugt else 1))[:3]
                geladen = await seiten_laden(wichtig)
                aus_treffern(fund, list(geladen or []), seiten=True)
        auswaehlen(fund, bevorzugt)
        erledigt += 1
        if melden:
            ergebnis = melden(erledigt, len(positionen), fund.name)
            if asyncio.iscoroutine(ergebnis):
                await ergebnis
        return fund

    return list(await asyncio.gather(*(eine(p) for p in positionen)))


async def seiten_laden_standard(treffer: list[dict[str, str]]) -> list[dict[str, str]]:
    """Lädt Seiten über denselben geschützten Abruf wie die Websuche im Chat."""
    import httpx

    from app.intelligence import enrich_web_results

    async with httpx.AsyncClient() as client:
        return await enrich_web_results(treffer, client)


# ------------------------------------------------------------------ Einsetzen und Prüfen
def stand() -> str:
    return datetime.date.today().strftime("%d.%m.%Y")


def auftrag_text(funde: list[Fund]) -> str:
    """Die Tabelle für das Modell: nur diese Werte, mit Stand und Quelle."""
    gefunden = [f for f in funde if f.neu is not None]
    fehlend = [f for f in funde if f.neu is None]
    zeilen = [f"RECHERCHIERTE AKTUELLE PREISE (Stand {stand()}, von JOSHI im Internet gesucht):"]
    zeilen += [f"- {f.name}: {_euro(f.neu)} (bisher {_euro(f.alt)}; Quelle: {f.quelle} — {f.url})" for f in gefunden]
    if fehlend:
        zeilen += ["", "Nicht gefunden oder nicht eindeutig — diese Preise bleiben unverändert: "
                   + "; ".join(f.name for f in fehlend)]
    zeilen += ["", "So setzt du das um:",
               "- Ersetze die bisherigen Preise dieser Produkte durch genau die recherchierten Werte. Erfinde keine "
               "anderen Preise und runde nicht.",
               "- Lege die Preise gesammelt als Daten ab (ein Objekt oder eine Liste mit Preis, Quelle und Link je "
               "Produkt), damit sie sich später austauschen lassen.",
               f"- Zeige in der Anwendung gut sichtbar „Preise Stand {stand()}“ und nenne die Quellen (Händler).",
               "- Alle Berechnungen (Summen, Budget, Alternativen) nutzen die neuen Preise."]
    return "\n".join(zeilen)


def _euro(wert: float | None) -> str:
    if wert is None:
        return "–"
    return f"{wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _formen(wert: float) -> list[str]:
    """Wie ein Preis im Code stehen kann: 179, 179.0, 179.00, 179,00, 1.049,00, 1049."""
    formen = {f"{wert:.2f}", f"{wert:.2f}".replace(".", ","), _euro(wert).replace(" €", "")}
    if float(wert).is_integer():
        formen |= {str(int(wert)), f"{int(wert)}.0"}
    else:
        formen.add(f"{wert:g}")
    return sorted(formen, key=len, reverse=True)


def abgleich(html: str, funde: list[Fund]) -> tuple[list[Fund], list[Fund]]:
    """(übernommen, fehlend): Steht der recherchierte Preis im Code der neuen Version?"""
    uebernommen, fehlend = [], []
    for fund in (f for f in funde if f.neu is not None):
        treffer = any(re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d])", html) for form in _formen(fund.neu))
        (uebernommen if treffer else fehlend).append(fund)
    return uebernommen, fehlend


def als_json(funde: list[Fund]) -> str:
    return json.dumps({"stand": stand(), "positionen": [f.als_dict() for f in funde]}, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ Selbst einsetzen
# Gefunden am 29.09.2026: Das Modell setzte den Preisblock vor die Definition
# von CAT_KEYS — „Cannot access before initialization“, App tot. Preise tauschen
# ist Datenarbeit: JOSHI ersetzt sie selbst, beim jeweiligen Produkt im Code.
_PREISSCHLUESSEL = r"(?:price|preis|kosten|cost|eur|euro|betrag|amount|p)"


def einsetzen(html: str, funde: list[Fund]) -> tuple[str, list[Fund], list[Fund]]:
    """Ersetzt je Produkt den alten Preis durch den recherchierten.

    Gesucht wird der exakte Produktname in Anführungszeichen und dahinter —
    im selben Objekt, vor der nächsten schließenden Klammer — ein Preisfeld mit
    dem alten Wert (`price:200`, `"preis": 200.00`). Nur eindeutige Stellen
    werden ersetzt; alles andere bleibt für das Modell.
    """
    eingesetzt, offen = [], []
    for fund in (f for f in funde if f.neu is not None):
        erledigt = False
        for name_treffer in re.finditer(r"([\"'`])" + re.escape(fund.name) + r"\1", html):
            ende = html.find("}", name_treffer.end())
            anfang = html.rfind("{", 0, name_treffer.start())
            if ende < 0 or anfang < 0 or ende - anfang > 1500:
                continue
            objekt = html[anfang:ende]
            alt = _zahl_muster(fund.alt)
            muster = re.compile(rf"(\b{_PREISSCHLUESSEL}[\"']?\s*:\s*){alt}(?![\d.])", re.I)
            stellen = list(muster.finditer(objekt))
            if len(stellen) != 1:
                continue
            neu_wert = f"{fund.neu:.2f}".rstrip("0").rstrip(".")
            objekt_neu = objekt[:stellen[0].start()] + stellen[0].group(1) + neu_wert + objekt[stellen[0].end():]
            html = html[:anfang] + objekt_neu + html[ende:]
            erledigt = True
            break
        (eingesetzt if erledigt else offen).append(fund)
    return html, eingesetzt, offen


def _zahl_muster(wert: float) -> str:
    ganz = int(wert) if float(wert).is_integer() else None
    if ganz is not None:
        return rf"{ganz}(?:\.0+)?"
    return re.escape(f"{wert:.2f}").replace(r"\.", r"\.") + "?"


def anzeige_auftrag(funde: list[Fund], eingesetzt: list[Fund]) -> str:
    """Was das Modell noch tun soll, wenn JOSHI die Preise schon eingesetzt hat."""
    quellen = sorted({f.quelle for f in eingesetzt if f.quelle})
    rest = [f for f in funde if f.neu is not None and f not in eingesetzt]
    # 29.09.2026: Hier stand „Deine Aufgabe jetzt nur: …“ — das Modell ließ daraufhin den
    # eigentlichen Änderungswunsch (Budget-Logik, Upgrades) komplett liegen.
    zeilen = [f"HINWEIS ZU DEN PREISEN: JOSHI hat die Preise von {len(eingesetzt)} Produkten bereits selbst im Code "
              f"aktualisiert (im Netz recherchiert, Stand {stand()}). Ändere diese Preiswerte NICHT.",
              "", "Setze den Änderungswunsch oben vollständig um und zeige ZUSÄTZLICH gut sichtbar "
              f"„Preise Stand {stand()}“ und die Quellen: {', '.join(quellen)}."]
    if rest:
        zeilen += ["", "Zusätzlich diese Preise, die JOSHI im Code nicht eindeutig fand, einsetzen:"]
        zeilen += [f"- {f.name}: {_euro(f.neu)} (bisher {_euro(f.alt)})" for f in rest]
    return "\n".join(zeilen)


# ------------------------------------------------------------------ Katalog für einen Neubau
# 29.09.2026: „Erstelle einen Konfigurator — das LLM soll zuerst aktuelle
# Hardware-Daten im Netz ansehen und inkl. Preis und Leistung einsetzen.“
# JOSHI liest Bestenlisten und Preisvergleiche, das Modell zieht daraus nur
# Produkte, die wörtlich darin stehen, und JOSHI recherchiert deren Preise.
_NETZ = re.compile(r"aktuell\w*|internet|\bnetz\b|\bweb\b|online|recherch\w*|echte[nrs]?\b|heutige[nrs]?\b|marktpreis\w*|"
                   r"tagesaktuell\w*|neueste[nrs]?\b|\b20\d\d\b", re.I)
_DATEN = re.compile(r"preis\w*|hardware|produkt\w*|modell\w*|komponent\w*|daten\b|leistung\w*|benchmark\w*|"
                    r"angebot\w*|katalog\w*", re.I)


def bedarf_neubau(text: str) -> bool:
    """Verlangt ein Neubau Produktdaten aus dem Netz („aktuelle Hardware inkl. Preis und Leistung“)?"""
    return bool(_NETZ.search(text or "") and _DATEN.search(text or "")
                and re.search(r"netz|internet|web|online|recherch|aktuell|echte", text or "", re.I))


KATEGORIEN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"kategorien": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "suche": {"type": "string"}}, "required": ["name", "suche"]}}},
    "required": ["kategorien"],
}
PRODUKTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"produkte": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "leistung": {"type": "number"}, "merkmale": {"type": "string"},
        "preis": {"type": "number"}}, "required": ["name"]}}},
    "required": ["produkte"],
}


async def _json_mit_nachfrage(zugang: Any, modell: str, nachrichten: list[dict[str, Any]], schema: dict[str, Any],
                              schluessel: str, verbrauch: dict[str, int]) -> Any:
    """Strukturierter Aufruf; kommt kein JSON mit `schluessel` (29.09.2026: ein Modell schrieb statt der
    Kategorienliste gleich die ganze App), wird einmal ausdrücklich nachgefragt."""
    for versuch in range(2):
        try:
            roh = await zugang.strukturiert(modell, nachrichten, schema, temperatur=0.0, verbrauch=verbrauch)
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001
            roh = {}
        daten = json_aus_antwort(roh)
        if isinstance(daten, dict) and isinstance(daten.get(schluessel), list) and daten[schluessel]:
            return daten
        nachrichten = [*nachrichten, {"role": "assistant", "content": str(roh)[:300]},
                       {"role": "user", "content": f"Das war kein JSON. Antworte jetzt NUR mit dem JSON-Objekt "
                                                   f"{{\"{schluessel}\": [...]}} — kein Code, keine Anwendung, kein Text."}]
    return {}


# Wenn das Modell keine Kategorien liefert: für PC-Hardware bewährte Standardsuchen.
PC_KATEGORIEN = [("Prozessor", "CPU Bestenliste {jahr} Gaming Kaufberatung"),
                 ("Grafikkarte", "Grafikkarten Bestenliste {jahr} Preis Leistung"),
                 ("Mainboard", "Mainboard Bestenliste {jahr} AM5 LGA1851"),
                 ("Arbeitsspeicher", "DDR5 RAM Bestenliste {jahr}"),
                 ("SSD", "NVMe SSD Bestenliste {jahr}"),
                 ("Netzteil", "Netzteil Bestenliste {jahr}"),
                 ("CPU-Kühler", "CPU Kühler Bestenliste {jahr}"),
                 ("Gehäuse", "PC Gehäuse Bestenliste {jahr}")]


async def kategorien_planen(zugang: Any, modell: str, auftrag: str, verbrauch: dict[str, int],
                            jahr: int) -> list[dict[str, str]]:
    nachrichten = [
        {"role": "system", "content": (
            "Du planst eine Internetrecherche für eine Anwendung. Nenne die Produktkategorien, deren aktuelle "
            "Produkte die Anwendung als Daten braucht, und je eine gute deutsche Suchanfrage nach einer aktuellen "
            f"Bestenliste oder Kaufberatung (mit Jahreszahl {jahr}). Höchstens 8 Kategorien. Nur JSON: "
            '{"kategorien": [{"name": "Grafikkarte", "suche": "Grafikkarten Bestenliste ' + str(jahr) + '"}]}')},
        {"role": "user", "content": "Auftrag an die spätere Anwendung — NICHT umsetzen, nur die Kategorien für die "
                                    f"Recherche nennen:\n<auftrag>\n{auftrag[:4000]}\n</auftrag>"}]
    daten = await _json_mit_nachfrage(zugang, modell, nachrichten, KATEGORIEN_SCHEMA, "kategorien", verbrauch)
    ergebnis = []
    for eintrag in (daten or {}).get("kategorien") or [] if isinstance(daten, dict) else []:
        if isinstance(eintrag, dict) and str(eintrag.get("name") or "").strip():
            name = str(eintrag["name"]).strip()[:40]
            ergebnis.append({"name": name, "suche": str(eintrag.get("suche") or f"{name} Bestenliste {jahr}")[:120]})
    if not ergebnis and HARDWARE.search(auftrag or ""):
        ergebnis = [{"name": n, "suche": s.format(jahr=jahr)} for n, s in PC_KATEGORIEN]
    return ergebnis[:8]


async def produkte_aus_texten(zugang: Any, modell: str, kategorie: str, texte: str,
                              verbrauch: dict[str, int], grenze: int = 6) -> list[dict[str, Any]]:
    """Das Modell nennt nur Produkte, die wörtlich in den gelesenen Texten stehen — JOSHI prüft das nach."""
    nachrichten = [
        {"role": "system", "content": (
            f"Aus den folgenden Texten aktueller Webseiten ziehst du die aktuell empfohlenen Produkte der Kategorie "
            f"„{kategorie}“. Nur Produkte, deren genauer Name im Text steht — nichts aus dem Gedächtnis ergänzen. "
            f"Höchstens {grenze}, von günstig bis stark gemischt. Je Produkt: name (genau wie im Text), "
            "leistung (relativer Index 1–100 innerhalb der Kategorie, abgeleitet aus Tests und Rangfolge im Text), "
            "merkmale (die wichtigsten technischen Daten aus dem Text, kurz), preis (Euro, falls im Text genannt, "
            'sonst 0). Nur JSON: {"produkte": [...]}')},
        {"role": "user", "content": f"Texte der Webseiten:\n<texte>\n{texte[:14_000]}\n</texte>"}]
    daten = await _json_mit_nachfrage(zugang, modell, nachrichten, PRODUKTE_SCHEMA, "produkte", verbrauch)
    produkte = []
    for eintrag in (daten or {}).get("produkte") or [] if isinstance(daten, dict) else []:
        if not isinstance(eintrag, dict):
            continue
        name = re.sub(r"\s+", " ", str(eintrag.get("name") or "")).strip()[:100]
        # Ein Produktname, kein Werbesatz: „Mini-Tower-Gehäuse, Vollseitiges transparen…“ fliegt raus.
        if "," in name or len(name) > 60 or not re.search(r"\d", name) and len(name.split()) < 2 \
                or re.search(r"\bvon\b|gehäuse,|pc-gehäuse|mini-tower-gehäuse", name, re.I):
            continue
        # Nachprüfen: Steht das Produkt wirklich in den gelesenen Texten?
        if len(name) < 4 or not passt_zum_produkt(texte, name, varianten=False):
            continue
        try:
            leistung = max(1.0, min(100.0, float(eintrag.get("leistung") or 0))) if eintrag.get("leistung") else 0.0
            preis = max(0.0, float(eintrag.get("preis") or 0))
        except (TypeError, ValueError):
            leistung, preis = 0.0, 0.0
        produkte.append({"name": name, "kategorie": kategorie, "leistung": leistung,
                         "merkmale": str(eintrag.get("merkmale") or "")[:200], "preis": preis})
        if len(produkte) >= grenze:
            break
    return produkte


async def katalog_erstellen(zugang: Any, modell: str, auftrag: str, verbrauch: dict[str, int], *,
                            melden: Callable[[str], Any] | None = None,
                            suche: Callable[[str], list[dict[str, str]]] = _ddg,
                            seiten_laden: Callable[[list[dict[str, str]]], Any] | None = seiten_laden_standard,
                            ) -> tuple[list[dict[str, Any]], list[Fund]]:
    """(Katalog, Preisfunde): nur Produkte aus echten Webseiten und mit gefundenem Preis."""
    async def sag(text: str) -> None:
        if melden:
            ergebnis = melden(text)
            if asyncio.iscoroutine(ergebnis):
                await ergebnis

    jahr = datetime.date.today().year
    kategorien = await kategorien_planen(zugang, modell, auftrag, verbrauch, jahr)
    await sag(f"Kategorien: {', '.join(k['name'] for k in kategorien) or 'keine'}")
    produkte: list[dict[str, Any]] = []
    for nummer, kategorie in enumerate(kategorien, 1):
        await sag(f"Aktuelle Produkte suchen · {nummer} von {len(kategorien)} · {kategorie['name']}")
        gefunden: list[dict[str, Any]] = []
        treffer: list[dict[str, str]] = []
        texte = ""
        # Fällt eine Suche aus (29.09.2026: „Mainboard: 0 Seiten“, „Netzteil: 0 Produkte“),
        # versucht JOSHI zwei Ersatzanfragen — sonst erfindet das Modell die Kategorie.
        for anfrage in (kategorie["suche"], f"{kategorie['name']} Kaufberatung {jahr}",
                        f"site:geizhals.de {kategorie['name']} Bestseller"):
            treffer = [t for t in await asyncio.to_thread(suche, anfrage)
                       if t.get("url") and not any(m in t["url"] for m in MEIDEN)][:5]
            if not treffer:
                continue
            geladen = list(await seiten_laden(treffer[:3]) or []) if seiten_laden else []
            texte = "\n\n".join(f"{t.get('title', '')}\n{t.get('snippet', '')}" for t in treffer)
            texte += "\n\n" + "\n\n".join(f"{g.get('title', '')}\n{str(g.get('content') or '')[:4000]}" for g in geladen)
            gefunden = await produkte_aus_texten(zugang, modell, kategorie["name"], texte, verbrauch)
            if len(gefunden) >= 3:
                break
        await sag(f"{kategorie['name']}: {len(treffer)} Seiten, {len(texte)} Zeichen gelesen, "
                  f"{len(gefunden)} Produkte: {', '.join(p['name'] for p in gefunden)[:160]}")
        produkte += gefunden
    if not produkte:
        return [], []
    await sag(f"Preise recherchieren für {len(produkte)} Produkte …")

    async def preis_melden(fertig: int, gesamt: int, name: str) -> None:
        await sag(f"Preise recherchieren · {fertig} von {gesamt} · {name}")

    funde = await recherchieren([{"name": p["name"], "kategorie": p["kategorie"], "preis": p["preis"]} for p in produkte],
                                melden=preis_melden, suche=suche, seiten_laden=seiten_laden)
    katalog = []
    for produkt, fund in zip(produkte, funde):
        if fund.neu is None:
            continue
        katalog.append({**produkt, "preis": fund.neu, "quelle": fund.quelle, "url": fund.url})
    return katalog, [f for f in funde if f.neu is not None]


def katalog_text(katalog: list[dict[str, Any]]) -> str:
    zeilen = [f"AKTUELLE PRODUKTDATEN AUS DEM INTERNET (von JOSHI recherchiert, Stand {stand()}) — verbindlich:",
              "Kategorie | Produkt | Preis | Leistung (Index 1–100, Einschätzung aus Tests) | Merkmale | Quelle"]
    for p in katalog:
        zeilen.append(f"{p['kategorie']} | {p['name']} | {_euro(p['preis'])} | {int(p['leistung']) or '–'} | "
                      f"{p['merkmale'] or '–'} | {p['quelle']}")
    zeilen += ["", "So nutzt du diese Daten:",
               "- Verwende genau diese Produkte mit genau diesen Preisen (als Zahl im Code, z. B. price: 149.89) als "
               "Datenbasis der Anwendung. Erfinde keine weiteren Produkte und keine anderen Preise.",
               "- Lege die Daten gesammelt als ein Objekt/Array ab (Name, Kategorie, Preis, Leistung, Merkmale, Quelle).",
               f"- Zeige gut sichtbar „Preise Stand {stand()}“ und die Quellen (Händler).",
               "- Leistungsindex als Einschätzung kennzeichnen; technische Kompatibilität nur aus den Merkmalen ableiten.",
               "- Alle Komponenten stehen in EINER gemeinsamen Datenstruktur. Jede Kategorie, die die Anwendung braucht, "
               "hat darin mindestens drei Produkte (günstig, mittel, stark), damit Downgrade und Upgrade immer möglich sind.",
               "- Fehlt eine Kategorie oben oder hat sie zu wenige Produkte, ergänze sie in derselben Struktur mit "
               "realistischen Richtwerten und kennzeichne diese sichtbar als „Richtwert“.",
               "- Jede Auswahl, jeder Startwert und jedes Zurücksetzen verweist nur auf Produkte, die in dieser "
               "Datenstruktur existieren — nie auf eine ID, die es nicht gibt."]
    return "\n".join(zeilen)
