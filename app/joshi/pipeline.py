# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Der feste JOSHI-Ablauf.

    VERSTEHEN → BAUEN → VERBINDEN → PRÜFEN → (REPARIEREN → VERBINDEN → PRÜFEN)* → BEREIT

Das Modell wird mehrfach gefragt, aber der Ablauf gehört dem Code: feste
Phasen, höchstens zwei Reparaturen, kein offener Agentenkreislauf. „Bereit“
setzt allein der Prüfer — nie die Selbstauskunft des Modells.

Große Änderungen (seit dem Tabellenkalkulations-Stresstest vom 21.09.2026):

    ÄNDERUNGSLINIE → PLAN → SCHRITT 1 → PRÜFEN → … → SCHRITT n → PRÜFEN
                   → ENDABNAHME gegen den vollständigen Root-Vertrag → PROMOTION

Ein erneuter Versuch („versuch es erneut“) gehört zum selben Auftrag und
behält dessen Vertrag. Eine abgeschnittene Modellantwort ist nie fertig, ein
teilweise angewendeter Patch nie ein Erfolg, und nur ein vollständig
nachgewiesener Kandidat ersetzt die aktive Version — genau einmal.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app import database
from app.joshi import (abnahme, aenderung, dateien, grenzen, projekt, projektdateien, prompts, pruefer, recherche,
                        speicher)
from app.joshi.html_werk import (
    _ANFANG,
    Auszug,
    Patchbericht,
    aenderungsbloecke,
    asset_verweise,
    bloecke_einzeln,
    ersetzung_vorhanden,
    export_dokument,
    fortsetzung_anfuegen,
    html_aus_antwort,
    json_aus_antwort,
    titel_aus_html,
)
from app.joshi.jobs import Auftrag
from app.joshi.modell import Modellzugang

MAX_REPARATUREN = 2
MAX_FORTSETZUNGEN = 2
# Kleine Dateien schreibt das Modell schneller neu, als es Änderungsblöcke
# fehlerfrei kopiert.
KLEINE_DATEI = 7000
# Ab dieser Größe schreibt JOSHI eine Anwendung nach einem Patchkonflikt nicht
# mehr ganz neu, sondern arbeitet in geprüften Schritten weiter.
GROSSE_DATEI = 40_000
ZEICHEN_JE_TOKEN = 3.0
# Rechnet das Modell länger als vier Minuten ohne ein einziges Zeichen,
# hängt es.
STILLSTAND_SEKUNDEN = 240
# Je Schritt eines gestuften Auftrags höchstens eine Reparatur.
REPARATUREN_JE_STUFE = 1

SCHRITTE = {
    "bauen": [("verstehen", "Idee verstehen"), ("erstellen", "Produkt erstellen"),
              ("verbinden", "Funktionen verbinden"), ("pruefen", "Prüfen"), ("teilbar", "Teilbare Version")],
    "aendern": [("erstellen", "Änderung umsetzen"), ("verbinden", "Funktionen verbinden"),
                ("pruefen", "Prüfen"), ("teilbar", "Neue Version")],
    "reparieren": [("erstellen", "Fehler beheben"), ("verbinden", "Funktionen verbinden"),
                   ("pruefen", "Prüfen"), ("teilbar", "Neue Version")],
    "importieren": [("verstehen", "Aus dem Chat übernehmen"), ("verbinden", "Funktionen verbinden"),
                    ("pruefen", "Prüfen"), ("teilbar", "Teilbare Version")],
}
AKZEPTANZ = {"abnahme", "unbewiesen", "unbeweisbar"}
RETRY_HINWEIS = ("Schreib „versuch es erneut“ für einen weiteren Versuch mit demselben Auftrag — "
                 "oder „verwirf die Änderung“, um neu anzufangen.")


# Fall 06.10.2026: Ollama Cloud meldete nach ≈3.270 Tokens „Internal Server
# Error“ mitten im Strom. Die Modellschicht wiederholt nur vor dem ersten
# Zeichen (sonst doppelter Text); JOSHI verwirft den halben Text und fordert
# denselben Schritt neu an, statt den ganzen Auftrag abzubrechen.
STROM_WIEDERHOLUNG = (5.0, 20.0)
_VORUEBERGEHEND = re.compile(
    r"internal server error|bad gateway|service unavailable|gateway time-?out|overloaded|"
    r"\b50[0234]\b|vorzeitig beendet|brach mitten in der antwort ab|temporarily", re.IGNORECASE)


def strom_fehler_voruebergehend(fehler: BaseException) -> bool:
    """Nur echte, vorübergehende Dienstfehler der Modellschicht — keine eigenen
    Grenzen (Umsetzungsfehler), keine Limits, keine Anmeldefehler."""
    if type(fehler) is not RuntimeError:
        return False
    text = str(fehler)
    if re.search(r"limit|kontingent|anmeld|drossel|429", text, re.IGNORECASE):
        return False
    return bool(_VORUEBERGEHEND.search(text))


def nachweis_vergleich(vorherige: dict[str, Any] | None, bericht: "pruefer.Pruefbericht") -> tuple[int, int]:
    """Bestandene Pflichtpunkte (aktive Version, neuer Stand) — nur über dieselben Kriterien."""
    jetzt = {e.get("id"): e for e in bericht.abnahme.get("ergebnisse") or [] if e.get("pflicht")}
    vorher = {e.get("id"): e for e in (((vorherige or {}).get("pruefung") or {}).get("abnahme") or {}).get("ergebnisse") or []
              if e.get("pflicht")}
    gemeinsam = set(jetzt) & set(vorher)
    return (sum(vorher[i].get("status") == "PASS" for i in gemeinsam),
            sum(jetzt[i].get("status") == "PASS" for i in gemeinsam))


def tragfaehig(bericht: "pruefer.Pruefbericht") -> bool:
    """Läuft ohne Fehler und hat nichts verloren — darf als Ergebnis gelten,
    auch wenn der Wunsch (noch) nicht nachgewiesen ist."""
    return (not any(b.art == "fehler" for b in bericht.befunde)
            and not any("kleiner als vorher" in b.text for b in bericht.befunde))


class Umsetzungsfehler(RuntimeError):
    def __init__(self, text: str, technik: str = "") -> None:
        super().__init__(text)
        self.text = text
        self.technik = technik


class Grenzfall(Umsetzungsfehler):
    """Die Generierung überschritt ihre Grenzen: abgeschnitten, ausufernd oder Patchkonflikt.

    Kein Kandidat entsteht daraus. Bei einer Änderung versucht JOSHI den
    Auftrag danach in geprüften Schritten; sonst endet der Versuch kontrolliert.
    """

    def __init__(self, text: str, technik: str = "", *, art: str = "ausufernd") -> None:
        super().__init__(text, technik)
        self.art = art


