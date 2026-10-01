# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Grenzen für Modellausgaben — zentral und einstellbar.

Gefunden im Tabellenkalkulations-Stresstest am 21.09.2026: Eine Änderung an
einer Anwendung von 7.609 Zeichen lieferte nach 587 Sekunden 217.048 Zeichen
mit 112 Änderungsblöcken und endete mit `length` — die Antwort war
abgeschnitten, wurde aber wie eine fertige behandelt.

Zwei Regeln folgen daraus:

1. **Abgeschnitten ist nicht fertig.** Endet eine Generierung mit einem
   Grund wie `length`, ist sie unvollständig, egal wie brauchbar der Text
   aussieht.
2. **Ein Wächter beobachtet jede Generierung.** Die Grenzen sind relativ zur
   aktiven Anwendung, damit große Anwendungen nicht an festen Zahlen
   scheitern. Eine weiche Grenze meldet nur („ungewöhnlich groß“), eine harte
   bricht die Generierung kontrolliert ab.

Jede Grenze lässt sich über eine Umgebungsvariable einstellen
(`JOSHI_GRENZE_<NAME>`), zum Beispiel `JOSHI_GRENZE_HART_FAKTOR=6`. Die
Grenzen einer einzelnen Stufe im gestuften Modus heißen auch
`JOSHI_STAGE_SOFT_SECONDS`, `JOSHI_STAGE_HARD_SECONDS`,
`JOSHI_STAGE_SOFT_OUTPUT`, `JOSHI_STAGE_HARD_OUTPUT` und
`JOSHI_STAGE_MAX_PATCH_BLOCKS`.