class Beendet(Exception):
    """Der Nutzer hat den offenen Auftrag verworfen, ohne etwas Neues zu wollen."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


@dataclass
class Eingabe:
    text: str
    material: str = ""
    chat: str = ""
    bilder: list[dict[str, Any]] = field(default_factory=list)   # name, datei, mime, b64
    html: str = ""       # importieren: HTML aus dem Chat
    fehler: str = ""     # reparieren: im Browser gemeldeter Fehler
    # Aus dem Asset-/Eingabeordner gewählte Dateien (Build-Snapshot, eingaben.Auswahl)
    eingaben: list[Any] = field(default_factory=list)
    workspace: bool = False   # das Ergebnis gehört (auch) in ein Workspace-Projekt
    web: bool = False         # Web-Schalter: JOSHI recherchiert aktuelle Daten im Netz


def verstaendnis_normalisieren(roh: Any, auftrag: str) -> dict[str, Any]:
    roh = json_aus_antwort(roh)
    daten = roh if isinstance(roh, dict) else {}

    def liste(name: str, grenze: int) -> list[str]:
        werte = daten.get(name)
        if not isinstance(werte, list):
            return []
        return [str(w).strip()[:160] for w in werte if str(w).strip()][:grenze]

    titel = str(daten.get("titel") or "").strip().strip("„“\"'")[:60]
    if not titel:
        titel = " ".join(auftrag.split()[:5])[:60] or "Neues Produkt"
    return {
        "titel": titel,
        "zweck": str(daten.get("zweck") or "").strip()[:400],
        "art": str(daten.get("art") or "werkzeug")[:30],
        "funktionen": liste("funktionen", 8),
        "bedienelemente": liste("bedienelemente", 8),
        "daten": liste("daten", 8),
        "gestaltung": str(daten.get("gestaltung") or "").strip()[:300],
    }


def fokuswoerter(vertrag: dict[str, Any]) -> list[str]:
    """Wörter, nach denen die Bedienprobe Knöpfe bevorzugt: was der Vertrag bedienen will."""
    worte: list[str] = []
    for kriterium in vertrag.get("kriterien") or []:
        if kriterium.get("nachweis") not in {"bedienung", "ablauf"} and not kriterium.get("interaktion"):
            continue
        worte.extend(str(w) for w in kriterium.get("stichworte") or [])
        worte.extend(w for w in str(kriterium.get("id") or "").split("_") if len(w) >= 4)
    gesehen: list[str] = []
    for wort in worte:
        wort = wort.strip().lower()
        if len(wort) >= 3 and wort not in gesehen:
            gesehen.append(wort)
    return gesehen[:30]


def zahl(wert: int) -> str:
    return f"{wert:,}".replace(",", ".")


def _gliederung_kompakt(gliederung: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (gliederung or {}).items() if k not in {"markdown", "zustand"}}


def zip_noetig(intern: dict[str, Any]) -> bool:
    """Teilen als ZIP nur, wenn neben der HTML-Datei weitere Dateien nötig sind."""
    dateiliste = intern.get("dateien") or {}
    return bool(dateiliste.get("data") or dateiliste.get("medien"))


def _vertrag_und_plan(linie: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return ((linie or {}).get("vertrag"), (linie or {}).get("plan"))


class Lauf:
    def __init__(self, auftrag: Auftrag, *, user_id: str, produkt: dict[str, Any], art: str,
                 eingabe: Eingabe, modell: str, zugang: Modellzugang) -> None:
        self.auftrag = auftrag
        self.user_id = user_id
        self.produkt = produkt
        self.art = art
        self.eingabe = eingabe
        self.modell = modell
        self.zugang = zugang
        self.verbrauch = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0,
                          "eval_duration_ns": 0, "timed_calls": 0}
        # Sekunden, in denen wirklich ein Modell erzeugt hat. Nur daraus wird
        # Tok/s gerechnet: Rendern, Prüfen und Speichern gehören nicht dazu.
        self.modellsekunden = 0.0
        self.offene_zeichen = 0
        self.sieht_bilder = False
        # Abnahmevertrag und die Messwerte der zuletzt geprüften Version:
        # Daran entscheidet sich, ob ein Kandidat aktiv werden darf.
        self.vertrag: dict[str, Any] = {}
        self.baseline: dict[str, Any] = {}
        # Änderungslinie: Root-Auftrag, Versuch, Wunsch für das Modell.
        self.linie: dict[str, Any] | None = None
        self.protokoll: aenderung.Versuchsprotokoll | None = None
        self.wunsch = ""
        self.gestuft = False
        self.grenzen = grenzen.Grenzen.aus_umgebung()
        self.signale: list[grenzen.Signal] = []
        self.patch: Patchbericht | None = None
        self.ausgabe_zeichen = 0
        self.gruende: list[str] = []
        self.reparaturen = 0
        self.vollstaendig = True
        # Ergebnisgarantie: Schritte, die offen blieben (Titel, Grund), und der
        # letzte fehlerfreie Zwischenstand einer gestuften Änderung.
        self.offene_stufen: list[tuple[str, str]] = []
        self.zwischenstand = ""
        self.szenarien: dict[str, dict[str, Any]] = {}
        self.stufe_text = ""
        self.letzte_abnahme: dict[str, int] = {}
        # Gestufter Modus: die gerade laufende Stufe (für Wächter, Oberfläche, Usage).
        self.aktive_stufe: dict[str, Any] | None = None
        self.komplex: dict[str, Any] = {}
        # Ausgabe eines ordentlich beendeten Streams ohne Provider-Usage und
        # Ausgabe eines abgebrochenen Streams: beides bleibt Schätzung, aber
        # nur Letzteres ist unvollständig.
        self.abgeschlossen_geschaetzte_zeichen = 0
        self.abgebrochen_zeichen = 0
        # Der gespeicherte Vertrag mit zurückgestellten Kriterien; self.vertrag
        # ist davon nur, was jetzt zählt.
        self.vertrag_gesamt: dict[str, Any] = {}
        # Projekt-Workspace: warum JOSHI in Dateien arbeitet, und der zuletzt
        # bearbeitete Stand (für Checkpoint und Promotion).
        self.projekt_grund = ""
        # „nutz den Workspace“: Projektdateien auch unterhalb der Größenschwelle.
        self.projekt_erzwingen = False
        # Daten aus dem Netz (Preise): was JOSHI recherchiert hat — Grundlage
        # für den Auftrag an das Modell und für den Abgleich in der Abnahme.
        self.recherche_funde: list[recherche.Fund] = []
        self.recherche_html = ""
        # Allgemeine Recherche (Orte, Adressen, Termine …): Einträge mit Quelle.
        self.recherche_daten: list[dict[str, Any]] = []
        self.projekt_stand: projektdateien.Projekt | None = None

    # ------------------------------------------------------------ Meldungen
    async def melde(self, art: str, **daten: Any) -> None:
        await self.auftrag.melde(art, **daten)

    async def status(self, status: str, text: str = "") -> None:
        await self.melde("status", status=status, text=text)

    async def schritt(self, name: str, zustand: str, text: str = "") -> None:
        await self.melde("schritt", schritt=name, zustand=zustand, text=text)

    async def technik(self, text: str) -> None:
        await self.melde("technik", text=text[:2000])

    def pruefe_abbruch(self) -> None:
        if self.auftrag.abbruch.is_set():
            raise asyncio.CancelledError()

    def tokenwerte(self, *, zeichen: int = 0, seit: float = 0.0, laufend: bool = False) -> dict[str, Any]:
        """Wie viele Tokens dieser Lauf erzeugt hat — und in wie viel Modellzeit.

        Fertige Aufrufe zählen exakt (eval_count aus der Modellschicht). Der
        gerade laufende Strom wird bis zu seinem Ende geschätzt, wie im Chat;
        danach ersetzt die echte Zahl die Schätzung.
        """
        tatsaechlich = int(self.verbrauch["completion_tokens"])
        eingabe_tatsaechlich = int(self.verbrauch["prompt_tokens"])
        laufend_geschaetzt = int(round(zeichen / ZEICHEN_JE_TOKEN))
        abgeschlossen = int(round(self.abgeschlossen_geschaetzte_zeichen / ZEICHEN_JE_TOKEN))
        abgebrochen = int(round(self.abgebrochen_zeichen / ZEICHEN_JE_TOKEN))
        geschaetzt = laufend_geschaetzt + abgeschlossen
        unvollstaendig = abgebrochen
        fehlende_provider_ausgaben = max(0, int(self.verbrauch["calls"])
                                          - int(self.verbrauch.get("provider_output_usage_calls", 0)))
        if unvollstaendig:
            usage_status = "incomplete"
        elif geschaetzt or fehlende_provider_ausgaben:
            usage_status = "estimated"
        else:
            usage_status = "actual"
        return {"tokens": tatsaechlich + geschaetzt + unvollstaendig,
                # Getrennt: bestätigte Werte der Modellschicht und Schätzungen.
                "tokens_actual": tatsaechlich,
                "output_tokens_actual": tatsaechlich,
                "input_tokens_actual": eingabe_tatsaechlich,
                "eingabetokens": eingabe_tatsaechlich,  # kompatibler Name für ältere Oberflächen
                "output_tokens_estimated": geschaetzt,
                "output_tokens_incomplete": unvollstaendig,
                "laufend_geschaetzt": laufend_geschaetzt,
                "abgeschlossen_geschaetzt": abgeschlossen,
                "abgebrochen_geschaetzt": abgebrochen,
                "usage_status": usage_status,
                "geschaetzt": usage_status != "actual",
                "rate_geschaetzt": usage_status != "actual" or self.verbrauch["timed_calls"] < self.verbrauch["calls"],
                "modellsekunden": round(self.modellsekunden + seit, 4),
                "aufrufe": self.verbrauch["calls"], "laufend": laufend,
                "provider_input_usage_reported": bool(self.verbrauch.get("provider_input_usage_reported", False)),
                "provider_output_usage_reported": bool(self.verbrauch.get("provider_output_usage_reported", False)),
                "provider_input_usage_calls": int(self.verbrauch.get("provider_input_usage_calls", 0)),
                "provider_output_usage_calls": int(self.verbrauch.get("provider_output_usage_calls", 0))}

    def usage_stand(self) -> tuple[int, int, int, float, int, int, int, int, int]:
        return (self.verbrauch["prompt_tokens"], self.verbrauch["completion_tokens"], self.verbrauch["calls"],
                self.modellsekunden, len(self.gruende), self.abgeschlossen_geschaetzte_zeichen,
                self.abgebrochen_zeichen, int(self.verbrauch.get("provider_input_usage_calls", 0)),
                int(self.verbrauch.get("provider_output_usage_calls", 0)))

    def usage_seit(self, vorher: tuple[int, int, int, float, int, int, int, int, int], beginn: float) -> dict[str, Any]:
        """Usage einer Stufe: echte Werte der Modellschicht, Schätzung getrennt."""
        eingabe, ausgabe, aufrufe, sekunden, gruende, abgeschlossen, abgebrochen, input_calls, output_calls = vorher
        ausgabe_geschaetzt = int(round((self.abgeschlossen_geschaetzte_zeichen - abgeschlossen) / ZEICHEN_JE_TOKEN))
        ausgabe_unvollstaendig = int(round((self.abgebrochen_zeichen - abgebrochen) / ZEICHEN_JE_TOKEN))
        aufrufe_neu = self.verbrauch["calls"] - aufrufe
        fehlende_ausgaben = aufrufe_neu > (int(self.verbrauch.get("provider_output_usage_calls", 0)) - output_calls)
        status = "incomplete" if ausgabe_unvollstaendig else (
            "estimated" if ausgabe_geschaetzt or fehlende_ausgaben else "actual")
        gruende_neu = self.gruende[gruende:]
        return {"eingabe": self.verbrauch["prompt_tokens"] - eingabe,
                "ausgabe": self.verbrauch["completion_tokens"] - ausgabe,
                "input_tokens_actual": self.verbrauch["prompt_tokens"] - eingabe,
                "output_tokens_actual": self.verbrauch["completion_tokens"] - ausgabe,
                "output_tokens_estimated": ausgabe_geschaetzt,
                "output_tokens_incomplete": ausgabe_unvollstaendig,
                "aufrufe": aufrufe_neu,
                "sekunden": round(time.monotonic() - beginn, 1),
                "modellsekunden": round(self.modellsekunden - sekunden, 1),
                "gruende": gruende_neu,
                "finish_reason": gruende_neu[-1] if gruende_neu else "",
                "geschaetzt_abgeschlossen": ausgabe_geschaetzt,
                "geschaetzt_abgebrochen": ausgabe_unvollstaendig,
                "provider_input_usage_calls": int(self.verbrauch.get("provider_input_usage_calls", 0)) - input_calls,
                "provider_output_usage_calls": int(self.verbrauch.get("provider_output_usage_calls", 0)) - output_calls,
                "usage_status": status,
                "status": status}

    async def tokenstand(self, **werte: Any) -> None:
        werte.setdefault("zeichen", self.offene_zeichen)
        stand = self.tokenwerte(**werte)
        await self.melde("tokens", **stand)
        await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id,
                                verbrauch={**self.verbrauch, "tokenstand": stand})

    async def gemessen(self, aufruf: Any) -> Any:
        """Auch die kurzen Struktur-Aufrufe gehören zum Durchsatz dieses Laufs."""
        beginn = time.monotonic()
        dauer_vorher = self.verbrauch["eval_duration_ns"]
        ausgabe_vorher = self.verbrauch["completion_tokens"]
        aufrufe_vorher = self.verbrauch["calls"]
        provider_ausgabe_vorher = int(self.verbrauch.get("provider_output_usage_calls", 0))
        ergebnis: Any = None
        erhalten = False
        try:
            ergebnis = await aufruf
            erhalten = True
            return ergebnis
        finally:
            # Ein nicht-streamender Aufruf kann erfolgreich enden, ohne dass
            # sein Provider Tokenwerte zurückliefert. Sein Inhalt wird dann
            # transparent geschätzt statt als exakter Nullwert angezeigt.
            if (erhalten and self.verbrauch["calls"] > aufrufe_vorher
                    and self.verbrauch["completion_tokens"] == ausgabe_vorher
                    and int(self.verbrauch.get("provider_output_usage_calls", 0)) == provider_ausgabe_vorher):
                try:
                    zeichen = len(ergebnis) if isinstance(ergebnis, str) else len(json.dumps(ergebnis, ensure_ascii=False))
                except (TypeError, ValueError):
                    zeichen = 0
                self.abgeschlossen_geschaetzte_zeichen += max(0, zeichen)
            gemeldet = (self.verbrauch["eval_duration_ns"] - dauer_vorher) / 1e9
            self.modellsekunden += gemeldet or time.monotonic() - beginn
            await self.tokenstand()

    async def signal(self, signal: grenzen.Signal) -> None:
        """Ein Grenzsignal wird festgehalten; weiche Signale sieht der Nutzer einmal."""
        if any(s.art == signal.art and s.stufe == signal.stufe and s.kontext == signal.kontext for s in self.signale):
            return
        self.signale.append(signal)
        if self.protokoll is not None:
            self.protokoll.signale.append(signal.als_dict())
        await self.technik(f"[{signal.stufe}] {signal.text} {signal.technik}")
        if signal.stufe != "weich":
            return
        if signal.kontext:
            await self.melde("hinweis", text=signal.text)       # „Schritt 3 dauert ungewöhnlich lange.“
        elif not any(s.stufe == "weich" and not s.kontext for s in self.signale[:-1]):
            await self.melde("hinweis", text=signal.text + " JOSHI behält sie im Blick.")

    # -------------------------------------------------------------- Modell
    async def generieren(self, nachrichten: list[dict[str, Any]], fortschritt: str,
                         temperatur: float = 0.2, *, basis: int = 0, bloecke: bool = False) -> tuple[str, str]:
        dauer_vorher = self.verbrauch["eval_duration_ns"]
        self._strombeginn = None
        try:
            stufe = f"Schritt {self.aktive_stufe['nummer']}" if self.aktive_stufe else ""
            for versuch in range(len(STROM_WIEDERHOLUNG) + 1):
                try:
                    return await self._generieren(
                        nachrichten, fortschritt, temperatur,
                        grenzen.Waechter(basis, bloecke=bloecke, grenzen=self.grenzen, stufe=stufe))
                except RuntimeError as fehler:
                    if not strom_fehler_voruebergehend(fehler) or versuch >= len(STROM_WIEDERHOLUNG):
                        raise
                    await self.melde("hinweis", text="Der Modelldienst brach mitten in der Antwort ab "
                                                     "– JOSHI fordert denselben Schritt neu an.")
                    await self.technik(f"Strom abgebrochen ({str(fehler)[:160]}); "
                                       f"neuer Versuch {versuch + 2} in {STROM_WIEDERHOLUNG[versuch]:.0f} s.")
                    await asyncio.sleep(STROM_WIEDERHOLUNG[versuch])
                    self.pruefe_abbruch()
            raise AssertionError("unerreichbar")
        finally:
            gemeldet = (self.verbrauch["eval_duration_ns"] - dauer_vorher) / 1e9
            seit = time.monotonic() - self._strombeginn if self._strombeginn is not None else 0
            self.modellsekunden += gemeldet or seit
            await self.tokenstand(laufend=False)

    async def _generieren(self, nachrichten: list[dict[str, Any]], fortschritt: str,
                          temperatur: float, waechter: grenzen.Waechter) -> tuple[str, str]:
        """Streamt eine Antwort, meldet laufend, wie weit sie ist — und hält sie in Grenzen."""
        teile: list[str] = []
        zeichen = 0
        denken = 0
        grund = "stop"
        zuletzt = 0.0
        gezaehlt = False
        ende_gesehen = False
        ausgabe_vorher = self.verbrauch["completion_tokens"]
        provider_ausgabe_vorher = int(self.verbrauch.get("provider_output_usage_calls", 0))
        beginn = time.monotonic()
        strom = self.zugang.strom(self.modell, nachrichten, temperatur=temperatur, verbrauch=self.verbrauch)
        iterator = strom.__aiter__()

        async def grenzen_pruefen(jetzt: float) -> None:
            """Prüft nach *jedem* Stück, nicht nur beim UI-Takt.

            Der frühere 1,2-Sekunden-Takt war nur für die Oberfläche gedacht.
            Ein großer einzelner Chunk konnte deshalb fertig sein, bevor sein
            Output- oder Blocklimit überhaupt geprüft wurde.
            """
            signal = waechter.pruefen("".join(teile), jetzt - beginn, denken)
            while signal is not None:
                await self.signal(signal)
                if signal.stufe == "hart":
                    self.ausgabe_zeichen += zeichen
                    self.gruende.append("waechter")
                    raise Grenzfall(
                        f"{signal.text} Die Generierung wurde kontrolliert beendet; "
                        "der unvollständige Stand wurde nicht übernommen.",
                        signal.technik, art="ausufernd")
                signal = waechter.pruefen("".join(teile), jetzt - beginn, denken)

        naechstes: asyncio.Task[Any] | None = None
        try:
            while True:
                self.pruefe_abbruch()
                if naechstes is None:
                    naechstes = asyncio.create_task(iterator.__anext__())
                vergangen = time.monotonic() - beginn
                # Ein Soft-Limit soll warnen, ohne den noch laufenden
                # Generator zu canceln.  Daher wird der nächste Chunk als Task
                # abgewartet; ein Timeout prüft nur den Wächter und lässt den
                # Stream weiterlaufen.
                zeitpunkte = [STILLSTAND_SEKUNDEN, waechter.hart_sekunden]
                if "dauer:weich" not in waechter.gemeldet:
                    zeitpunkte.append(waechter.weich_sekunden)
                naechster = min((punkt for punkt in zeitpunkte if punkt > vergangen), default=0.01)
                try:
                    fertig, _ = await asyncio.wait({naechstes}, timeout=max(0.01, naechster))
                except asyncio.CancelledError:
                    raise
                if not fertig:
                    jetzt = time.monotonic()
                    await grenzen_pruefen(jetzt)
                    if jetzt - beginn >= STILLSTAND_SEKUNDEN:
                        raise Umsetzungsfehler(
                            "Das Modell hat mehrere Minuten lang nichts geliefert und wurde gestoppt.",
                            f"Kein Token seit {STILLSTAND_SEKUNDEN} s",
                        )
                    continue
                try:
                    stueck = naechstes.result()
                except StopAsyncIteration:
                    break
                finally:
                    naechstes = None
                if "text" in stueck:
                    teile.append(stueck["text"])
                    zeichen += len(stueck["text"])
                elif "denken" in stueck:
                    denken += int(stueck["denken"] or 0)
                elif "ende" in stueck:
                    grund = str(stueck["ende"] or "stop")
                    ende_gesehen = True
                    # Ein `done` bedeutet nicht automatisch, dass der Provider
                    # Tokenwerte geliefert hat. `eval_count=0` ist echt (die
                    # zentrale Schicht zählt ihn als Provider-Call); ein
                    # fehlendes `eval_count` bleibt dagegen Schätzung.
                    gezaehlt = (
                        int(self.verbrauch.get("provider_output_usage_calls", 0)) > provider_ausgabe_vorher
                        or self.verbrauch["completion_tokens"] > ausgabe_vorher
                    )
                jetzt = time.monotonic()
                if self._strombeginn is None and (zeichen or denken):
                    self._strombeginn = jetzt
                self.offene_zeichen = 0 if gezaehlt else zeichen + denken
                await grenzen_pruefen(jetzt)
                if jetzt - zuletzt > 1.2:
                    zuletzt = jetzt
                    text = f"{fortschritt} · {zahl(zeichen)} Zeichen" if zeichen else (
                        "Das Modell denkt nach …" if denken else f"{fortschritt} …")
                    await self.melde("fortschritt", text=text, zeichen=zeichen, sekunden=round(jetzt - beginn),
                                     **self.tokenwerte(zeichen=0 if gezaehlt else zeichen + denken,
                                                       seit=jetzt - self._strombeginn if self._strombeginn is not None else 0,
                                                       laufend=True))
        finally:
            # Fehlende Provider-Usage ist nie ein echter Nullwert: ein sauber
            # beendeter Stream wird als normale Schätzung behalten, Wächter /
            # Abbruch dagegen ausdrücklich als unvollständig markiert.
            if not gezaehlt and (zeichen or denken):
                if ende_gesehen:
                    self.abgeschlossen_geschaetzte_zeichen += zeichen + denken
                else:
                    self.abgebrochen_zeichen += zeichen + denken
            self.offene_zeichen = 0
            # Der Strom wird immer geschlossen — auch bei Abbruch und harter
            # Grenze. Damit endet die Generierung bei der Modellschicht.
            if naechstes is not None and not naechstes.done():
                naechstes.cancel()
                try:
                    await naechstes
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
                except Exception:  # noqa: BLE001 – der Strom wird gleich geschlossen
                    pass
            schliessen = getattr(iterator, "aclose", None)
            if schliessen is not None:
                try:
                    await schliessen()
                except Exception:  # noqa: BLE001 – schon geschlossen
                    pass
        self.ausgabe_zeichen += zeichen
        self.gruende.append(grund)
        if grenzen.ist_abgeschnitten(grund):
            await self.signal(grenzen.Signal(
                "abgeschnitten", "hart", grenzen.LIMIT_TEXT,
                f"Ende: {grund} nach {zahl(zeichen)} Zeichen in {time.monotonic() - beginn:.0f} s"))
        await self.technik(f"Modellantwort: {zahl(zeichen)} Zeichen in {time.monotonic() - beginn:.0f} s "
                           f"(Ende: {grund}).")
        return "".join(teile), grund

    def _abgeschnittene_stufe_verwerfen(self, text: str, grund: str) -> None:
        """Verwirft jede abgeschnittene Ausgabe innerhalb einer Stufe.

        Auch eine Fortsetzung kann zufällig mit einem schließenden HTML-Tag
        enden. Der `finish_reason` des Providers ist hier verbindlich: In
        einem gestuften Lauf darf daraus nie ein Kandidat werden.
        """
        bloecke = aenderungsbloecke(text)
        self.patch = Patchbericht(status="abgeschnitten", bloecke=len(bloecke), grund=grund)
        raise Grenzfall(
            grenzen.LIMIT_TEXT,
            f"TRUNCATED_STAGE: Antwort endete mit „{grund}“ nach {zahl(len(text))} Zeichen; "
            "der Stage-Kandidat wurde nicht angewendet.",
            art="abgeschnitten")

    async def vervollstaendigen(self, nachrichten: list[dict[str, Any]], text: str, basis: int = 0, *,
                                gestuft: bool = False, grund: str = "") -> Auszug:
        """Holt abgeschnittene Dateien nach, statt sie zu verwerfen.

        Nur für ganze Dateien: Eine Fortsetzung wird angehängt und danach im
        Browser geprüft. Bleibt die Datei trotz Fortsetzungen offen, ist sie
        unvollständig — kein Kandidat.
        """
        if gestuft and grenzen.ist_abgeschnitten(grund):
            self._abgeschnittene_stufe_verwerfen(text, grund)
        auszug = html_aus_antwort(text, self.produkt["titel"])
        for runde in range(MAX_FORTSETZUNGEN):
            if auszug.vollstaendig or not auszug.html:
                break
            await self.technik(f"Datei abgeschnitten — Fortsetzung {runde + 1}")
            weiter, weiter_grund = await self.generieren(
                [*nachrichten, {"role": "assistant", "content": text},
                 {"role": "user", "content": prompts.FORTSETZEN}],
                "Datei wird fortgesetzt", basis=basis,
            )
            if gestuft and grenzen.ist_abgeschnitten(weiter_grund):
                self._abgeschnittene_stufe_verwerfen(weiter, weiter_grund)
            text = weiter if _ANFANG.search(weiter[:300]) else fortsetzung_anfuegen(text, weiter)
            auszug = html_aus_antwort(text, self.produkt["titel"])
        return auszug

    def passt_ins_fenster(self, nachrichten: list[dict[str, Any]], ausgabe_zeichen: int) -> bool:
        eingabe = sum(len(str(n.get("content") or "")) for n in nachrichten)
        return (eingabe + ausgabe_zeichen) / ZEICHEN_JE_TOKEN + 600 <= self.zugang.fenster(self.modell)

    def mit_bildern(self, nachrichten: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not (self.sieht_bilder and self.eingabe.bilder):
            return nachrichten
        kopie = [dict(n) for n in nachrichten]
        kopie[-1]["images"] = [b["b64"] for b in self.eingabe.bilder if b.get("b64")][:4]
        return kopie

    # ------------------------------------------------------------ Phasen
    async def ausfuehren(self) -> None:
        schritte = list(SCHRITTE[self.art])
        # Neubau mit Daten aus dem Netz: eigener Schritt nach dem Verstehen.
        # Nur mit eingeschaltetem Web-Knopf — dann immer, ohne Schlagwort-Raten.
        katalog_noetig = self.art == "bauen" and self.eingabe.web
        if katalog_noetig:
            schritte.insert(1, ("recherche", "Daten aus dem Netz"))
        await self.melde("plan", schritte=[{"id": k, "text": t} for k, t in schritte], auftragsart=self.art)
        if self.eingabe.bilder:
            self.sieht_bilder = "vision" in await self.zugang.faehigkeiten(self.modell)
            if not self.sieht_bilder:
                await self.melde("hinweis", text=(
                    "Das gewählte Modell kann keine Bilder sehen. Die Bilder werden eingebunden, "
                    "aber nicht als Vorlage ausgewertet — dafür ein Modell mit Bildverständnis wählen."))
        vorher = self.produkt.get("version") or 0
        vorherige = speicher.version(self.produkt["id"], vorher) if vorher else None
        try:
            if self.art == "bauen":
                verstaendnis = await self.verstehen()
                if katalog_noetig:
                    await self.katalog_ausfuehren(verstaendnis)
                # Neubau: Der Abnahmevertrag entsteht aus dem schon vorhandenen
                # Verständnis — kein zusätzlicher Modellaufruf.
                self.vertrag = abnahme.vertrag_aus_verstaendnis(verstaendnis, self.eingabe.text)
                html, vollstaendig = await self.bauen(verstaendnis)
                erwartet = verstaendnis.get("bedienelemente") or []
                aenderungstext = self.eingabe.text
            elif self.art == "importieren":
                html, vollstaendig = await self.importieren()
                erwartet, aenderungstext = [], "Aus dem Chat übernommen"
            else:
                if not vorherige:
                    raise Umsetzungsfehler("Es gibt noch keine Version, die geändert werden könnte.")
                self.baseline = (vorherige.get("pruefung") or {}).get("gliederung") or {}
                if self.art == "aendern":
                    await self.aenderung_vorbereiten(vorher)
                    if self.eingabe.web:
                        await self.recherche_ausfuehren(vorherige["html"])
                html, vollstaendig = await self.aendern_mit_plan(self.recherche_html or vorherige["html"])
                erwartet = []
                if self.art == "aendern":
                    aenderungstext = self.linie["wunsch"] if self.linie else self.eingabe.text
                    if self.protokoll and self.protokoll.versuch > 1:
                        aenderungstext = f"{aenderungstext} (Versuch {self.protokoll.versuch})"
                else:
                    aenderungstext = "Fehler behoben: " + self.eingabe.fehler[:300]
            html, bericht = await self.pruefen_und_reparieren(html, vollstaendig, erwartet)
        except asyncio.CancelledError:
            await self.abbruch_vermerken()
            raise
        except Beendet as ende:
            await self.beenden_ohne_version(ende.text, vorher)
            return
        except Umsetzungsfehler as fehler:
            if await self.retten(fehler.text, vorherige):
                return
            await self.scheitern(fehler.text, fehler.technik, vorher, ergebnis=bool(vorherige))
            return
        except RuntimeError as fehler:
            # Meldungen der Modellschicht sind bereits verständlich formuliert
            # (Nutzungslimit, Anmeldung, nicht erreichbar).
            if await self.retten(str(fehler), vorherige):
                return
            await self.scheitern(str(fehler), "", vorher)
            return
        await self.abschliessen(html, bericht, aenderungstext, vorherige)

    async def retten(self, grund: str, vorherige: dict[str, Any] | None) -> bool:
        """Ergebnisgarantie: Bricht eine gestufte Änderung später ab (Modelldienst,
        Grenzen), wird der letzte fehlerfreie Zwischenstand trotzdem Ergebnis."""
        if (self.art != "aendern" or not self.zwischenstand or not vorherige
                or self.zwischenstand == vorherige.get("html")):
            return False
        await self.melde("hinweis", text="Der Rest der Änderung ließ sich nicht mehr umsetzen — JOSHI liefert den "
                                         "letzten fehlerfreien Zwischenstand und sagt dir, was offen ist.")
        self.offene_stufen.append(("Rest der Änderung", grund[:200]))
        self.aktive_stufe = None
        try:
            html, bericht = await self.pruefen_und_reparieren(self.zwischenstand, True, [], max_reparaturen=0)
        except Exception as fehler:  # noqa: BLE001 – dann bleibt es beim ehrlichen Scheitern
            await self.technik(f"Zwischenstand nicht prüfbar: {fehler}")
            return False
        if not tragfaehig(bericht):
            return False
        text = (self.linie or {}).get("wunsch") or self.eingabe.text
        await self.abschliessen(html, bericht, f"{text} (Zwischenstand)", vorherige)
        return True

    async def abnahmevertrag(self, wunsch: str, melden: bool = True) -> dict[str, Any]:
        """Aus dem Änderungswunsch werden prüfbare Kriterien."""
        bestand = ", ".join([
            *[f"Knopf „{k}“" for k in (self.baseline.get("knoepfe") or [])[:8]],
            *[f"Feld „{f.get('label')}“" for f in (self.baseline.get("felder") or [])[:8] if f.get("label")],
        ])
        vertrag = await self.gemessen(abnahme.vertrag_erzeugen(self.zugang, self.modell, wunsch=wunsch,
                                                               bestand=bestand, verbrauch=self.verbrauch))
        try:
            vertrag, korrigiert = await self.gemessen(abnahme.vertrag_gegenpruefen(
                self.zugang, self.modell, wunsch=wunsch, vertrag=vertrag, verbrauch=self.verbrauch))
        except Exception as fehler:  # noqa: BLE001 – Absicherung, darf den Auftrag nie stoppen
            await self.technik(f"Gegenprobe übersprungen: {fehler}")
            korrigiert = []
        if korrigiert:
            await self.technik("Gegenprobe Fehlerbericht: " + "; ".join(korrigiert))
        kriterien = vertrag.get("kriterien") or []
        if kriterien and melden:
            await self.technik("Abnahmekriterien: " + "; ".join(k["beschreibung"] for k in kriterien))
            await self.melde("abnahmevertrag", vertrag=vertrag)
        return vertrag

    # ----------------------------------------------------- Änderungslinie
    def _altbestand(self) -> dict[str, Any] | None:
        """Frühere Aufträge ohne Änderungslinie (vor dem 21.09.2026) nachbilden.

        Nur für eine Wiederholungsbitte: Der Wunsch des letzten gescheiterten
        Änderungsauftrags wird zum Root-Wunsch, spätere Zusätze zu Ergänzungen.
        """
        if speicher.aenderungen(self.produkt["id"]):
            return None
        jobs = speicher.jobs_des_produkts(self.user_id, self.produkt["id"])
        kette: list[dict[str, Any]] = []
        for job in reversed(jobs):
            if job["id"] == self.auftrag.job_id:
                continue
            if job["art"] == "aendern" and job["status"] == "failed":
                kette.append(job)
                continue
            break
        kette.reverse()
        texte = [(job, str((job.get("eingabe") or {}).get("text") or "")) for job in kette]

        def traegt_inhalt(text: str) -> bool:
            absicht = aenderung.absicht_erkennen(text, offen=True)
            return bool(text) and (absicht.art != "wiederholen" or bool(absicht.rest))

        inhalt = [(job, text) for job, text in texte if traegt_inhalt(text)]
        if not inhalt:
            return None
        root = inhalt[0][1]
        linie = speicher.aenderung_anlegen(self.user_id, self.produkt["id"], root, {},
                                           basis=int(self.produkt.get("version") or 0))
        versuche = []
        for nummer, (job, _) in enumerate(texte, 1):
            abgeschnitten = any("(Ende: length)" in str(e.get("text", "")) for e in job.get("ereignisse") or [])
            versuche.append({
                "versuch": nummer, "job": job["id"], "text": str((job.get("eingabe") or {}).get("text") or "")[:300],
                "ergebnis": "abgelehnt", "ergebnis_text": (job.get("fehler") or "")[:200],
                "signale": [{"art": "abgeschnitten", "stufe": "hart", "text": grenzen.LIMIT_TEXT,
                             "technik": "aus dem früheren Auftrag"}] if abgeschnitten else [],
            })
        ergaenzungen = [{"text": text, "job": job["id"]} for job, text in inhalt[1:]]
        return speicher.aenderung_aendern(linie["id"], versuche=versuche, ergaenzungen=ergaenzungen)

    async def aenderung_vorbereiten(self, aktive: int) -> None:
        """Ordnet den Satz des Nutzers seinem Änderungsauftrag zu.

        Ein erneuter Versuch behält Root-Wunsch und Root-Vertrag, eine
        Ergänzung erweitert beides, und nur etwas wirklich Neues beginnt einen
        neuen Auftrag.
        """
        offen = await asyncio.to_thread(speicher.offene_aenderung, self.produkt["id"])
        if offen is not None:
            offen = await self._linie_bereinigen(offen)
        absicht = aenderung.absicht_erkennen(self.eingabe.text, offen is not None, *_vertrag_und_plan(offen))
        if offen is None and aenderung.absicht_erkennen(self.eingabe.text, True).art == "wiederholen":
            offen = await asyncio.to_thread(self._altbestand)
            if offen is not None:
                absicht = aenderung.absicht_erkennen(self.eingabe.text, True, *_vertrag_und_plan(offen))
        # Ein exakt erneut gesendeter Root-Wunsch ist ein weiterer Versuch,
        # keine Ergänzung.  Sonst würde der Acceptance Contract bei einem
        # Retry still verdoppelt.
        if offen is not None and aenderung.ist_identischer_wunsch(self.eingabe.text, offen):
            absicht = aenderung.Absicht("wiederholen", "")
        if absicht.art == "verwerfen":
            if offen is not None:
                await asyncio.to_thread(speicher.aenderung_aendern, offen["id"], status="verworfen")
                await self.technik(f"Änderungsauftrag verworfen: {offen['wunsch'][:200]}")
            offen = None
            if not absicht.rest:
                raise Beendet("Der offene Änderungsauftrag ist verworfen. Deine aktive Version bleibt unverändert.")
            absicht = aenderung.Absicht("neu", absicht.rest)
        if absicht.art == "wiederholen" and offen is None:
            raise Umsetzungsfehler("Es gibt keinen offenen Auftrag, den JOSHI erneut versuchen könnte. "
                                   "Beschreibe, was sich ändern soll.")

        if offen is None:
            vertrag = aenderung.vertrag_einfrieren(await self.abnahmevertrag(absicht.rest or self.eingabe.text,
                                                                             melden=False))
            linie = await asyncio.to_thread(speicher.aenderung_anlegen, self.user_id, self.produkt["id"],
                                            absicht.rest or self.eingabe.text, vertrag, aktive)
        else:
            linie = offen
            vertrag = linie.get("vertrag") or {}
            if not vertrag.get("kriterien"):
                # Nachgebildete Linie ohne Vertrag: einmal aus dem Root-Wunsch erzeugen.
                vertrag = aenderung.vertrag_einfrieren(await self.abnahmevertrag(
                    aenderung.gesamtwunsch(linie), melden=False))
            if absicht.art in {"zurueckstellen", "wiederaufnehmen"}:
                # Kein neues Kriterium: Die gemeinten behalten ID und Wortlaut und
                # zählen bis auf Weiteres nicht (oder wieder).
                vertrag = (aenderung.zurueckstellen(vertrag, absicht.ziele, self.eingabe.text)
                           if absicht.art == "zurueckstellen" else aenderung.wiederaufnehmen(vertrag, absicht.ziele))
                ergaenzungen = [*(linie.get("ergaenzungen") or []), {
                    "text": self.eingabe.text, "job": self.auftrag.job_id, "art": absicht.art, "ids": absicht.ziele}]
                linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], ergaenzungen=ergaenzungen,
                                                vertrag=vertrag, status="open")
                await self.zurueckstellen_melden(absicht.art, absicht.ziele, vertrag)
                absicht = aenderung.Absicht("ergaenzen" if absicht.rest else "wiederholen", absicht.rest)
            if "workspace" in absicht.steuerung:
                ergaenzungen = [*(linie.get("ergaenzungen") or []), {
                    "text": self.eingabe.text, "job": self.auftrag.job_id, "art": "steuerung",
                    "steuerung": sorted(absicht.steuerung)}]
                linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], ergaenzungen=ergaenzungen)
            if absicht.rest:
                zusatz = await self.abnahmevertrag(absicht.rest, melden=False)
                ergaenzungen = [*(linie.get("ergaenzungen") or []), {"text": absicht.rest, "job": self.auftrag.job_id,
                                                                     "ueberholt_geprueft": True}]
                ueberholt = await self.gemessen(aenderung.ueberholte_kriterien(
                    self.zugang, self.modell, vertrag, absicht.rest, self.verbrauch))
                if ueberholt:
                    vertrag = aenderung.ueberholt_markieren(vertrag, ueberholt, absicht.rest)
                    await self.melde("hinweis", text="Durch deinen neuen Wunsch überholt und entfallen: " + "; ".join(
                        k["beschreibung"] for k in vertrag["kriterien"] if k["id"] in ueberholt))
                vertrag = aenderung.vertrag_ergaenzen(vertrag, zusatz, len(ergaenzungen))
                plan = linie.get("plan") or {}
                neue_ids = [k["id"] for k in vertrag["kriterien"] if k.get("herkunft") == f"ergaenzung_{len(ergaenzungen)}"]
                if plan.get("stufen") and neue_ids:
                    plan = {**plan, "stufen": [*plan["stufen"], {"titel": "Ergänzung", "auftrag": absicht.rest[:1200],
                                                                  "kriterien": neue_ids}]}
                linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], ergaenzungen=ergaenzungen,
                                                plan=plan, vertrag=vertrag, status="open")
            else:
                linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], vertrag=vertrag,
                                                status="open")
        self.linie = linie
        self.projekt_erzwingen = "workspace" in absicht.steuerung or any(
            isinstance(z, dict) and "workspace" in (z.get("steuerung") or []) for z in linie.get("ergaenzungen") or [])
        if self.projekt_erzwingen:
            await self.technik("Anweisung erkannt: JOSHI arbeitet in Projektdateien (Workspace) — keine neue Anforderung")
        self.vertrag_gesamt = vertrag
        self.vertrag = aenderung.aktiver_vertrag(vertrag)
        if self.vertrag_gesamt.get("kriterien") and not self.vertrag.get("kriterien"):
            raise Beendet("Alle offenen Punkte dieses Auftrags sind zurückgestellt. Deine aktive Version bleibt "
                          "unverändert. Schreib zum Beispiel „nimm die Info-Knöpfe wieder auf“, wenn sie drankommen sollen.")
        vertrag = self.vertrag
        zurueck = aenderung.zurueckgestellt(self.vertrag_gesamt)
        versuch = len(linie.get("versuche") or []) + 1
        self.protokoll = aenderung.Versuchsprotokoll(versuch=versuch, job=self.auftrag.job_id,
                                                     text=self.eingabe.text[:300])
        await self.versuch_speichern()
        wunsch = aenderung.gesamtwunsch(linie)
        self.wunsch = prompts.wunsch_mit_vorbefunden(wunsch, aenderung.vorbefunde(linie), versuch)
        kriterien = vertrag.get("kriterien") or []
        pflicht = aenderung.pflichtkriterien(vertrag)
        await self.technik(
            f"Änderungsauftrag {linie['id'][:8]} · Versuch {versuch} · {absicht.art} · Root-Vertrag mit "
            f"{len(kriterien)} Kriterien ({len(pflicht)} Pflicht): "
            + "; ".join(f"{k['id']} [{k.get('nachweis', 'inhalt')}]" for k in kriterien)
            + (f" · zurückgestellt: {', '.join(k['id'] for k in zurueck)}" if zurueck else ""))
        await self.melde("abnahmevertrag", vertrag=self.vertrag_gesamt, aenderung=linie["id"], versuch=versuch)
        if versuch > 1:
            await self.melde("hinweis", text=(
                f"JOSHI versucht den ursprünglichen Auftrag erneut (Versuch {versuch}) — "
                + (f"mit {len(kriterien)} offenen Abnahmekriterien ({len(zurueck)} zurückgestellt)."
                   if zurueck else
                   f"mit allen {len(kriterien)} Abnahmekriterien"
                   + (f" und {len(linie.get('ergaenzungen') or [])} Ergänzung(en)." if linie.get("ergaenzungen") else "."))))
        try:
            job = await asyncio.to_thread(speicher.job, self.user_id, self.auftrag.job_id)
            await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id, eingabe={
                **((job or {}).get("eingabe") or {}), "aenderung": linie["id"], "versuch": versuch,
                "absicht": absicht.art})
        except Exception:  # noqa: BLE001 – nur Metadaten
            pass

    async def katalog_ausfuehren(self, verstaendnis: dict[str, Any]) -> None:
        """Neubau: aktuelle Produkte samt Preis und Leistung aus dem Netz, bevor das Modell baut."""
        await self.schritt("recherche", "aktiv", "JOSHI plant, welche Daten aus dem Netz nötig sind …")

        async def melden(text: str) -> None:
            await self.schritt("recherche", "aktiv", text[:160])
            if not text.startswith(("Aktuelle Produkte suchen", "Preise recherchieren ·", "Recherche ·")):
                await self.technik(f"Recherche: {text}")

        auftrag = f"{self.eingabe.text}\n\nFunktionen: " + "; ".join(verstaendnis.get("funktionen") or [])
        plan = await self.gemessen(recherche.recherche_planen(self.zugang, self.modell, auftrag, self.verbrauch))
        await self.technik(f"Rechercheplan: {plan['art']} · " + "; ".join(f"{th['name']} ({th['suche']})"
                                                                        for th in plan["themen"]))
        if plan["art"] != "produkte":
            await self.daten_einholen(plan, melden, ziel="material")
            return
        katalog, funde = await self.gemessen(recherche.katalog_erstellen(
            self.zugang, self.modell, auftrag, self.verbrauch, melden=melden))
        if not katalog:
            await self.schritt("recherche", "fertig", "Keine verlässlichen Produktdaten im Netz gefunden")
            await self.melde("hinweis", text="JOSHI hat im Netz keine verlässlichen aktuellen Produktdaten mit Preis "
                                             "gefunden. Die Anwendung entsteht ohne recherchierte Daten.")
            return
        self.recherche_funde = funde
        kategorien = sorted({p["kategorie"] for p in katalog})
        for p in katalog:
            await self.technik(f"Katalog {p['kategorie']}: {p['name']} · {p['preis']:.2f} € ({p['quelle']}) · "
                               f"Leistung {int(p['leistung']) or '–'} · {p['merkmale'][:80]} {p['url']}")
        try:
            ordner = projektdateien.ordner(database.DATA_DIR, self.produkt) / "recherche"
            ordner.mkdir(parents=True, exist_ok=True)
            (ordner / f"katalog-{time.strftime('%Y%m%d-%H%M')}.json").write_text(
                json.dumps({"stand": recherche.stand(), "katalog": katalog}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except (OSError, projektdateien.ProjektFehler):
            pass
        await self.schritt("recherche", "fertig", f"{len(katalog)} aktuelle Produkte in {len(kategorien)} Kategorien "
                                                  f"mit Preis aus dem Netz (Stand {recherche.stand()})")
        await self.melde("hinweis", text=(f"Aktuelle Produktdaten recherchiert: {len(katalog)} Produkte in "
                                          f"{', '.join(kategorien)} — mit Preis und Quelle. Die Anwendung wird "
                                          "mit genau diesen Daten gebaut."))
        self.eingabe.material = (recherche.katalog_text(katalog) + "\n\n" + (self.eingabe.material or "")).strip()

    async def daten_einholen(self, plan: dict[str, Any], melden: Any, *, ziel: str) -> None:
        """Allgemeine Recherche: Einträge mit Feldern und Quelle — in den Bau- oder Änderungsauftrag."""
        if plan["art"] == "keine" or not plan["themen"]:
            await self.schritt("recherche", "fertig", "Für diesen Auftrag sind keine Daten aus dem Netz nötig")
            return
        eintraege = await self.gemessen(recherche.daten_recherchieren(
            self.zugang, self.modell, plan, self.verbrauch, melden=melden))
        if not eintraege:
            await self.schritt("recherche", "fertig", "Keine verlässlichen Daten im Netz gefunden")
            await self.melde("hinweis", text="JOSHI hat im Netz keine verlässlichen Daten zu diesem Auftrag gefunden. "
                                             "Es geht ohne recherchierte Daten weiter.")
            return
        self.recherche_daten = eintraege
        for e in eintraege:
            await self.technik(f"Daten {e['thema']}: {e['name']} · "
                               + "; ".join(f"{k}: {v}" for k, v in e["werte"].items())[:200] + f" · {e['quelle']}")
        try:
            ordner = projektdateien.ordner(database.DATA_DIR, self.produkt) / "recherche"
            ordner.mkdir(parents=True, exist_ok=True)
            (ordner / f"daten-{time.strftime('%Y%m%d-%H%M')}.json").write_text(
                json.dumps({"stand": recherche.stand(), "eintraege": eintraege}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except (OSError, projektdateien.ProjektFehler):
            pass
        themen = list(dict.fromkeys(e["thema"] for e in eintraege))
        await self.schritt("recherche", "fertig", f"{len(eintraege)} Einträge zu {len(themen)} Themen aus dem Netz "
                                                  f"(Stand {recherche.stand()})")
        await self.melde("hinweis", text=(f"Daten recherchiert: {len(eintraege)} Einträge zu {', '.join(themen)} — "
                                          "mit Quelle. JOSHI baut sie in die Anwendung ein."))
        text = recherche.daten_text(eintraege)
        if ziel == "material":
            self.eingabe.material = (text + "\n\n" + (self.eingabe.material or "")).strip()
        else:
            self.wunsch = f"{self.wunsch or self.eingabe.text}\n\n{text}"

    async def recherche_ausfuehren(self, html: str) -> None:
        """Daten aus dem Netz, bevor das Modell eine Zeile schreibt — mit Quelle, nie geraten.

        „Preise aktualisieren“ tauscht die Preise vorhandener Produkte (Preisvergleiche); jeder andere
        Wunsch wird geplant und gezielt recherchiert (neue Einträge, Fakten, Termine …).
        """
        schritte = [("recherche", "Daten aus dem Netz"), *SCHRITTE[self.art]]
        await self.melde("plan", schritte=[{"id": k, "text": t} for k, t in schritte], auftragsart=self.art)
        wunsch = f"{self.eingabe.text}\n{(self.linie or {}).get('wunsch', '')}"
        if not recherche.bedarf(wunsch):
            await self.schritt("recherche", "aktiv", "JOSHI plant, welche Daten aus dem Netz nötig sind …")

            async def melden(text: str) -> None:
                await self.schritt("recherche", "aktiv", text[:160])
                if not text.startswith(("Recherche ·", "Preise recherchieren ·", "Aktuelle Produkte suchen")):
                    await self.technik(f"Recherche: {text}")

            bestand = " · ".join([*(self.baseline.get("ueberschriften") or [])[:12], *(self.baseline.get("knoepfe") or [])[:12]])
            plan = await self.gemessen(recherche.recherche_planen(self.zugang, self.modell, wunsch, self.verbrauch,
                                                                  bestand=bestand))
            await self.technik(f"Rechercheplan: {plan['art']} · " + "; ".join(f"{th['name']} ({th['suche']})"
                                                                            for th in plan["themen"]))
            if plan["art"] == "produkte":
                katalog, funde = await self.gemessen(recherche.katalog_erstellen(
                    self.zugang, self.modell, wunsch, self.verbrauch, melden=melden))
                if katalog:
                    self.recherche_funde = funde
                    await self.schritt("recherche", "fertig", f"{len(katalog)} aktuelle Produkte mit Preis aus dem Netz")
                    self.wunsch = f"{self.wunsch or self.eingabe.text}\n\n{recherche.katalog_text(katalog)}"
                else:
                    await self.schritt("recherche", "fertig", "Keine verlässlichen Produktdaten im Netz gefunden")
                return
            await self.daten_einholen(plan, melden, ziel="wunsch")
            return
        await self.schritt("recherche", "aktiv", "Produkte und Preise werden aus der Anwendung gelesen …")
        positionen = await self.gemessen(recherche.positionen_lesen(self.zugang, self.modell, html, self.verbrauch))
        if not positionen:
            await self.schritt("recherche", "fertig", "Keine Produkte mit Preis in der Anwendung gefunden")
            await self.melde("hinweis", text="JOSHI hat in der Anwendung keine Produkte mit Preis gefunden, die sich "
                                             "im Netz nachschlagen lassen — es geht ohne Recherche weiter.")
            return

        async def melden(fertig: int, gesamt: int, name: str) -> None:
            await self.schritt("recherche", "aktiv", f"Preise recherchieren · {fertig} von {gesamt} · {name}")

        funde = await recherche.recherchieren(positionen, melden=melden, seiten_laden=recherche.seiten_laden_standard)
        self.recherche_funde = funde
        gefunden = [f for f in funde if f.neu is not None]
        for fund in funde:
            await self.technik(f"Recherche {fund.name}: {fund.alt:.2f} € → "
                               + (f"{fund.neu:.2f} € ({fund.quelle}) {fund.url}" if fund.neu is not None
                                  else ("unsicher, bleibt" if fund.unsicher else "nicht gefunden, bleibt")))
        try:
            ordner = projektdateien.ordner(database.DATA_DIR, self.produkt) / "recherche"
            ordner.mkdir(parents=True, exist_ok=True)
            (ordner / f"preise-{time.strftime('%Y%m%d-%H%M')}.json").write_text(recherche.als_json(funde), encoding="utf-8")
        except (OSError, projektdateien.ProjektFehler):
            pass
        await self.schritt("recherche", "fertig",
                           f"{len(gefunden)} von {len(funde)} Preisen im Netz gefunden (Stand {recherche.stand()})")
        if not gefunden:
            await self.melde("hinweis", text="JOSHI hat für keines der Produkte einen verlässlichen Preis im Netz "
                                             "gefunden. Die Preise bleiben, wie sie sind.")
            return
        beispiele = "; ".join(f"{f.name} {recherche._euro(f.neu)} ({f.quelle})" for f in gefunden[:4])
        await self.melde("hinweis", text=(f"Preise recherchiert: {len(gefunden)} von {len(funde)} gefunden, u. a. "
                                          f"{beispiele}. Nicht Gefundenes bleibt unverändert."))
        neu_html, eingesetzt, _ = recherche.einsetzen(html, funde)
        if eingesetzt:
            self.recherche_html = neu_html
            await self.technik(f"Preise selbst eingesetzt: {len(eingesetzt)} von {len(gefunden)} direkt im Code "
                               "ersetzt — das Modell zeigt nur noch Stand und Quellen an.")
            self.wunsch = f"{self.wunsch or self.eingabe.text}\n\n{recherche.anzeige_auftrag(funde, eingesetzt)}"
        else:
            self.wunsch = f"{self.wunsch or self.eingabe.text}\n\n{recherche.auftrag_text(funde)}"

    def datenabgleich(self, html: str, bericht: pruefer.Pruefbericht) -> None:
        """Stehen die recherchierten Preise bzw. Daten wirklich in der neuen Version?"""
        self._daten_eintraege_abgleichen(html, bericht)
        gefunden = [f for f in self.recherche_funde if f.neu is not None]
        if not gefunden:
            return
        uebernommen, fehlend = recherche.abgleich(html, gefunden)
        bestanden = len(uebernommen) >= max(1, round(0.8 * len(gefunden)))
        ergebnis = {"id": "preise_recherchiert", "pflicht": True, "nachweis": "daten",
                    "beschreibung": f"Die {len(gefunden)} im Netz recherchierten Preise stehen in der Anwendung",
                    "status": "PASS" if bestanden else "FAIL",
                    "begruendung": f"{len(uebernommen)} von {len(gefunden)} übernommen"
                                   + (f"; fehlt: {', '.join(f.name + ' ' + recherche._euro(f.neu) for f in fehlend[:6])}"
                                      if fehlend else ""),
                    "beleg": "daten"}
        abnahme_dict = bericht.abnahme or {"ergebnisse": [], "zaehlung": {"PASS": 0, "FAIL": 0, "NOT_PROVEN": 0}}
        abnahme_dict.setdefault("ergebnisse", []).append(ergebnis)
        zaehlung = abnahme_dict.setdefault("zaehlung", {"PASS": 0, "FAIL": 0, "NOT_PROVEN": 0})
        zaehlung[ergebnis["status"]] = int(zaehlung.get(ergebnis["status"], 0)) + 1
        bericht.abnahme = abnahme_dict
        if not bestanden:
            bericht.befunde.append(pruefer.Befund(
                "abnahme", "Die recherchierten Preise sind noch nicht übernommen: "
                + "; ".join(f"{f.name} {recherche._euro(f.neu)}" for f in fehlend[:8]),
                ergebnis["begruendung"]))

    def _nur_geschmack(self, bericht: pruefer.Pruefbericht) -> list[str]:
        """IDs der offenen Kriterien, wenn ALLE offenen reine Gestaltungsurteile ohne Messregel sind."""
        ergebnisse = (bericht.abnahme or {}).get("ergebnisse") or []
        offen = [e for e in ergebnisse if e.get("pflicht") and e.get("status") in {"FAIL", "NOT_PROVEN"}]
        if not offen:
            return []
        arten = {k["id"]: k for k in self.vertrag.get("kriterien") or []}
        for e in offen:
            kriterium = arten.get(e.get("id"), {})
            if kriterium.get("nachweis") != "gestaltung" or str(e.get("beleg") or "") in {"stil", "mobil"}:
                return []
            # Messbare Gestaltung (Farben, Glas, Schatten, Handybreite) bleibt verbindlich.
            if abnahme._gestaltung_pruefen(kriterium, {"gestaltung": {"farben": {}, "glas": 0, "transparent": 0,
                                                                     "schatten": 0}}) \
                    or abnahme.ist_mobil(kriterium):
                return []
        return [str(e.get("id")) for e in offen]

    def _daten_eintraege_abgleichen(self, html: str, bericht: pruefer.Pruefbericht) -> None:
        if not self.recherche_daten:
            return
        drin, fehlend = recherche.daten_abgleich(html, self.recherche_daten)
        bestanden = len(drin) * 10 >= len(self.recherche_daten) * 7
        ergebnis = {"id": "daten_recherchiert", "pflicht": True, "nachweis": "daten",
                    "beschreibung": f"Die {len(self.recherche_daten)} im Netz recherchierten Einträge stehen in der Anwendung",
                    "status": "PASS" if bestanden else "FAIL", "beleg": "daten",
                    "begruendung": f"{len(drin)} von {len(self.recherche_daten)} übernommen"
                                   + (f"; fehlt: {', '.join(e['name'] for e in fehlend[:6])}" if fehlend else "")}
        abnahme_dict = bericht.abnahme or {"ergebnisse": [], "zaehlung": {"PASS": 0, "FAIL": 0, "NOT_PROVEN": 0}}
        abnahme_dict.setdefault("ergebnisse", []).append(ergebnis)
        zaehlung = abnahme_dict.setdefault("zaehlung", {"PASS": 0, "FAIL": 0, "NOT_PROVEN": 0})
        zaehlung[ergebnis["status"]] = int(zaehlung.get(ergebnis["status"], 0)) + 1
        bericht.abnahme = abnahme_dict
        if not bestanden:
            bericht.befunde.append(pruefer.Befund(
                "abnahme", "Die recherchierten Daten sind noch nicht übernommen: "
                + "; ".join(e["name"] for e in fehlend[:8]), ergebnis["begruendung"]))

    async def _linie_bereinigen(self, linie: dict[str, Any]) -> dict[str, Any]:
        """Ein früher als Ergänzung verbuchtes Zurückstellen wird nachträglich richtig verbucht."""
        linie = await self._ueberholte_nachpruefen(linie)
        linie = await self._fehlerbericht_nachpruefen(linie)
        vertrag, korrekturen = aenderung.vertrag_bereinigen(linie)
        if not korrekturen:
            return linie
        linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], vertrag=vertrag,
                                        ergaenzungen=linie.get("ergaenzungen") or [])
        await self.technik("Änderungslinie bereinigt: " + " | ".join(korrekturen))
        zurueck = [k["id"] for k in aenderung.zurueckgestellt(vertrag)]
        if zurueck:
            await self.zurueckstellen_melden("zurueckstellen", zurueck, vertrag, nachtraeglich=True)
        entfallen = [k["beschreibung"] for k in vertrag.get("kriterien") or [] if k.get("entfallen")]
        if entfallen and any("Anweisung an JOSHI" in k for k in korrekturen):
            await self.melde("hinweis", text=("Deine Nachricht „…nutzt den Workspace“ war eine Anweisung an JOSHI, "
                                              "keine Anforderung an die Anwendung. Entfallen: " + "; ".join(entfallen)))
        return linie

    async def _fehlerbericht_nachpruefen(self, linie: dict[str, Any]) -> dict[str, Any]:
        """Ältere Linien: einmal prüfen, ob ein Fehlerbericht falsch herum verstanden wurde.

        Wurde etwas korrigiert, passen Schrittplan und Checkpoint nicht mehr —
        sie bauten auf dem verdrehten Ziel auf und werden verworfen.
        """
        vertrag = linie.get("vertrag") or {}
        if vertrag.get("gegengeprueft") or not vertrag.get("kriterien"):
            return linie
        try:
            vertrag, korrigiert = await self.gemessen(abnahme.vertrag_gegenpruefen(
                self.zugang, self.modell, wunsch=aenderung.gesamtwunsch(linie), vertrag=vertrag,
                verbrauch=self.verbrauch))
        except Exception as fehler:  # noqa: BLE001 – Absicherung, darf den Auftrag nie stoppen
            await self.technik(f"Gegenprobe übersprungen: {fehler}")
            return linie
        aenderungen: dict[str, Any] = {"vertrag": vertrag}
        if korrigiert:
            aenderungen.update(plan={}, checkpoint="", checkpoint_stufe=0)
            await self.technik("Gegenprobe Fehlerbericht (bestehender Auftrag): " + "; ".join(korrigiert))
            await self.melde("hinweis", text=(
                "JOSHI hatte deinen Fehlerbericht falsch herum verstanden und korrigiert das Ziel: "
                + "; ".join(korrigiert[:3]) + ". Die Schritte werden dafür neu geplant."))
        return await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], **aenderungen)

    async def _ueberholte_nachpruefen(self, linie: dict[str, Any]) -> dict[str, Any]:
        """Ältere Linien: Hat eine spätere Ergänzung frühere Kriterien überholt? Einmal je Ergänzung."""
        ergaenzungen = linie.get("ergaenzungen") or []
        offen = [(n, z) for n, z in enumerate(ergaenzungen, 1)
                 if isinstance(z, dict) and not z.get("ueberholt_geprueft") and not z.get("art")]
        if not offen:
            return linie
        vertrag = linie.get("vertrag") or {}
        entfallen: list[str] = []
        for nummer, zusatz in offen:
            eigene = {k["id"] for k in vertrag.get("kriterien") or [] if k.get("herkunft") == f"ergaenzung_{nummer}"}
            spaeter = {k["id"] for k in vertrag.get("kriterien") or []
                       if str(k.get("herkunft", "")).startswith("ergaenzung_")
                       and int(str(k["herkunft"]).split("_")[1] or 0) > nummer}
            ids = await self.gemessen(aenderung.ueberholte_kriterien(
                self.zugang, self.modell, vertrag, str(zusatz.get("text") or ""), self.verbrauch,
                schuetzen=eigene | spaeter))
            if ids:
                vertrag = aenderung.ueberholt_markieren(vertrag, ids, str(zusatz.get("text") or ""))
                entfallen += ids
            zusatz["ueberholt_geprueft"] = True
        linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], vertrag=vertrag, ergaenzungen=ergaenzungen)
        if entfallen:
            await self.technik("Überholte Kriterien entfallen: " + ", ".join(entfallen))
            await self.melde("hinweis", text="Durch spätere Wünsche überholt und entfallen: " + "; ".join(
                k["beschreibung"] for k in vertrag.get("kriterien") or [] if k["id"] in entfallen))
        return linie

    async def zurueckstellen_melden(self, art: str, ids: list[str], vertrag: dict[str, Any], *,
                                    nachtraeglich: bool = False) -> None:
        namen = {k["id"]: k["beschreibung"] for k in vertrag.get("kriterien") or []}
        liste = "; ".join(namen.get(i, i) for i in ids)
        if art == "wiederaufnehmen":
            await self.melde("hinweis", text=f"Wieder aufgenommen: {liste}")
            return
        await self.melde("hinweis", text=(
            ("Deine Nachricht von vorhin war ein Zurückstellen, keine neue Anforderung. " if nachtraeglich else "")
            + f"Zurückgestellt: {liste}. Diese Punkte zählen jetzt nicht — was davon schon da ist, bleibt. "
            "Schreib „nimm … wieder auf“, wenn sie drankommen sollen."))

    async def versuch_speichern(self) -> None:
        if not (self.linie and self.protokoll):
            return
        linie = await asyncio.to_thread(speicher.aenderung, self.linie["id"])
        if not linie:
            return
        versuche = [v for v in linie.get("versuche") or [] if v.get("job") != self.protokoll.job]
        versuche.append(self.protokoll.als_dict())
        self.linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], versuche=versuche)

    def gestuft_beginnen(self, basis: int = 0) -> bool:
        """Pre-Flight: Braucht diese Änderung geprüfte Schritte — vor dem ersten großen Aufruf?"""
        if self.art != "aendern" or not self.linie:
            return False
        if aenderung.war_zu_gross(self.linie):
            self.komplex = {"gestuft": True, "gruende": ["ein früherer Versuch war für einen Schritt zu groß"],
                            "quelle": "vorversuch"}
            return True
        komplex = aenderung.komplexitaet(self.vertrag, basis=basis, grenzen=self.grenzen)
        self.komplex = {**komplex.als_dict(), "quelle": "vertrag"}
        return komplex.gestuft

    async def aendern_mit_plan(self, html: str) -> tuple[str, bool]:
        """Schneller Einmal-Weg — oder direkt geprüfte Schritte, wenn der Vertrag es verlangt.

        Gefunden im Killer-Retest am 21.09.2026: Bei 10 Pflichtkriterien mit
        Leistung, Mehrbenutzer und Formel-Engine lief erst 901 Sekunden lang
        ein Einmal-Versuch, bevor JOSHI in Schritte wechselte. Jetzt fällt die
        Entscheidung vor dem ersten großen Aufruf.
        """
        if self.gestuft_beginnen(len(html)):
            await self.technik("Direkt gestuft (" + self.komplex.get("quelle", "") + "): "
                               + "; ".join(self.komplex.get("gruende") or []))
            await self.melde("hinweis", text=(
                "Der letzte Versuch war für einen Schritt zu groß. JOSHI setzt die Änderung in geprüften Schritten um."
                if self.komplex.get("quelle") == "vorversuch" else
                "Diese Änderung betrifft mehrere Kernbereiche. JOSHI zerlegt sie direkt in geprüfte Schritte."))
            return await self.aendern_gestuft(html, direkt=True)
        try:
            return await self.aendern(html)
        except Grenzfall as fall:
            if self.art != "aendern" or not self.linie:
                raise
            await self.technik(f"Einmal-Änderung nicht übernommen ({fall.art}): {fall.technik}")
            return await self.aendern_gestuft(html)

    # --------------------------------------------------------- Neubau usw.
    async def verstehen(self) -> dict[str, Any]:
        await self.status("understanding")
        await self.schritt("verstehen", "aktiv", "JOSHI überlegt, was die Anwendung können muss …")
        bilder = prompts.bilder_text(self.eingabe.bilder, self.sieht_bilder)
        nachrichten = self.mit_bildern(prompts.verstehen_nachrichten(
            self.eingabe.text, self.eingabe.material, self.eingabe.chat, bilder))
        try:
            roh = await self.gemessen(self.zugang.strukturiert(
                self.modell, nachrichten, prompts.VERSTAENDNIS_SCHEMA,
                temperatur=0.2, verbrauch=self.verbrauch))
        except RuntimeError as fehler:
            if "Nutzungslimit" in str(fehler) or "Anmeldung" in str(fehler):
                raise
            await self.technik(f"Verstehen ohne Ergebnis: {fehler}")
            roh = {}
        verstaendnis = verstaendnis_normalisieren(roh, self.eingabe.text)
        gelesen = json_aus_antwort(roh)
        if not (isinstance(gelesen, dict) and gelesen.get("titel")):
            await self.technik("Verstehen ohne verwertbares Ergebnis — es geht mit dem Auftrag allein weiter.")
            verstaendnis["titel"] = self.produkt["titel"]
        aenderungen: dict[str, Any] = {"verstaendnis": verstaendnis}
        if self.produkt.get("quelle", {}).get("titel_auto", True):
            aenderungen["titel"] = verstaendnis["titel"]
            self.produkt["titel"] = verstaendnis["titel"]
        await asyncio.to_thread(speicher.produkt_aendern, self.user_id, self.produkt["id"], **aenderungen)
        funktionen = verstaendnis["funktionen"]
        await self.melde("verstaendnis", verstaendnis=verstaendnis, titel=self.produkt["titel"])
        await self.schritt("verstehen", "fertig",
                           f"{verstaendnis['titel']}: {len(funktionen)} Funktion{'en' if len(funktionen) != 1 else ''} geplant")
        return verstaendnis

    async def bauen(self, verstaendnis: dict[str, Any]) -> tuple[str, bool]:
        await self.status("building")
        await self.schritt("erstellen", "aktiv", "Die Anwendung entsteht …")
        bilder = prompts.bilder_text(self.eingabe.bilder, self.sieht_bilder)
        nachrichten = prompts.bauen_nachrichten(self.eingabe.text, verstaendnis, self.eingabe.material,
                                                self.eingabe.chat, bilder)
        if not self.passt_ins_fenster(nachrichten, 24000):
            await self.technik("Material gekürzt, damit Auftrag und Datei ins Kontextfenster passen.")
            budget = max(2000, int(self.zugang.fenster(self.modell) * ZEICHEN_JE_TOKEN) - 36000)
            nachrichten = prompts.bauen_nachrichten(self.eingabe.text, verstaendnis, self.eingabe.material[:budget // 2],
                                                    self.eingabe.chat[:budget // 2], bilder)
        nachrichten = self.mit_bildern(nachrichten)
        text, _ = await self.generieren(nachrichten, "Anwendung wird geschrieben")
        auszug = await self.vervollstaendigen(nachrichten, text)
        if not auszug.html:
            raise Umsetzungsfehler("Das Modell hat keine Anwendung geliefert.", text[:600])
        for hinweis in auszug.hinweise:
            await self.technik(hinweis)
        await self.schritt("erstellen", "fertig", f"{zahl(len(auszug.html))} Zeichen HTML, CSS und JavaScript")
        return auszug.html, auszug.vollstaendig

    async def importieren(self) -> tuple[str, bool]:
        await self.status("understanding")
        await self.schritt("verstehen", "aktiv", "HTML aus dem Chat wird übernommen …")
        auszug = html_aus_antwort(self.eingabe.html, self.produkt["titel"])
        if not auszug.html:
            raise Umsetzungsfehler("In der Chat-Nachricht steckt keine HTML-Anwendung.")
        titel = titel_aus_html(auszug.html) or self.produkt["titel"]
        verstaendnis = verstaendnis_normalisieren({"titel": titel, "zweck": "Aus dem Chat übernommen"}, titel)
        await asyncio.to_thread(speicher.produkt_aendern, self.user_id, self.produkt["id"],
                                titel=titel, verstaendnis=verstaendnis)
        self.produkt["titel"] = titel
        await self.melde("verstaendnis", verstaendnis=verstaendnis, titel=titel)
        await self.schritt("verstehen", "fertig", f"{zahl(len(auszug.html))} Zeichen übernommen")
        return auszug.html, auszug.vollstaendig

    def _nachrichten_fuer(self, html: str, wunsch: str, bilder: str = "") -> Any:
        zustand = self.produkt.get("zustand") or {}

        def nachrichten_fuer(vollstaendig: bool) -> list[dict[str, Any]]:
            return self.mit_bildern(prompts.aendern_nachrichten(
                html, wunsch, zustand=zustand, material=self.eingabe.material, bilder=bilder,
                vollstaendig=vollstaendig))
        return nachrichten_fuer

    async def aendern(self, html: str) -> tuple[str, bool]:
        await self.status("building")
        await self.schritt("erstellen", "aktiv", "Die Änderung wird eingearbeitet …")
        bilder = prompts.bilder_text(self.eingabe.bilder, self.sieht_bilder)
        if self.art == "reparieren":
            wunsch = ("Beim Benutzen der Anwendung trat dieser Fehler auf. Finde und behebe die Ursache, "
                      f"ohne Funktionen zu entfernen:\n{self.eingabe.fehler}")
            if self.eingabe.text:
                wunsch += f"\n\nHinweis des Nutzers: {self.eingabe.text}"
        else:
            wunsch = self.wunsch or self.eingabe.text
        neu, vollstaendig, wie = await self.umsetzen(html, self._nachrichten_fuer(html, wunsch, bilder),
                                                     "Änderung wird geschrieben", wunsch=wunsch)
        await self.schritt("erstellen", "fertig", wie)
        return neu, vollstaendig

    async def _projektdateien_umsetzen(self, html: str, wunsch: str, fortschritt: str, *,
                                       gestuft: bool) -> tuple[str, bool, str]:
        """Bearbeitet große Apps dateiweise; Browserprüfung bleibt beim Aufrufer."""
        fenster = self.zugang.fenster(self.modell)
        if fenster < 12_000:
            raise Umsetzungsfehler(
                f"Die Anwendung ist zu groß für das Kontextfenster dieses Modells ({zahl(fenster)} Tokens). "
                "Wähle ein Cloud-Modell oder stelle in der Ollama-App ein größeres Kontextfenster ein.",
                f"PROJECT_CONTEXT_TOO_SMALL: {len(html)} Zeichen HTML, {zahl(fenster)} Tokens Modellfenster.",
            )
        ziel = projektdateien.auftrag_ordner(database.DATA_DIR, self.produkt, self.auftrag.job_id)
        basis = await asyncio.to_thread(projektdateien.laden, ziel, html)
        if basis is None:
            basis = projektdateien.zerlegen(html)
        if not basis.dateien:
            raise Umsetzungsfehler(
                "Die große Anwendung ließ sich nicht sicher in bearbeitbare Projektdateien zerlegen. "
                "Die aktive Version bleibt unverändert.",
                f"PROJECT_SPLIT_UNAVAILABLE: {len(html)} Zeichen, keine sicheren CSS/JS-Schnittstellen.",
            )

        uebersicht = projektdateien.uebersicht(basis)
        reihe = projektdateien.rangfolge(basis, wunsch)
        fenster_zeichen = fenster * ZEICHEN_JE_TOKEN
        budget = max(0, int((fenster_zeichen - 9_000) / 2))
        material = self.eingabe.material[:min(12_000, max(1_200, int(fenster_zeichen * 0.15)))]
        gewaehlt: list[str] = []
        nachrichten: list[dict[str, Any]] = []
        ausgabe_reserve = 0
        while budget >= 1200:
            gewaehlt = projektdateien.auswahl_begrenzen(basis, reihe, budget)
            if not gewaehlt:
                break
            inhalte = {name: basis.alle()[name] for name in gewaehlt}
            nachrichten = prompts.projektdateien_nachrichten(
                uebersicht, inhalte, wunsch, zustand=self.produkt.get("zustand") or {},
                material=material,
                bilder=prompts.bilder_text(self.eingabe.bilder, self.sieht_bilder),
            )
            ausgabe_reserve = min(max(7_000, sum(map(len, inhalte.values())) + 1_500),
                                  max(7_000, int(fenster_zeichen * 0.42)))
            if self.passt_ins_fenster(nachrichten, ausgabe_reserve):
                break
            if material:
                material = material[:max(0, int(len(material) * 0.65))]
                if len(material) < 500:
                    material = ""
                continue
            budget = int(budget * 0.72)
        else:
            gewaehlt = []
        if not gewaehlt or not self.passt_ins_fenster(nachrichten, ausgabe_reserve):
            raise Umsetzungsfehler(
                f"Keine passende Projektdatei passt sicher in das Kontextfenster dieses Modells "
                f"({zahl(self.zugang.fenster(self.modell))} Tokens). Wähle ein Modell mit größerem Kontextfenster.",
                f"PROJECT_CONTEXT_TOO_SMALL: {len(html)} Zeichen Gesamtprojekt; Auswahlbudget {budget} Zeichen.",
            )

        basis_meta = {"produkt": self.produkt["id"], "auftrag": self.auftrag.job_id,
                      "basis_version": int(self.produkt.get("version") or 0), "status": "working"}
        await asyncio.to_thread(projektdateien.schreiben, ziel, basis, **basis_meta)
        await asyncio.to_thread(projektdateien.dokumentation_schreiben, ziel, projektdateien.beschreibung(
            self.produkt, basis, grund="große Anwendung", auftrag=wunsch,
            version=int(self.produkt.get("version") or 0),
            zurueckgestellt=[k.get("beschreibung", "") for k in aenderung.zurueckgestellt(self.vertrag_gesamt)]))
        self.projekt_grund = str(ziel)
        self.projekt_stand = basis
        if len(material) < len(self.eingabe.material):
            await self.technik(f"Anhangskontext begrenzt: {len(material):,} von "
                               f"{len(self.eingabe.material):,} Zeichen Modellkontext.".replace(",", "."))
        await self.technik(
            f"Projektdatei-Modus: {len(html):,} Zeichen in {len(basis.dateien) + 1} Dateien; "
            f"Modellkontext: {', '.join(gewaehlt)}; interner Auftragspfad {ziel}".replace(",", "."))

        text, grund = await self.generieren(self.mit_bildern(nachrichten), fortschritt,
                                            basis=len(html), bloecke=True)
        if grenzen.ist_abgeschnitten(grund):
            self.patch = Patchbericht(status="abgeschnitten", grund=grund)
            raise Grenzfall(grenzen.LIMIT_TEXT,
                            f"PROJECT_FILES_TRUNCATED: Antwort endete mit „{grund}“; "
                            "keine Projektdatei wurde übernommen.", art="abgeschnitten")

        antwort = projektdateien.anwenden(basis, text, gesehen=gewaehlt, aufgabe=wunsch)
        anzahl = len(antwort.geaendert) + len(antwort.neu)
        if (anzahl <= 0 or antwort.probleme) and not antwort.offen:
            # Einmal nachfragen statt aufgeben (29.09.2026: eine Reparatur kam als
            # 289 Zeichen Erklärung ohne Dateiabschnitt — JOSHI gab auf).
            hinweis = ("Deine Antwort enthielt keine verwendbaren Dateiabschnitte"
                       + (f" ({'; '.join(str(p) for p in antwort.probleme[:3])})" if antwort.probleme else "")
                       + ". Gib jetzt nur die geänderten Dateien aus, jede genau so:\n=== DATEI: pfad ===\n"
                         "(vollständiger Inhalt)\n=== ENDE ===\nKeine Erklärungen.")
            nachfrage = [*self.mit_bildern(nachrichten), {"role": "assistant", "content": text[:4000]},
                         {"role": "user", "content": hinweis}]
            await self.technik("Projektdateien: Antwort ohne verwendbare Dateien — JOSHI fragt einmal gezielt nach.")
            zweiter, grund2 = await self.generieren(nachfrage, "Projektdateien werden nachgefordert",
                                                    basis=len(html), bloecke=True)
            if not grenzen.ist_abgeschnitten(grund2):
                nochmal = projektdateien.anwenden(basis, zweiter, gesehen=gewaehlt, aufgabe=wunsch)
                if len(nochmal.geaendert) + len(nochmal.neu) > 0:
                    antwort, text, grund = nochmal, zweiter, grund2
                    anzahl = len(antwort.geaendert) + len(antwort.neu)
        if antwort.probleme:
            self.patch = Patchbericht(status="konflikt", konflikte=antwort.probleme, grund=grund)
            raise Grenzfall("Die Projektdatei-Antwort war nicht sicher anwendbar.",
                            "PROJECT_FILES_REJECTED: " + " | ".join(antwort.probleme[:5]), art="konflikt")
        if antwort.offen:
            # Höchstens ein gezielter Folgeaufruf. Bereits passende Änderungen
            # bleiben nur im temporären Kandidaten; bei weiterem Konflikt wird
            # der gesamte Kandidat verworfen.
            nachtrag = prompts.projektdateien_nachtrag(antwort.projekt.alle(), antwort.offen, wunsch)
            if self.passt_ins_fenster(nachtrag, 9_000):
                self.patch = Patchbericht(status="teilweise", bloecke=anzahl,
                                          konflikte=[pfad for pfad in antwort.offen], grund=grund, nachtrag=True)
                zweiter, grund2 = await self.generieren(nachtrag, "Projektdatei-Änderungen werden abgeglichen",
                                                        basis=len(html), bloecke=True)
                if not grenzen.ist_abgeschnitten(grund2):
                    nachher = projektdateien.anwenden(antwort.projekt, zweiter, gesehen=gewaehlt, aufgabe=wunsch)
                    if not nachher.probleme and not nachher.offen:
                        antwort = nachher
                        grund = grund2
                        anzahl = len(antwort.geaendert) + len(antwort.neu)
                    else:
                        antwort = nachher
            if antwort.offen:
                konflikte = [pfad for pfad in antwort.offen]
                self.patch = Patchbericht(status="konflikt", bloecke=anzahl, konflikte=konflikte, grund=grund,
                                          nachtrag=True)
                await self.signal(grenzen.Signal(
                    "konflikt", "hart", "Einige Projektdatei-Änderungen ließen sich nicht eindeutig zuordnen.",
                    "PROJECT_FILES_CONFLICT: " + ", ".join(konflikte[:6])))
                raise Grenzfall("Die Änderung ließ sich nicht vollständig einarbeiten. "
                                "Der Projektdatei-Kandidat wurde verworfen.",
                                "PROJECT_FILES_CONFLICT: " + ", ".join(konflikte[:6]), art="konflikt")
            if antwort.probleme:
                self.patch = Patchbericht(status="konflikt", konflikte=antwort.probleme, grund=grund, nachtrag=True)
                raise Grenzfall("Der Projektdatei-Nachtrag war nicht sicher anwendbar.",
                                "PROJECT_FILES_REJECTED: " + " | ".join(antwort.probleme[:5]), art="konflikt")

        if anzahl <= 0:
            self.patch = Patchbericht(status="konflikt", grund=grund)
            raise Grenzfall("Das Modell hat keine verwendbare Projektdatei-Änderung geliefert.",
                            "PROJECT_FILES_EMPTY: Es gab keinen gültigen Dateiabschnitt.", art="konflikt")
        try:
            neu = antwort.projekt.zusammensetzen()
        except projektdateien.ProjektFehler as fehler:
            self.patch = Patchbericht(status="konflikt", konflikte=[str(fehler)], grund=grund)
            raise Grenzfall("Die Projektdateien ergeben kein vollständiges HTML-Dokument.",
                            f"PROJECT_FILES_ASSEMBLY: {fehler}", art="konflikt") from fehler

        self.patch = Patchbericht(status="komplett", bloecke=anzahl, angewendet=anzahl, grund=grund)
        self.projekt_stand = antwort.projekt
        await asyncio.to_thread(projektdateien.schreiben, ziel, antwort.projekt,
                                **{**basis_meta, "status": "candidate", "gewaehlt": gewaehlt})
        await asyncio.to_thread(projektdateien.dokumentation_schreiben, ziel, projektdateien.beschreibung(
            self.produkt, antwort.projekt, grund="geprüfter Zwischenstand des Auftrags", auftrag=wunsch,
            version=int(self.produkt.get("version") or 0),
            zurueckgestellt=[k.get("beschreibung", "") for k in aenderung.zurueckgestellt(self.vertrag_gesamt)]))
        return neu, True, f"{anzahl} Projektdatei{'en' if anzahl != 1 else ''} geändert"

    async def umsetzen(self, html: str, nachrichten_fuer: Any, fortschritt: str, *,
                       wunsch: str = "", gestuft: bool = False) -> tuple[str, bool, str]:
        """Änderungsblöcke, bei kleinen Dateien oder Fehlschlag die ganze Datei.

        Rückgabe: (HTML, vollständig, Beschreibung für den Schritt). Eine
        abgeschnittene Antwort und ein Patch, dessen Änderungen nicht alle
        ankommen, enden als Grenzfall — nie als halbe Änderung.
        """
        if len(html) >= projektdateien.PROJEKT_AB or (self.projekt_erzwingen and len(html) >= 4000):
            return await self._projektdateien_umsetzen(html, wunsch or self.wunsch or self.eingabe.text,
                                                       fortschritt, gestuft=gestuft)
        ganz = len(html) < KLEINE_DATEI and self.passt_ins_fenster(nachrichten_fuer(True), len(html) + 4000)
        if not ganz and not self.passt_ins_fenster(nachrichten_fuer(False), 6000):
            fenster = self.zugang.fenster(self.modell)
            raise Umsetzungsfehler(
                f"Die Anwendung ist zu groß für das Kontextfenster dieses Modells ({zahl(fenster)} Tokens). "
                "Wähle ein Cloud-Modell oder stelle in der Ollama-App ein größeres Kontextfenster ein.",
                f"{zahl(len(html))} Zeichen HTML",
            )
        nachrichten = nachrichten_fuer(ganz)
        weich_vorher = sum(s.stufe == "weich" for s in self.signale)
        text, grund = await self.generieren(nachrichten, fortschritt, basis=len(html), bloecke=not ganz)
        # Ein Stage-Output mit `length` kann zufällig wie ein vollständiges
        # HTML aussehen.  Der Provider hat trotzdem explizit gesagt, dass der
        # Call unvollständig war; in Schritten wird so ein Kandidat nie
        # fortgesetzt oder angewendet, sondern gezielt erneut versucht.
        if gestuft and grenzen.ist_abgeschnitten(grund):
            self._abgeschnittene_stufe_verwerfen(text, grund)
        if _ANFANG.search(text):
            auszug = await self.vervollstaendigen(nachrichten, text, basis=len(html), gestuft=gestuft, grund=grund)
            if auszug.html and auszug.vollstaendig:
                self.patch = Patchbericht(status="neu_geschrieben", grund=grund)
                return auszug.html, True, "Datei neu geschrieben"
            if auszug.html:
                self.patch = Patchbericht(status="abgeschnitten", grund=grund)
                raise Grenzfall(grenzen.LIMIT_TEXT, "Die Datei endet auch nach Fortsetzungen ohne </html>.",
                                art="abgeschnitten")
        if grenzen.ist_abgeschnitten(grund):
            bloecke = aenderungsbloecke(text)
            self.patch = Patchbericht(status="abgeschnitten", bloecke=len(bloecke), grund=grund)
            raise Grenzfall(grenzen.LIMIT_TEXT,
                            f"TRUNCATED_PATCH: Antwort endete mit „{grund}“ nach {zahl(len(text))} Zeichen; "
                            f"{len(bloecke)} vollständige Änderungsblöcke wurden nicht angewendet.",
                            art="abgeschnitten")
        bloecke = aenderungsbloecke(text)
        if bloecke:
            neu, offen = bloecke_einzeln(html, bloecke)
            patch = Patchbericht(bloecke=len(bloecke), angewendet=len(bloecke) - len(offen),
                                 konflikte=[a.strip()[:300] for a, _ in offen], grund=grund)
            self.patch = patch
            beschreibung = f"{len(bloecke)} Stelle{'n' if len(bloecke) != 1 else ''} geändert"
            if not offen:
                return neu, True, beschreibung
            # PARTIAL_PATCH: genau ein gezielter Nachtrag — nur für die fehlenden
            # Blöcke und auf dem teilweise geänderten Stand, nie auf dem Original.
            patch.status = "teilweise"
            await self.technik(f"{len(offen)} von {len(bloecke)} Änderungsblöcken passten nicht — "
                               "gezielter Nachtrag nur für diese Blöcke.")
            nachtrag = prompts.nachtrag_nachrichten(neu, offen, wunsch or self.wunsch)
            if self.passt_ins_fenster(nachtrag, 8000):
                patch.nachtrag = True
                zweiter, grund2 = await self.generieren(nachtrag, "Änderung wird nachgetragen",
                                                        basis=len(neu), bloecke=True)
                if not grenzen.ist_abgeschnitten(grund2):
                    if _ANFANG.search(zweiter):
                        auszug = html_aus_antwort(zweiter, self.produkt["titel"])
                        if auszug.html and auszug.vollstaendig:
                            self.patch = Patchbericht(status="neu_geschrieben", bloecke=len(bloecke), grund=grund2)
                            return auszug.html, True, "Datei neu geschrieben"
                    nachgetragen, _ = bloecke_einzeln(neu, aenderungsbloecke(zweiter))
                    fehlend = [(a, n) for a, n in offen if not ersetzung_vorhanden(nachgetragen, n)]
                    if not fehlend:
                        patch.status, patch.angewendet, patch.konflikte = "komplett", len(bloecke), []
                        return nachgetragen, True, beschreibung + " (mit Nachtrag)"
                    patch.konflikte = [a.strip()[:300] for a, _ in fehlend]
            patch.status = "konflikt"
            await self.signal(grenzen.Signal(
                "konflikt", "hart", "Einige Änderungen ließen sich nicht eindeutig einarbeiten.",
                f"PATCH_CONFLICT: {len(patch.konflikte)} von {len(bloecke)} Blöcken kamen auch nach dem "
                "Nachtrag nicht an: " + " | ".join(k[:80] for k in patch.konflikte[:4])))
            # Die ganze Datei neu — aber nicht bei einer ohnehin übergroßen oder
            # gestuften Änderung: Das wäre genau der Monster-Aufruf, den die
            # Schritte vermeiden sollen.
            # Eine große Anwendung ganz neu schreiben zu lassen, ist selbst der
            # Monster-Aufruf (gemessen am 27.09.2026: 62.000 Zeichen, 625.000
            # Zeichen Denkstrom). Dann lieber geprüfte Schritte.
            zu_gross = sum(s.stufe == "weich" for s in self.signale) > weich_vorher \
                or len(bloecke) > self.grenzen.bloecke(len(html))[0] or len(html) > GROSSE_DATEI
            if gestuft or zu_gross:
                raise Grenzfall("Die Änderung ließ sich nicht vollständig einarbeiten. "
                                "Der unvollständige Stand wurde nicht übernommen.",
                                f"PATCH_CONFLICT: {len(patch.konflikte)} von {len(bloecke)} Blöcken nicht anwendbar.",
                                art="konflikt")
        elif ganz:
            auszug = html_aus_antwort(text, self.produkt["titel"])
            if auszug.html:
                return auszug.html, auszug.vollstaendig, "Datei neu geschrieben"
        # Letzter Weg: die ganze Datei neu — sofern sie ins Fenster passt.
        voll = nachrichten_fuer(True)
        if not self.passt_ins_fenster(voll, len(html) + 4000):
            raise Umsetzungsfehler("Die Änderung ließ sich nicht eindeutig in die Anwendung einarbeiten.",
                                   "Änderungsblöcke passten nicht; ganze Datei passt nicht ins Kontextfenster.")
        await self.technik("Änderungsblöcke nicht anwendbar — die Datei wird vollständig neu geschrieben.")
        text, grund = await self.generieren(voll, "Datei wird neu geschrieben", basis=len(html))
        auszug = await self.vervollstaendigen(voll, text, basis=len(html), gestuft=gestuft, grund=grund)
        if not auszug.html:
            raise Umsetzungsfehler("Das Modell hat keine geänderte Anwendung geliefert.", text[:600])
        if not auszug.vollstaendig:
            raise Grenzfall(grenzen.LIMIT_TEXT, "Die neu geschriebene Datei endet ohne </html>.", art="abgeschnitten")
        self.patch = Patchbericht(status="neu_geschrieben", bloecke=len(bloecke), grund=grund)
        return auszug.html, True, "Datei neu geschrieben"

    # ----------------------------------------------------- Gestufter Modus
    async def stufe_melden(self, zustand: str, **zusatz: Any) -> None:
        """Zustand der laufenden Stufe: planned → generating → connecting → validating
        (→ repairing) → passed | failed | aborted. Die Oberfläche zeigt immer diese Stufe."""
        if not self.aktive_stufe:
            return
        self.aktive_stufe["zustand"] = zustand
        if self.protokoll and self.protokoll.stufen:
            self.protokoll.stufen[-1]["zustand"] = zustand
        await self.melde("stufe", **{k: v for k, v in self.aktive_stufe.items() if k != "zustand"},
                         zustand=zustand, **zusatz)
        if zustand in {"generating", "validating", "passed", "failed", "aborted"}:
            await self.versuch_speichern()

    async def aendern_gestuft(self, html_basis: str, direkt: bool = False) -> tuple[str, bool]:
        """Große Änderung in geprüften Schritten auf einem internen Arbeitsstand.

        Kein Schritt ersetzt die aktive Version. Jeder bestandene Schritt wird
        als interner Checkpoint gesichert; scheitert ein späterer Schritt,
        bleibt die aktive Version unverändert, und ein neuer Versuch setzt am
        letzten Checkpoint fort. Erst die Endabnahme gegen den vollständigen
        Root-Vertrag entscheidet über die Promotion.

        Jede Stufe hat ein eigenes Budget (grenzen.stufe_*). Überschreitet sie
        es oder endet sie abgeschnitten, wird nichts angewendet; die Stufe
        bekommt genau einen knapperen zweiten Versuch.
        """
        if not self.linie:
            raise Umsetzungsfehler("Ohne Änderungsauftrag gibt es keinen Stufenplan.")
        self.gestuft = True
        if self.protokoll:
            self.protokoll.gestuft = True
        await self.status("building")
        linie = self.linie
        plan = linie.get("plan") or {}
        if not plan.get("stufen"):
            await self.schritt("erstellen", "aktiv", "JOSHI plant die Schritte …")
            # „versuch es erneut“ nach einer Teilversion: nur die Punkte planen, die die
            # aktive Version noch nicht nachweist — die Endprüfung prüft weiterhin alle.
            zu_planen = self._noch_offen(self.vertrag)
            if len(zu_planen.get("kriterien") or []) < len(self.vertrag.get("kriterien") or []):
                await self.melde("hinweis", text=(
                    f"{len(self.vertrag['kriterien']) - len(zu_planen['kriterien'])} Punkte sind in deiner aktiven "
                    f"Version schon nachgewiesen — JOSHI plant nur die {len(zu_planen['kriterien'])} offenen."))
            plan = await self.gemessen(aenderung.stufenplan_erzeugen(
                self.zugang, self.modell, wunsch=aenderung.gesamtwunsch(linie), vertrag=zu_planen,
                groesse=len(html_basis), verbrauch=self.verbrauch, max_stufen=self.grenzen.max_stufen))
            linie = await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], plan=plan)
            self.linie = linie
        stufen = plan.get("stufen") or []
        if not stufen:
            raise Umsetzungsfehler("Für diese Änderung ließ sich kein Stufenplan aufstellen.")
        von = len(stufen)
        aktive = int(self.produkt.get("version") or 0)
        start, arbeit, gliederung = 0, html_basis, self.baseline
        if (linie.get("checkpoint") and linie.get("checkpoint_basis") == aktive
                and 0 < int(linie.get("checkpoint_stufe") or 0) < von):
            start = int(linie["checkpoint_stufe"])
            arbeit = linie["checkpoint"]
            gliederung = linie.get("checkpoint_gliederung") or self.baseline
        aktiv_ids = {k["id"] for k in self.vertrag.get("kriterien") or []}

        def ruht(stufe: dict[str, Any]) -> bool:
            """Alle Kriterien des Schritts sind zurückgestellt oder entfallen."""
            return bool(stufe.get("kriterien")) and not any(i in aktiv_ids for i in stufe["kriterien"])
        umfang = f"{von} geprüfte Schritte" if von > 1 else "einen eigenen, geprüften Schritt"
        await self.melde("hinweis", text=(f"Plan: {umfang}." if direkt else
                                          f"JOSHI zerlegt diese umfangreiche Änderung in {umfang}.")
                         + (f" Schritte 1–{start} sind aus dem letzten Versuch schon geprüft; es geht bei "
                            f"Schritt {start + 1} weiter." if start else ""))
        await self.melde("stufen", von=von, start=start, stufen=[
            {"nummer": n + 1, "titel": s["titel"], "kriterien": len(s["kriterien"]),
             "zustand": "passed" if n < start else "deferred" if ruht(s) else "planned"}
            for n, s in enumerate(stufen)])
        await self.technik("Stufenplan (" + str(plan.get("quelle", "")) + "): "
                           + " | ".join(f"{n + 1}. {s['titel']} → {', '.join(s['kriterien'])}"
                                        for n, s in enumerate(stufen)))
        # Auch ein Stufenlauf bekommt bei Retries den Versuchszähler und die
        # bisherigen Befunde, nicht nur den nackten Root-Wunsch.
        gesamt = self.wunsch or aenderung.gesamtwunsch(linie)
        bilder = prompts.bilder_text(self.eingabe.bilder, self.sieht_bilder)
        baseline_vorher = self.baseline
        try:
            for index in range(start, von):
                self.pruefe_abbruch()
                stufe = stufen[index]
                nummer = index + 1
                if ruht(stufe):
                    if self.protokoll:
                        self.protokoll.stufen.append({"nummer": nummer, "titel": stufe["titel"],
                                                      "ergebnis": "zurueckgestellt", "zustand": "deferred"})
                    await self.technik(f"Schritt {nummer} („{stufe['titel']}“) übersprungen: alle Kriterien zurückgestellt")
                    continue
                self.stufe_text = f"{nummer}/{von}"
                self.aktive_stufe = {"nummer": nummer, "von": von, "titel": stufe["titel"]}
                eintrag: dict[str, Any] = {"nummer": nummer, "titel": stufe["titel"], "ergebnis": "laeuft",
                                           "zustand": "generating"}
                if self.protokoll:
                    self.protokoll.stufen.append(eintrag)
                teil = aenderung.teilvertrag(self.vertrag, stufe["kriterien"])
                wunsch = prompts.stufen_wunsch(gesamt, stufe, nummer, von,
                                               [s["titel"] for s in stufen[:index]], teil.get("kriterien") or [])
                await self.status("building")
                await self.schritt("erstellen", "aktiv", f"Schritt {nummer} von {von} · {stufe['titel']}")
                await self.stufe_melden("generating")
                vorher, beginn = self.usage_stand(), time.monotonic()
                self.baseline = gliederung
                try:
                    for anlauf in (1, 2):
                        try:
                            neu, vollstaendig, wie = await self.umsetzen(
                                arbeit, self._nachrichten_fuer(arbeit, wunsch, bilder),
                                f"Schritt {nummer} von {von} · Änderung wird erstellt", wunsch=wunsch, gestuft=True)
                            neu, bericht = await self.pruefen_und_reparieren(
                                neu, vollstaendig, [], vertrag=teil, max_reparaturen=REPARATUREN_JE_STUFE,
                                wunsch=wunsch, stufe=f"Schritt {nummer} von {von}")
                            break
                        except Grenzfall as fall:
                            eintrag.setdefault("grenzfaelle", []).append({"art": fall.art, "technik": fall.technik[:240]})
                            if anlauf == 2:
                                raise
                            grund = ("ließ sich nicht vollständig einarbeiten" if fall.art == "konflikt"
                                     else "endete am Ausgabelimit" if fall.art == "abgeschnitten"
                                     else "wurde zu umfangreich")
                            await self.melde("hinweis", text=(
                                f"Schritt {nummer} {grund} — nichts davon wurde übernommen. JOSHI "
                                "versucht ihn einmal knapper; die Schritte davor bleiben gesichert."))
                            wunsch = wunsch + "\n\n" + prompts.STUFE_KNAPP
                            await self.stufe_melden("generating", zweiter_versuch=True)
                except Grenzfall as fall:
                    # Ergebnisgarantie: Ein Schritt, der sich nicht einarbeiten
                    # lässt, hält die übrigen nicht auf. Nichts davon wird
                    # übernommen; JOSHI macht mit dem nächsten Schritt weiter.
                    eintrag.update(ergebnis="offen", grund=fall.technik[:300])
                    await self.stufe_offen(stufe["titel"], nummer, von, fall.text, "failed")
                    continue
                finally:
                    self.baseline = baseline_vorher
                    eintrag["usage"] = self.usage_seit(vorher, beginn)
                blockierend = [b for b in bericht.befunde if b.art in {"fehler", "abnahme"}]
                # Scheitert ein Schritt nur an Geschmacksfragen („zeigt sich im neuen Design“),
                # die keine Messregel hat und nur das Modell nach Augenmaß beurteilt, blockiert
                # er nicht (30.09.2026: Schritt 1 „Neues Design“ riss den ganzen Lauf ab, obwohl
                # die App lief und Schritte 2–6 schon erfüllt waren). Er bleibt als offen vermerkt.
                geschmack = self._nur_geschmack(bericht)
                if blockierend and geschmack and not any(b.art == "fehler" for b in bericht.befunde):
                    await self.technik(f"Schritt {nummer}: nur nicht messbare Gestaltung offen ({', '.join(geschmack)}) "
                                       "— kein Abbruch, JOSHI macht weiter.")
                    await self.melde("hinweis", text=(f"Schritt {nummer} („{stufe['titel']}“): Die Gestaltung lässt sich "
                                                      "nicht messen und wurde nicht eindeutig bestätigt. JOSHI macht "
                                                      "trotzdem weiter — sieh sie dir am Ende selbst an."))
                    bericht.befunde = [b for b in bericht.befunde if b.art != "abnahme"]
                    blockierend = []
                if blockierend or not self.vollstaendig:
                    grund = (blockierend[0].text if blockierend else "Die Datei blieb unvollständig.")[:300]
                    await self.technik(f"Schritt {nummer} offen: {bericht.reparaturtext()[:600]}")
                    if self.vollstaendig and tragfaehig(bericht) and neu != arbeit:
                        # Läuft fehlerfrei, nur nicht nachgewiesen: übernehmen —
                        # spätere Schritte und die Endprüfung bauen darauf auf.
                        eintrag.update(ergebnis="nicht_nachgewiesen", grund=grund, zeichen=len(neu))
                        arbeit, gliederung = neu, bericht.gliederung
                        self.zwischenstand = arbeit
                        await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], checkpoint=neu,
                                                checkpoint_stufe=nummer, checkpoint_basis=aktive,
                                                checkpoint_gliederung=_gliederung_kompakt(gliederung))
                        await self.stufe_offen(stufe["titel"], nummer, von, grund, "not_proven", uebernommen=True)
                    else:
                        eintrag.update(ergebnis="offen", grund=grund)
                        await self.stufe_offen(stufe["titel"], nummer, von, grund, "failed")
                    continue
                arbeit, gliederung = neu, bericht.gliederung
                self.zwischenstand = arbeit
                unbewiesen = int((bericht.abnahme.get("zaehlung") or {}).get("NOT_PROVEN") or 0)
                eintrag.update(ergebnis="bestanden", zeichen=len(neu), wie=wie, nicht_bewiesen=unbewiesen)
                await asyncio.to_thread(speicher.aenderung_aendern, linie["id"], checkpoint=neu,
                                        checkpoint_stufe=nummer, checkpoint_basis=aktive,
                                        checkpoint_gliederung=_gliederung_kompakt(gliederung))
                await self.stufe_melden("passed", nicht_bewiesen=unbewiesen)
                await self.technik(f"Schritt {nummer} bestanden: {bericht.kurzfassung()} "
                                   f"(interner Checkpoint, {zahl(len(neu))} Zeichen — nicht aktiv) · Usage "
                                   f"{eintrag['usage']['ausgabe']} Ausgabe / {eintrag['usage']['eingabe']} Eingabe, "
                                   f"{eintrag['usage']['sekunden']} s")
        except asyncio.CancelledError:
            await self.stufe_melden("aborted")
            raise
        finally:
            self.aktive_stufe = None
        self.stufe_text = f"{von}/{von}"
        if arbeit == html_basis:
            gruende = "; ".join(f"„{t}“: {g}" for t, g in self.offene_stufen[:4])
            raise Umsetzungsfehler(
                "Keiner der Schritte ließ sich einbauen, ohne die Anwendung zu beschädigen — deine aktive Version "
                f"bleibt unverändert. Woran es lag: {gruende}", "Kein tragfähiger Zwischenstand")
        offen = len(self.offene_stufen)
        await self.schritt("erstellen", "fertig" if not offen else "fehler",
                           f"{von - offen} von {von} Schritten geprüft umgesetzt" + (f", {offen} offen" if offen else ""))
        return arbeit, True

    def _noch_offen(self, vertrag: dict[str, Any]) -> dict[str, Any]:
        """Der Vertrag ohne die Kriterien, die die aktive Version schon nachweist."""
        nummer = int(self.produkt.get("version") or 0)
        aktiv = speicher.version(self.produkt["id"], nummer) if nummer else None
        bestanden = {e.get("id") for e in (((aktiv or {}).get("pruefung") or {}).get("abnahme") or {}).get("ergebnisse") or []
                     if e.get("status") == "PASS"}
        offen = [k for k in vertrag.get("kriterien") or [] if k.get("id") not in bestanden]
        return {**vertrag, "kriterien": offen} if offen else vertrag

    async def stufe_offen(self, titel: str, nummer: int, von: int, grund: str, zustand: str,
                          uebernommen: bool = False) -> None:
        """Ein Schritt bleibt offen — gemeldet, vermerkt, und JOSHI macht weiter."""
        self.offene_stufen.append((titel, grund))
        await self.stufe_melden(zustand, grund=grund[:200])
        await self.melde("hinweis", text=(
            f"Schritt {nummer} von {von} („{titel}“) ließ sich nicht nachweisen"
            + (" — er läuft fehlerfrei und bleibt drin." if uebernommen else " — nichts davon wurde übernommen.")
            + (" JOSHI macht mit den übrigen Schritten weiter." if nummer < von else "")))

    # -------------------------------------------------------------- Prüfen
    def verbinden(self, html: str, assets: dict[str, str]) -> tuple[str, list[str]]:
        """Deterministische Handgriffe, die kein Modell vergessen darf."""
        hinweise: list[str] = []
        from app.joshi import bibliotheken

        html, eingebunden, fehlgeschlagen = bibliotheken.einbinden(html)
        if eingebunden:
            hinweise.append(f"Bibliothek eingebettet: {', '.join(eingebunden)} — läuft ohne Internet")
        if fehlgeschlagen:
            hinweise.append(f"Bibliothek nicht ladbar: {', '.join(fehlgeschlagen)}")
        if not re.search(r"<meta[^>]+charset", html, re.IGNORECASE):
            html = re.sub(r"(<head\b[^>]*>)", r'\1<meta charset="utf-8">', html, count=1, flags=re.IGNORECASE)
        if not re.search(r"<meta[^>]+name=[\"']?viewport", html, re.IGNORECASE):
            html = re.sub(r"(<head\b[^>]*>)",
                          r'\1<meta name="viewport" content="width=device-width, initial-scale=1">',
                          html, count=1, flags=re.IGNORECASE)
            hinweise.append("Viewport für Smartphones ergänzt")
        if not re.search(r"<title\b", html, re.IGNORECASE):
            titel = self.produkt["titel"].replace("<", "").replace(">", "")
            html = re.sub(r"(</head\s*>)", f"<title>{titel}</title>\\1", html, count=1, flags=re.IGNORECASE)
        unbekannt = [v for v in asset_verweise(html) if v not in assets]
        if unbekannt:
            hinweise.append("Unbekannte Bildverweise: " + ", ".join(unbekannt))
        eingebunden = [v for v in asset_verweise(html) if v in assets]
        if eingebunden:
            hinweise.append(f"{len(eingebunden)} Bild{'er' if len(eingebunden) != 1 else ''} eingebettet")
        return html, hinweise

    async def abnehmen(self, html: str, bericht: pruefer.Pruefbericht, vertrag: dict[str, Any],
                       zustand: dict[str, Any] | None, assets: dict[str, str]) -> None:
        """Prüft nach der Technik, ob der Auftrag wirklich umgesetzt und belegt ist.

        Nur wenn die Anwendung technisch läuft — sonst wäre jede Aussage über
        den Inhalt wertlos, und die technische Reparatur kommt zuerst.
        Aktionsproben und Szenarien laufen nur, wenn der Vertrag sie verlangt.
        """
        kriterien = vertrag.get("kriterien") or []
        if not kriterien or not bericht.browser:
            return
        if any(b.art == "fehler" for b in bericht.befunde):
            return
        proben = abnahme.benoetigte_proben(vertrag)
        ablauf = abnahme.szenario_kriterien(vertrag)
        gezielt = abnahme.gezielte_szenarien(vertrag, bericht.gliederung)
        szenarien: list[dict[str, Any]] = []
        if ablauf:
            fehlend = [k for k in ablauf if k["id"] not in self.szenarien]
            if fehlend:
                erzeugt = await self.gemessen(abnahme.szenarien_erzeugen(
                    self.zugang, self.modell, kriterien=fehlend, gliederung=bericht.gliederung,
                    verbrauch=self.verbrauch))
                for szenario in erzeugt:
                    self.szenarien[szenario["kriterium"]] = szenario
                await self.technik(f"Szenarien: {len(erzeugt)} von {len(fehlend)} Ablauf-Kriterien haben ein Prüfszenario")
            szenarien = [self.szenarien[k["id"]] for k in ablauf if k["id"] in self.szenarien]
        # Diese Proben werden aus echten Feld-/Knopf-Beschriftungen gebaut;
        # sie umgehen weder Browserprüfung noch Persistenzprüfung und brauchen
        # keinen zusätzlichen Modellaufruf.
        szenarien.extend(s for s in gezielt if s.get("kriterium") not in {
            e.get("kriterium") for e in szenarien})
        if proben or szenarien:
            self.pruefe_abbruch()
            bericht.aktionen, bericht.szenarien = await pruefer.szenarien_ausfuehren(
                html, assets=assets, zustand=zustand, aktionen=proben, szenarien=szenarien)
            for probe in bericht.aktionen:
                await self.technik(f"Aktionsprobe {probe.get('aktion')} „{probe.get('knopf')}“: {probe.get('ergebnis')}"
                                   f" {', '.join(probe.get('belege') or [])} {probe.get('grund', '')}".strip())
            for szenario in bericht.szenarien:
                await self.technik(f"Szenario {szenario.get('id')}: {szenario.get('ergebnis')} "
                                   f"{szenario.get('grund', '')} {json.dumps(szenario.get('messwerte') or {})}".strip())
                # Ein Szenario, dessen Ziele es in dieser Fassung nicht gibt,
                # wird für die nächste Fassung neu geschrieben.
                if szenario.get("ergebnis") == "nicht_beweisbar" and "nicht gefunden" in str(szenario.get("grund")):
                    self.szenarien.pop(str(szenario.get("kriterium")), None)
        beweise = abnahme.beweise_sammeln(bericht.gliederung, bericht.interaktion, self.baseline, bericht.exporte,
                                          aktionen=bericht.aktionen, szenarien=bericht.szenarien,
                                          mobil=bericht.mobil)
        if not abnahme.beweisbar(beweise):
            self.datenabgleich(html, bericht)
            return
        abnahmebericht = await self.gemessen(abnahme.pruefen(
            self.zugang, self.modell, vertrag, beweise,
            verbrauch=self.verbrauch, streng=self.art == "aendern"))
        bericht.abnahme = abnahmebericht.als_dict()
        bericht.befunde.extend(abnahmebericht.befunde())
        zaehlung = abnahmebericht.zaehlung()
        self.letzte_abnahme = zaehlung
        await self.technik(f"Abnahme: PASS {zaehlung['PASS']} · FAIL {zaehlung['FAIL']} · "
                           f"NOT_PROVEN {zaehlung['NOT_PROVEN']} von {len(abnahmebericht.ergebnisse)} Kriterien"
                           + (" (mit Modellurteil)" if abnahmebericht.modell_gefragt else " (allein aus der Messung)"))
        self.datenabgleich(html, bericht)
        if self.recherche_funde:
            letzte = (bericht.abnahme.get("ergebnisse") or [{}])[-1]
            await self.technik(f"Datenabgleich: {letzte.get('status')} — {letzte.get('begruendung', '')}")

    async def pruefen_und_reparieren(self, html: str, vollstaendig: bool, erwartet: list[str], *,
                                     vertrag: dict[str, Any] | None = None, max_reparaturen: int = MAX_REPARATUREN,
                                     wunsch: str | None = None, stufe: str = "") -> tuple[str, pruefer.Pruefbericht]:
        vertrag = self.vertrag if vertrag is None else vertrag
        assets = await asyncio.to_thread(speicher.bild_data_uris, self.produkt["id"])
        zustand = self.produkt.get("zustand") if self.art in {"aendern", "reparieren"} else None
        vorsilbe = f"{stufe}: " if stufe else ""
        versuch = 0
        # Eine Reparatur darf nie schlechter machen, was schon da war: Gemessen
        # am 19.09. baute die zweite Reparatur einer Umfrage einen Syntaxfehler
        # ein, und die bessere erste Fassung ging verloren. Jetzt zählt die
        # beste geprüfte Fassung, und jede Reparatur setzt auf ihr auf.
        bester: tuple[tuple[int, int, int], str, bool, pruefer.Pruefbericht] | None = None
        vorige_signatur: Any = None
        while True:
            await self.phase("verbinden", "aktiv", "Laufzeit, Speicher und Bilder werden eingebunden …")
            html, hinweise = self.verbinden(html, assets)
            await self.phase("verbinden", "fertig", ", ".join(hinweise) or "Zustand und Bilder eingebunden")
            self.pruefe_abbruch()
            await self.status("validating")
            await self.phase("pruefen", "aktiv", vorsilbe + "Die Anwendung wird im Browser geladen und bedient …")
            bericht = await pruefer.pruefen(html, assets=assets, zustand=zustand, erwartet=erwartet,
                                            abgeschnitten=not vollstaendig, baseline=self.baseline,
                                            rueckbau=bool(vertrag.get("rueckbau")), fokus=fokuswoerter(vertrag))
            await self.abnehmen(html, bericht, vertrag, zustand, assets)
            for befund in bericht.befunde:
                await self.technik(f"{vorsilbe}[{befund.art}] {befund.text} {befund.technik}".strip())
            wertung = (sum(b.art == "fehler" for b in bericht.befunde),
                       sum(b.art in AKZEPTANZ for b in bericht.befunde),
                       sum(b.art == "luecke" for b in bericht.befunde))
            # Gleiche Befunde wie vor der Reparatur: Die Reparatur hat nichts
            # bewirkt, eine weitere würde nur raten. Gefunden am 27.09.2026:
            # drei Runden mit exakt PASS 2 / FAIL 6, rund 150 s und 26.000 Tokens.
            signatur = (wertung, tuple(sorted((b.art, b.text, b.technik[:400]) for b in bericht.befunde
                                              if b.art in pruefer.REPARIERBAR)))
            stillstand = versuch > 0 and signatur == vorige_signatur
            vorige_signatur = signatur
            if bester is None or wertung < bester[0]:
                bester = (wertung, html, vollstaendig, bericht)
            elif wertung > bester[0]:
                await self.technik(f"Reparatur {versuch} hat die Anwendung verschlechtert — "
                                   "weiter mit der besseren Fassung davor.")
            _, html, vollstaendig, bericht = bester
            self.vollstaendig = vollstaendig
            bedarf = bericht.reparaturbedarf()
            if stillstand and bedarf:
                await self.technik(f"{vorsilbe}Reparatur {versuch} ohne messbare Wirkung — dieselben Befunde wie davor. "
                                   "JOSHI hört hier auf, statt weiter zu raten.")
            if not bedarf or versuch >= max_reparaturen or stillstand:
                await self.phase("pruefen", "fertig" if bericht.ok else "fehler", vorsilbe + bericht.kurzfassung())
                return html, bericht
            versuch += 1
            self.reparaturen += 1
            if self.protokoll:
                self.protokoll.reparaturen = self.reparaturen
            await self.status("repairing")
            nur_luecken = all(b.art == "luecke" for b in bedarf)
            nur_abnahme = all(b.art in AKZEPTANZ | {"luecke"} for b in bedarf)
            if nur_luecken:
                taetigkeit = "ergänzt " + ("eine Lücke" if len(bedarf) == 1 else f"{len(bedarf)} Lücken")
            elif nur_abnahme:
                taetigkeit = "setzt den Auftrag noch vollständig um"
            else:
                taetigkeit = "behebt " + ("ein Problem" if len(bedarf) == 1 else f"{len(bedarf)} Probleme")
            await self.phase("pruefen", "reparatur",
                             f"{vorsilbe}JOSHI {taetigkeit} (Versuch {versuch} von {max_reparaturen}) …")
            await self.melde("hinweis", text=(
                ("JOSHI ergänzt, was noch fehlt: " if nur_luecken else
                 "JOSHI arbeitet den Auftrag nach: " if nur_abnahme else
                 "JOSHI konnte einen Teil der Anwendung noch nicht korrekt starten und repariert ihn: ")
                + "; ".join(b.text for b in bedarf[:3])))
            # Bei einer Abnahmelücke zählt der ursprüngliche Wunsch — bei einem
            # erneuten Versuch der ganze Root-Wunsch, nie nur „versuch es erneut“.
            ziel = wunsch if wunsch is not None else (
                self.wunsch or self.eingabe.text if self.art == "aendern" else self.produkt.get("auftrag", ""))

            def nachrichten_fuer(ganz: bool, basis: str = html) -> list[dict[str, Any]]:
                return prompts.reparieren_nachrichten(basis, bericht.reparaturtext(),
                                                      auftrag=ziel, vollstaendig=ganz)

            try:
                if not vollstaendig:
                    # Abgeschnittene Datei: Blöcke wären sinnlos, also ganz neu und knapper.
                    nachrichten = nachrichten_fuer(True)
                    text, grund = await self.generieren(nachrichten, "Reparatur wird geschrieben", basis=len(html))
                    # Dieser Reparaturpfad schreibt absichtlich eine ganze
                    # Datei. In einer Stage gilt dafür dieselbe harte Regel
                    # wie für den normalen Builder: `length` ist nie ein
                    # Kandidat, selbst wenn das HTML zufällig vollständig wirkt.
                    if stufe and grenzen.ist_abgeschnitten(grund):
                        self._abgeschnittene_stufe_verwerfen(text, grund)
                    auszug = await self.vervollstaendigen(nachrichten, text, basis=len(html),
                                                          gestuft=bool(stufe), grund=grund)
                    if auszug.html:
                        html, vollstaendig = auszug.html, auszug.vollstaendig
                    continue
                html, vollstaendig, _ = await self.umsetzen(html, nachrichten_fuer, "Reparatur wird geschrieben",
                                                            wunsch=ziel, gestuft=bool(stufe))
            except Grenzfall as fall:
                await self.technik(f"Reparatur nicht übernommen ({fall.art}): {fall.technik}")
                _, html, vollstaendig, bericht = bester
                await self.phase("pruefen", "fehler", vorsilbe + bericht.kurzfassung())
                return html, bericht
            except Umsetzungsfehler as fehler:
                await self.technik(f"Reparatur nicht anwendbar: {fehler.text}")
                await self.phase("pruefen", "fehler", vorsilbe + bericht.kurzfassung())
                return html, bericht

    async def phase(self, name: str, zustand: str, text: str) -> None:
        """Verbinden und Prüfen: im gestuften Modus Phasen der laufenden Stufe.

        Gefunden im Killer-Retest am 21.09.2026: Die Prüfung von Schritt 1
        setzte die globalen Schritte „Verbinden“ und „Prüfen“ auf erledigt —
        während Schritt 2 schon lief, sah es aus, als hinge JOSHI bei Schritt 1.
        """
        if not self.aktive_stufe:
            await self.schritt(name, zustand, text)
            return
        if name == "verbinden" and zustand == "aktiv":
            await self.stufe_melden("connecting")
        elif name == "pruefen" and zustand == "aktiv":
            await self.stufe_melden("validating")
        elif name == "pruefen" and zustand == "reparatur":
            await self.stufe_melden("repairing", detail=text)

    async def abbruch_vermerken(self) -> None:
        """Abbruch: Linie und Versuch sauber als abgebrochen vermerken — nichts wird aktiv."""
        try:
            if self.protokoll:
                self.protokoll.ergebnis = "abgebrochen"
                self.protokoll.ergebnis_text = "Vom Nutzer abgebrochen"
                await self.versuch_speichern()
            if self.linie:
                await asyncio.to_thread(speicher.aenderung_aendern, self.linie["id"], status="abgebrochen")
            await self.tokenstand(laufend=False)
        except Exception:  # noqa: BLE001 – der Abbruch selbst darf nicht scheitern
            pass

    # ------------------------------------------------------------ Abschluss
    def diagnose(self, befoerdert: bool, bericht: pruefer.Pruefbericht | None = None) -> dict[str, Any]:
        """Was „Technische Details“ über diesen Versuch zeigt."""
        abnahme_zahlen = dict(self.letzte_abnahme)
        if bericht is not None and bericht.abnahme.get("zaehlung"):
            abnahme_zahlen = bericht.abnahme["zaehlung"]
        return {
            "versuch": self.protokoll.versuch if self.protokoll else 1,
            "aenderung": self.linie["id"] if self.linie else "",
            "kriterien": len(self.vertrag.get("kriterien") or []),
            "pflicht": len(aenderung.pflichtkriterien(self.vertrag)) if self.art == "aendern" else 0,
            "gestuft": self.gestuft,
            "stufe": self.stufe_text,
            "stufen": self.protokoll.stufen if self.protokoll else [],
            "ausgabe_zeichen": self.ausgabe_zeichen,
            "ausgabe_tokens": self.verbrauch["completion_tokens"],
            "grund": self.gruende[-1] if self.gruende else "",
            "gruende": self.gruende[-8:],
            "patch": self.patch.als_dict() if self.patch else {},
            "abnahme": abnahme_zahlen,
            "reparaturen": self.reparaturen,
            "befoerdert": befoerdert,
            "signale": [s.als_dict() for s in self.signale][:10],
            "routing": self.komplex,
            "tokens": {k: v for k, v in self.tokenwerte().items()
                       if k in {"tokens_actual", "output_tokens_actual", "input_tokens_actual", "eingabetokens",
                                "output_tokens_estimated", "output_tokens_incomplete", "abgebrochen_geschaetzt",
                                "usage_status", "rate_geschaetzt", "aufrufe"}},
        }

    async def versuch_abschliessen(self, ergebnis: str, text: str, *, kandidat: int = 0,
                                   bericht: pruefer.Pruefbericht | None = None) -> None:
        if not (self.linie and self.protokoll):
            return
        self.protokoll.ergebnis = ergebnis
        self.protokoll.ergebnis_text = text[:300]
        self.protokoll.kandidat = kandidat
        self.protokoll.patch = self.patch.als_dict() if self.patch else {}
        if bericht is not None:
            self.protokoll.abnahme = bericht.abnahme.get("zaehlung") or dict(self.letzte_abnahme)
            self.protokoll.offen = [e.get("beschreibung", "") for e in bericht.abnahme.get("ergebnisse") or []
                                    if e.get("status") in {"FAIL", "NOT_PROVEN"} and e.get("pflicht")][:10]
        await self.versuch_speichern()
        if ergebnis == "teilweise":
            # Die neue aktive Version ist die Basis für den nächsten Versuch:
            # alte Checkpoints und Schrittpläne passen nicht mehr zu ihr.
            await asyncio.to_thread(speicher.aenderung_aendern, self.linie["id"], checkpoint="", checkpoint_stufe=0,
                                    plan={}, status="open")
        if ergebnis == "befoerdert":
            await asyncio.to_thread(speicher.aenderung_aendern, self.linie["id"], status="umgesetzt", checkpoint="",
                                    checkpoint_stufe=0)

    async def abschliessen(self, html: str, bericht: pruefer.Pruefbericht, aenderung_text: str,
                           vorherige: dict[str, Any] | None) -> None:
        """Ein Kandidat wird nur dann die aktive Version, wenn er besteht.

        Technik, Sichtbarkeit und Abnahme müssen stimmen. Sonst bleibt bei
        einer Änderung die letzte funktionierende Version aktiv; der Kandidat
        bleibt als abgelehnte Version in der Geschichte nachlesbar. Ein
        unvollständiger Kandidat (abgeschnitten) wird nie aktiv, auch nicht
        als Erstfassung.
        """
        erstfassung = self.art in {"bauen", "importieren"} or not vorherige
        vorher_ok = bool(vorherige and vorherige.get("pruefung", {}).get("ok"))
        assets = await asyncio.to_thread(speicher.bild_data_uris, self.produkt["id"])
        pruefung = bericht.als_dict()
        pruefung["diagnose"] = self.diagnose(False, bericht)
        if self.eingabe.eingaben:
            # Womit diese Version gebaut wurde — nachvollziehbar, auch wenn sich
            # die Dateien im Asset-/Eingabeordner später ändern.
            pruefung["eingaben"] = [a.snapshot() for a in self.eingabe.eingaben]
        akzeptanz_luecke = any(b.art in AKZEPTANZ for b in bericht.befunde)
        if not self.vollstaendig:
            await self.scheitern(grenzen.LIMIT_TEXT, "Der beste Kandidat ist unvollständig (kein </html>).",
                                 int(vorherige["nummer"]) if vorherige else 0, bericht=bericht)
            return
        # Mindestens eine funktionierende Version: Läuft der Kandidat fehlerfrei,
        # ist nichts verloren gegangen und ist wenigstens ein Pflichtpunkt
        # nachgewiesen, wird er aktiv — mit ehrlicher Liste des Offenen. Der
        # Auftrag bleibt offen; „versuch es erneut“ holt den Rest nach.
        ergebnisse = bericht.abnahme.get("ergebnisse") or []
        erfuellt = [e for e in ergebnisse if e.get("pflicht") and e.get("status") == "PASS"]
        pflicht = [e for e in ergebnisse if e.get("pflicht")]
        # Ergebnisgarantie (06.10.2026): Jeder Kandidat, der fehlerfrei läuft,
        # nichts verloren hat und sich von der aktiven Version unterscheidet,
        # wird Ergebnis — auch wenn der Wunsch (noch) nicht nachgewiesen ist.
        # Nie aktiv wird nur, was die Anwendung beschädigen würde.
        geaendert = bool(vorherige) and html != vorherige.get("html")
        teilweise = (not erstfassung and self.art == "aendern" and not bericht.ok and geaendert
                     and tragfaehig(bericht))
        # Fortschrittssperre: Ein neuer Stand darf nie weniger nachweisen als die aktive
        # Version (06.10.2026: AI Escape v6 wies 2 statt 3 Punkte nach und wurde trotzdem aktiv).
        vorher_bestanden, jetzt_bestanden = nachweis_vergleich(vorherige, bericht)
        if teilweise and jetzt_bestanden < vorher_bestanden:
            await self.ohne_fortschritt(html, bericht, aenderung_text, vorherige, pruefung,
                                        vorher_bestanden, jetzt_bestanden)
            return
        if not erstfassung and not bericht.ok and (vorher_ok or akzeptanz_luecke) and not teilweise:
            pruefung["abgelehnt"] = True
            nummer, _ = await asyncio.to_thread(
                speicher.version_festschreiben, self.produkt["id"], html, aenderung_text,
                zusammenfassung=bericht.kurzfassung(), pruefung=pruefung, modell=self.modell, aktivieren=False,
            )
            offen = [e["beschreibung"] for e in (bericht.abnahme.get("ergebnisse") or [])
                     if e.get("status") in {"FAIL", "NOT_PROVEN"} and e.get("pflicht")]
            text = ("JOSHI konnte die gewünschte Änderung noch nicht vollständig umsetzen. "
                    f"Deine letzte funktionierende Version {vorherige['nummer']} bleibt aktiv.")
            await self.technik(f"Kandidat {nummer} abgelehnt: {bericht.kurzfassung()}")
            await self.scheitern(text, bericht.reparaturtext(), vorherige["nummer"],
                                 warnungen=offen or [bericht.kurzfassung()], kandidat=nummer, bericht=bericht,
                                 ergebnis=True)
            return
        await self.schritt("teilbar", "aktiv", "Teilbare Fassung wird vorbereitet …")
        portabel = export_dokument(html, zustand=self.produkt.get("zustand"), assets=assets,
                                   meta={"joshi": 1, "titel": self.produkt["titel"], "produkt": self.produkt["id"]})
        status = "ready" if bericht.ok else "needs_attention"
        pruefung["diagnose"] = self.diagnose(True, bericht)
        nummer, _ = await asyncio.to_thread(
            speicher.version_festschreiben, self.produkt["id"], html, aenderung_text,
            zusammenfassung=bericht.kurzfassung(), pruefung=pruefung, modell=self.modell,
            aktivieren=True, status=status,
        )
        await self.versuch_abschliessen("teilweise" if teilweise else "befoerdert", f"Version {nummer}",
                                        kandidat=nummer, bericht=bericht)
        await self.arbeitsordner_sichern(nummer, html)
        produkt = await asyncio.to_thread(speicher.produkt, self.user_id, self.produkt["id"])
        await self.schritt("teilbar", "fertig", f"Version {nummer} · {zahl(len(portabel.encode()) // 1024)} KB als eine Datei")
        warnungen = [b.text for b in bericht.befunde if b.art in {"warnung", "luecke"}]
        if teilweise:
            offen = [e["beschreibung"] for e in pflicht if e.get("status") != "PASS"]
            # Ein offener Schritt, dessen Grund schon als offener Punkt dasteht, wird nicht doppelt genannt.
            schritte = [f"Schritt „{t}“: {g}" for t, g in self.offene_stufen
                        if not any(o[:60] in g for o in offen)]
            warnungen = [f"Offen: {o}" for o in offen] + [f"Offen – {x}" for x in schritte] + warnungen
            if erfuellt:
                text = (f"Version {nummer} ist aktiv und funktioniert — teilweise umgesetzt: {len(erfuellt)} von "
                        f"{len(pflicht)} Punkten nachgewiesen.")
            else:
                text = (f"Version {nummer} ist aktiv und läuft fehlerfrei — JOSHI hat die Änderung eingebaut, "
                        "konnte sie aber im Browser noch nicht nachweisen. Sieh sie dir bitte selbst an.")
            text += (f" Schreib „versuch es erneut“, dann arbeitet JOSHI gezielt die offenen Punkte nach. "
                     f"„Rückgängig“ holt Version {vorherige['nummer']} zurück.")
        elif bericht.ok:
            text = f"Version {nummer} ist bereit. {bericht.kurzfassung()}"
        else:
            text = (f"Version {nummer} ist sichtbar, aber nicht fehlerfrei: {bericht.kurzfassung()} "
                    "Beschreibe, was anders sein soll, oder lass JOSHI den Fehler beheben.")
        diagnose = self.diagnose(True, bericht)
        await self.technik(self.diagnose_text(diagnose))
        ergebnis = {"version": nummer, "status": status, "text": text, "warnungen": warnungen[:6],
                    "pruefung": {k: v for k, v in pruefung.items() if k != "gliederung"}, "diagnose": diagnose}
        await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id, status=status,
                                ergebnis=ergebnis, verbrauch=self.verbrauch)
        await self.tokenstand()
        await self.melde("fertig", **ergebnis, produkt=produkt, verbrauch=self.verbrauch)
        await self.status(status, text)

    async def ohne_fortschritt(self, html: str, bericht: pruefer.Pruefbericht, aenderung_text: str,
                               vorherige: dict[str, Any], pruefung: dict[str, Any], vorher: int, jetzt: int) -> None:
        """Ergebnis ohne neue aktive Version: Der neue Stand läuft, weist aber weniger nach.

        Kein Scheitern — eine ehrliche Antwort: Die bessere Version bleibt aktiv, der neue
        Stand liegt in der Versionsliste, und es steht da, was offen ist und warum.
        """
        pruefung = {**pruefung, "abgelehnt": True, "diagnose": self.diagnose(False, bericht)}
        nummer, _ = await asyncio.to_thread(
            speicher.version_festschreiben, self.produkt["id"], html, aenderung_text,
            zusammenfassung=bericht.kurzfassung(), pruefung=pruefung, modell=self.modell, aktivieren=False)
        await self.versuch_abschliessen("abgelehnt", f"Version {nummer} weist weniger nach ({jetzt} statt {vorher})",
                                        kandidat=nummer, bericht=bericht)
        offen = [e["beschreibung"] for e in (bericht.abnahme.get("ergebnisse") or [])
                 if e.get("pflicht") and e.get("status") != "PASS"]
        text = (f"Version {vorherige['nummer']} bleibt aktiv — sie weist mehr nach ({vorher} Punkte) als der neue Stand "
                f"({jetzt} Punkte). Der neue Stand läuft fehlerfrei und liegt als Version {nummer} in der Versionsliste. "
                "Schreib „versuch es erneut“, dann arbeitet JOSHI gezielt die offenen Punkte nach.")
        warnungen = [f"Offen: {o}" for o in offen] + [b.text for b in bericht.befunde if b.art in {"warnung", "luecke"}]
        status = await asyncio.to_thread(speicher.status_fuer_version, self.produkt["id"], vorherige["nummer"])
        produkt = await asyncio.to_thread(speicher.produkt_aendern, self.user_id, self.produkt["id"], status=status)
        diagnose = self.diagnose(False, bericht)
        await self.technik(self.diagnose_text(diagnose))
        ergebnis = {"version": vorherige["nummer"], "status": "needs_attention", "text": text,
                    "warnungen": warnungen[:6], "kandidat": nummer, "diagnose": diagnose}
        await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id, status="needs_attention",
                                ergebnis=ergebnis, verbrauch=self.verbrauch)
        await self.tokenstand()
        await self.melde("fertig", **ergebnis, produkt=produkt, verbrauch=self.verbrauch)
        await self.status("needs_attention", text)

    async def arbeitsordner_sichern(self, nummer: int, html: str) -> None:
        """Jedes Produkt hat intern einen Arbeitsordner — ohne Schalter, ohne Rückfrage.

        Nach jeder angenommenen Version: index.html (Bilder unter assets/,
        Daten unter data/), JOSHI_PROJECT.md, README.md und bei großen
        Anwendungen die Projektdateien, in denen JOSHI arbeitet. Wird das Produkt
        erstmals zu groß für eine Datei, sagt JOSHI das dem Nutzer.
        """
        produkt_id = self.produkt["id"]
        produkt = await asyncio.to_thread(speicher.produkt, self.user_id, produkt_id)
        if not produkt:
            return
        intern = dict((produkt.get("quelle") or {}).get("intern") or {})
        try:
            ordner = projektdateien.ordner(database.DATA_DIR, produkt)
            wurzel = dateien.Wurzel(ordner.parent, schreibbar=True, name="JOSHI intern")
            ordner.parent.mkdir(parents=True, exist_ok=True)
            version = await asyncio.to_thread(speicher.version, produkt_id, nummer)
            versionen = await asyncio.to_thread(speicher.versionen, produkt_id)
            bilder = await asyncio.to_thread(speicher.bilder, produkt_id)

            def bild_bytes(name: str) -> bytes | None:
                treffer = speicher.bild_bytes(produkt_id, name)
                return treffer[0] if treffer else None

            neu = await asyncio.to_thread(projekt.schreiben, wurzel, produkt=produkt, version=version,
                                          versionen=versionen, bilder=bilder, bild_bytes=bild_bytes,
                                          auswahl=self.eingabe.eingaben, meta={**intern, "ordner": ordner.name})
            gross = len(html) >= projektdateien.PROJEKT_AB
            if gross:
                await asyncio.to_thread(projektdateien.schreiben, ordner / "dateien",
                                        projektdateien.zerlegen(html), version=nummer)
            neu.update(gross=gross, zeichen=len(html), zip=zip_noetig(neu))
            await asyncio.to_thread(speicher.produkt_aendern, self.user_id, produkt_id,
                                    quelle={**(produkt.get("quelle") or {}), "intern": neu})
            await self.technik(f"Arbeitsordner gesichert: {ordner}" + (" (mit Projektdateien)" if gross else ""))
            if gross and not intern.get("gross"):
                await self.melde("hinweis", text=(
                    f"Dein Produkt ist mit {zahl(len(html))} Zeichen zu groß, um es als eine einzige Datei "
                    "zuverlässig zu ändern. JOSHI arbeitet ab jetzt intern in Projektdateien (HTML, CSS und "
                    "JavaScript getrennt) — du merkst davon nichts, teilen kannst du es weiterhin wie gewohnt."))
        except (dateien.Pfadfehler, projektdateien.ProjektFehler, OSError) as fehler:
            await self.technik(f"Arbeitsordner nicht geschrieben: {fehler}")

    @staticmethod
    def diagnose_text(d: dict[str, Any]) -> str:
        patch = d.get("patch") or {}
        teile = [f"Versuch {d.get('versuch')}"]
        if d.get("kriterien"):
            teile.append(f"Root-Vertrag {d['kriterien']} Kriterien")
        if d.get("gestuft"):
            teile.append(f"gestuft, Schritt {d.get('stufe') or '–'}")
        teile.append(f"Ausgabe {zahl(int(d.get('ausgabe_zeichen') or 0))} Zeichen / "
                     f"{zahl(int(d.get('ausgabe_tokens') or 0))} Tokens, Ende {d.get('grund') or '–'}")
        if patch:
            teile.append(f"Patch {patch.get('status')}: {patch.get('angewendet', 0)}/{patch.get('bloecke', 0)} Blöcke,"
                         f" {patch.get('konflikte', 0)} Konflikte")
        zahlen = d.get("abnahme") or {}
        if zahlen:
            teile.append(f"Abnahme PASS {zahlen.get('PASS', 0)} / FAIL {zahlen.get('FAIL', 0)} / "
                         f"NOT_PROVEN {zahlen.get('NOT_PROVEN', 0)}")
        teile.append(f"Reparaturen {d.get('reparaturen', 0)}")
        teile.append("befördert" if d.get("befoerdert") else "nicht befördert")
        return "Diagnose: " + " · ".join(teile)

    async def scheitern(self, text: str, technik: str, aktive_version: int,
                        warnungen: list[str] | None = None, kandidat: int = 0,
                        bericht: pruefer.Pruefbericht | None = None, ergebnis: bool = False) -> None:
        """Kein neuer Stand. Mit `ergebnis` (es gibt eine aktive Version, JOSHI selbst kam
        nicht weiter) ist das eine Antwort mit Begründung — „Mit Einschränkungen“, kein
        Fehlschlag (Ergebnisgarantie, 06.10.2026). Ein echter Fehlschlag bleibt nur, wenn
        der Modelldienst nicht verfügbar ist oder es noch gar keine Version gibt."""
        if technik:
            await self.technik(technik)
        if ergebnis and aktive_version:
            text = f"Version {aktive_version} bleibt aktiv. {text}"
        if self.art == "aendern" and self.linie:
            text = f"{text} {RETRY_HINWEIS}"
        aktiv = await asyncio.to_thread(speicher.produkt, self.user_id, self.produkt["id"])
        status = await asyncio.to_thread(speicher.status_fuer_version, self.produkt["id"], aktive_version)
        if aktiv and aktiv["status"] in {"building", "draft"}:
            aktiv = await asyncio.to_thread(speicher.produkt_aendern, self.user_id, self.produkt["id"], status=status)
        diagnose = self.diagnose(False, bericht)
        await self.technik(self.diagnose_text(diagnose))
        await self.versuch_abschliessen("abgelehnt" if kandidat else "gescheitert", text, kandidat=kandidat,
                                        bericht=bericht)
        endstatus = "needs_attention" if ergebnis and aktive_version else "failed"
        antwort = {"version": aktive_version, "status": endstatus, "text": text,
                   "warnungen": (warnungen or [])[:6], "kandidat": kandidat, "diagnose": diagnose}
        await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id, status=endstatus,
                                fehler="" if endstatus != "failed" else text,
                                ergebnis=antwort, verbrauch=self.verbrauch)
        await self.tokenstand()
        if endstatus == "failed":
            await self.melde("fehler", text=text, technik=technik[:1500], produkt=aktiv,
                             warnungen=(warnungen or [])[:6])
        else:
            await self.melde("fertig", **antwort, produkt=aktiv, verbrauch=self.verbrauch)
        await self.status(endstatus, text)

    async def beenden_ohne_version(self, text: str, aktive_version: int) -> None:
        """Verwerfen ohne neuen Wunsch: nichts zu bauen, die aktive Version bleibt."""
        aktiv = await asyncio.to_thread(speicher.produkt, self.user_id, self.produkt["id"])
        status = await asyncio.to_thread(speicher.status_fuer_version, self.produkt["id"], aktive_version)
        if aktiv and aktiv["status"] in {"building", "draft"}:
            aktiv = await asyncio.to_thread(speicher.produkt_aendern, self.user_id, self.produkt["id"], status=status)
        ergebnis = {"version": aktive_version, "status": "cancelled", "text": text, "warnungen": []}
        await asyncio.to_thread(speicher.job_aendern, self.auftrag.job_id, status="cancelled", fehler="",
                                ergebnis=ergebnis, verbrauch=self.verbrauch)
        await self.melde("fertig", **ergebnis, produkt=aktiv, verbrauch=self.verbrauch)
        await self.status("cancelled", text)