Gemessen wird die ganze erzeugte Menge — sichtbarer Text **und** Denkstrom.
Gefunden im Killer-Retest am 21.09.2026: Stufe 2 „dachte“ 13 Minuten lang,
ohne ein sichtbares Zeichen zu schreiben; kein Größenlimit griff.
"""
from __future__ import annotations

import os
import zlib
from dataclasses import dataclass, fields

# Gründe, mit denen Modellschichten eine abgeschnittene Ausgabe melden.
ABGESCHNITTEN = {
    "length", "max_tokens", "max_output_tokens", "output_limit", "truncated",
    "limit", "context_length", "model_length", "max_length",
}


def ist_abgeschnitten(grund: str | None) -> bool:
    return str(grund or "").strip().lower() in ABGESCHNITTEN


@dataclass(frozen=True)
class Grenzen:
    # Ausgabe im Verhältnis zur aktiven Anwendung (Zeichen).
    weich_faktor: float = 4.0
    hart_faktor: float = 10.0
    # Untergrenzen, damit kleine Anwendungen normal wachsen dürfen.
    weich_minimum: int = 60_000
    hart_minimum: int = 160_000
    # Neubau (noch keine aktive Anwendung): nur gegen Ausreißer.
    neu_weich: int = 150_000
    neu_hart: int = 720_000
    # Änderungsblöcke: relativ zur Dateigröße (ein Block je N Zeichen).
    bloecke_weich_minimum: int = 25
    bloecke_hart_minimum: int = 60
    zeichen_je_block_weich: int = 1000
    zeichen_je_block_hart: int = 400
    # Dauer einer einzelnen Generierung.
    weich_sekunden: int = 240
    hart_sekunden: int = 900
    # Wiederholung: Kompressionsrate der letzten Zeichen (Schleifen komprimieren extrem).
    wiederholung_quote: float = 0.04
    wiederholung_fenster: int = 16_000
    wiederholung_ab: int = 24_000
    # Denkstrom: Wer ein Vielfaches der Anwendung „denkt“, ohne zu schreiben,
    # läuft davon. Gemessen am 27.09.2026: 625.000 Zeichen Denken für eine
    # Neufassung von 62.000 Zeichen, erst nach 628 s gestoppt.
    denk_faktor: float = 3.0
    denk_minimum: int = 150_000
    denk_neu: int = 300_000
    # Gestufter Modus: ab so vielen Pflichtkriterien (siehe aenderung.komplexitaet).
    stufen_ab_kriterien: int = 6
    stufen_ab_zeichen: int = 1500
    max_stufen: int = 8
    # Eigenes Budget je Stufe: Eine Stufe ist ein kleiner, geprüfter Schritt.
    stufe_weich_sekunden: int = 180
    stufe_hart_sekunden: int = 480
    stufe_weich_ausgabe: int = 60_000
    stufe_hart_ausgabe: int = 150_000
    stufe_max_bloecke: int = 40

    @classmethod
    def aus_umgebung(cls) -> "Grenzen":
        werte = {}
        for feld in fields(cls):
            roh = os.getenv(f"JOSHI_GRENZE_{feld.name.upper()}", "").strip() \
                or os.getenv(_STUFEN_NAMEN.get(feld.name, "-"), "").strip()
            if not roh:
                continue
            try:
                werte[feld.name] = type(feld.default)(float(roh))
            except ValueError:
                continue
        return cls(**werte)

    def zeichen(self, basis: int) -> tuple[int, int]:
        """Ohne aktive Anwendung (Neubau) nur gegen Ausreißer, sonst relativ."""
        if basis <= 0:
            return self.neu_weich, self.neu_hart
        return (max(self.weich_minimum, int(basis * self.weich_faktor)),
                max(self.hart_minimum, int(basis * self.hart_faktor)))

    def denken(self, basis: int) -> int:
        return self.denk_neu if basis <= 0 else max(self.denk_minimum, int(basis * self.denk_faktor))

    def bloecke(self, basis: int) -> tuple[int, int]:
        return (max(self.bloecke_weich_minimum, basis // max(1, self.zeichen_je_block_weich)),
                max(self.bloecke_hart_minimum, basis // max(1, self.zeichen_je_block_hart)))

    def stufe(self, basis: int) -> tuple[int, int, int, int]:
        """Budget einer Stufe: (weich Zeichen, hart Zeichen, weich Blöcke, hart Blöcke).

        Eine ganze Neufassung der aktuellen Datei bleibt erlaubt (1,5 × Größe),
        ein Monster-Aufruf nicht — und nie mehr als die globale harte Grenze.
        """
        global_hart = self.zeichen(basis)[1]
        hart = min(global_hart, max(self.stufe_hart_ausgabe, int(basis * 1.5)))
        weich = min(hart, max(self.stufe_weich_ausgabe, basis))
        return weich, hart, max(1, self.stufe_max_bloecke // 2), self.stufe_max_bloecke


_STUFEN_NAMEN = {
    "stufe_weich_sekunden": "JOSHI_STAGE_SOFT_SECONDS",
    "stufe_hart_sekunden": "JOSHI_STAGE_HARD_SECONDS",
    "stufe_weich_ausgabe": "JOSHI_STAGE_SOFT_OUTPUT",
    "stufe_hart_ausgabe": "JOSHI_STAGE_HARD_OUTPUT",
    "stufe_max_bloecke": "JOSHI_STAGE_MAX_PATCH_BLOCKS",
}


@dataclass
class Signal:
    art: str        # ausgabe | bloecke | dauer | wiederholung | abgeschnitten | konflikt
    stufe: str      # weich | hart
    text: str       # für Menschen
    technik: str    # für die technischen Details
    kontext: str = ""   # z. B. „Schritt 3“ im gestuften Modus

    def als_dict(self) -> dict[str, str]:
        return {"art": self.art, "stufe": self.stufe, "text": self.text, "technik": self.technik,
                "kontext": self.kontext}


UNGEWOEHNLICH_GROSS = "Die Änderung ist ungewöhnlich groß."
LIMIT_TEXT = "Die Modellantwort erreichte ihr Ausgabelimit. Der unvollständige Stand wurde nicht übernommen."


class Waechter:
    """Beobachtet eine laufende Generierung.

    `basis` ist die Größe der aktiven Anwendung (0 bei einem Neubau),
    `bloecke` sagt, ob Änderungsblöcke erwartet werden (dann zählt auch ihre
    Zahl). Weiche Signale kommen je Art nur einmal; das erste harte Signal
    beendet die Generierung.
    """

    def __init__(self, basis: int, *, bloecke: bool, grenzen: Grenzen | None = None, stufe: str = "") -> None:
        self.grenzen = grenzen or Grenzen.aus_umgebung()
        self.basis = max(0, basis)
        self.bloecke_zaehlen = bloecke
        self.stufe = stufe
        if stufe:
            (self.weich_zeichen, self.hart_zeichen,
             self.weich_bloecke, self.hart_bloecke) = self.grenzen.stufe(self.basis)
            self.weich_sekunden, self.hart_sekunden = self.grenzen.stufe_weich_sekunden, self.grenzen.stufe_hart_sekunden
        else:
            self.weich_zeichen, self.hart_zeichen = self.grenzen.zeichen(self.basis)
            self.weich_bloecke, self.hart_bloecke = self.grenzen.bloecke(self.basis)
            self.weich_sekunden, self.hart_sekunden = self.grenzen.weich_sekunden, self.grenzen.hart_sekunden
        self.hart_denken = min(self.grenzen.denken(self.basis), self.hart_zeichen)
        self.gemeldet: set[str] = set()
        self.signale: list[Signal] = []

    def _signal(self, art: str, stufe: str, text: str, technik: str) -> Signal | None:
        schluessel = f"{art}:{stufe}"
        if schluessel in self.gemeldet:
            return None
        self.gemeldet.add(schluessel)
        if self.stufe:
            text = {"dauer": f"{self.stufe} dauert ungewöhnlich lange." if stufe == "weich"
                    else f"{self.stufe} dauerte zu lange.",
                    "ausgabe": f"{self.stufe} wird ungewöhnlich groß." if stufe == "weich"
                    else f"{self.stufe} wurde zu groß.",
                    "bloecke": f"{self.stufe} ändert ungewöhnlich viele Stellen."}.get(art, text)
        signal = Signal(art, stufe, text, technik, self.stufe)
        self.signale.append(signal)
        return signal

    def pruefen(self, text: str, sekunden: float, denken: int = 0) -> Signal | None:
        """Liefert das nächste neue Signal (hart vor weich) oder None.

        `denken` ist die Zahl der Zeichen im Denkstrom: Auch sie kosten Tokens
        und Zeit — ein Modell, das nur denkt, wächst ebenfalls über die Grenze.
        """
        g = self.grenzen
        zeichen = len(text) + max(0, denken)
        bloecke = text.count(">>>>>>>") if self.bloecke_zaehlen else 0
        verhaeltnis = (f"{zeichen:,} Zeichen" + (f" (davon {denken:,} Denkstrom)" if denken else "")
                       + f" bei einer Anwendung von {self.basis:,} Zeichen").replace(",", ".")
        if denken > self.hart_denken:
            return self._signal("denken", "hart", "Das Modell dachte ungewöhnlich lange, ohne zu schreiben.",
                                f"{denken:,} Zeichen Denkstrom bei {len(text):,} Zeichen Ausgabe "
                                f"(Grenze {self.hart_denken:,}) — die Antwort wurde verworfen".replace(",", "."))
        if denken > self.hart_denken // 2 and not text:
            signal = self._signal("denken", "weich", "Das Modell denkt ungewöhnlich lange.",
                                  f"{denken:,} Zeichen Denkstrom ohne sichtbare Ausgabe".replace(",", "."))
            if signal:
                return signal
        if zeichen > self.hart_zeichen:
            return self._signal("ausgabe", "hart", UNGEWOEHNLICH_GROSS,
                                f"Ausgabe über der harten Grenze ({verhaeltnis}; Grenze {self.hart_zeichen:,})"
                                .replace(",", "."))
        if bloecke > self.hart_bloecke:
            return self._signal("bloecke", "hart", UNGEWOEHNLICH_GROSS,
                                f"{bloecke} Änderungsblöcke (harte Grenze {self.hart_bloecke}) — "
                                "praktisch eine Neufassung")
        if sekunden > self.hart_sekunden:
            return self._signal("dauer", "hart", "Die Modellantwort dauerte ungewöhnlich lange.",
                                f"{sekunden:.0f} s ohne Abschluss (harte Grenze {self.hart_sekunden} s)")
        if zeichen >= g.wiederholung_ab:
            ende = text[-g.wiederholung_fenster:].encode("utf-8", "ignore")
            quote = len(zlib.compress(ende, 6)) / max(1, len(ende))
            if quote < g.wiederholung_quote:
                return self._signal("wiederholung", "hart", "Die Modellantwort wiederholt sich.",
                                    f"Die letzten {len(ende):,} Zeichen komprimieren auf {quote:.1%} — "
                                    "eine Schleife".replace(",", "."))
        if zeichen > self.weich_zeichen:
            return self._signal("ausgabe", "weich", UNGEWOEHNLICH_GROSS,
                                f"Ausgabe über der weichen Grenze ({verhaeltnis})")
        if bloecke > self.weich_bloecke:
            return self._signal("bloecke", "weich", UNGEWOEHNLICH_GROSS,
                                f"{bloecke} Änderungsblöcke (weiche Grenze {self.weich_bloecke})")
        if sekunden > self.weich_sekunden:
            return self._signal("dauer", "weich", "Die Modellantwort dauert ungewöhnlich lange.",
                                f"{sekunden:.0f} s (weiche Grenze {self.weich_sekunden} s)")
        return None

    @property
    def weich(self) -> bool:
        return any(s.stufe == "weich" for s in self.signale)
