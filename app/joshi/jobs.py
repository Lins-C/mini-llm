# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Hintergrundaufträge: Ein JOSHI-Auftrag läuft weiter, auch wenn niemand zusieht.

Der Browser hört nur zu (NDJSON-Strom ab einer Ereignisnummer) und kann sich
jederzeit neu verbinden. Wechselt der Nutzer zurück in den Chat oder schließt
er das Fenster, läuft der Auftrag unverändert weiter; sein Stand liegt bei
jedem Phasenwechsel zusätzlich in der Datenbank.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from app.joshi import speicher

LOGGER = logging.getLogger("mini-llm.joshi")
# Diese Ereignisse kommen im Sekundentakt; gespeichert wird nur das letzte.
FLUECHTIG = {"fortschritt", "tokens"}


def zeile(art: str, **daten: Any) -> bytes:
    return (json.dumps({"type": art, **daten}, ensure_ascii=False) + "\n").encode()


class Auftrag:
    def __init__(self, job_id: str, produkt_id: str, user_id: str) -> None:
        self.job_id = job_id
        self.produkt_id = produkt_id
        self.user_id = user_id
        self.ereignisse: list[bytes] = []
        self.status = "queued"
        self.fortschritt: dict[str, Any] = {}
        self.tokens: dict[str, Any] = {}
        self.beendet = False
        self.abbruch = asyncio.Event()
        self.bedingung = asyncio.Condition()
        self.task: asyncio.Task[None] | None = None
        self.geaendert = time.time()

    async def melde(self, art: str, **daten: Any) -> None:
        if isinstance(daten.get("tokens"), (int, float)):
            # Der Stand wird sowohl live im Snapshot als auch beim Abbruch in
            # die Datenbank übernommen. Nicht auf eine bekannte Feldliste
            # kürzen: Providerwerte und Schätzungen müssen unterscheidbar
            # bleiben, auch wenn die Pipeline weitere Usage-Felder ergänzt.
            self.tokens = dict(daten)
        roh = zeile(art, **daten)
        if art == "status":
            self.status = str(daten.get("status") or self.status)
        if art in {"schritt", "status", "fortschritt"}:
            self.fortschritt = {k: v for k, v in daten.items() if k in {"schritt", "zustand", "text", "status", "zeichen"}}
        self.geaendert = time.time()
        async with self.bedingung:
            self.ereignisse.append(roh)
            self.bedingung.notify_all()
        if art in {"status", "schritt"}:
            await asyncio.to_thread(speicher.job_aendern, self.job_id, status=self.status, fortschritt=self.fortschritt)

    def gespeicherte_ereignisse(self) -> list[dict[str, Any]]:
        ergebnis: list[dict[str, Any]] = []
        for roh in self.ereignisse:
            try:
                ereignis = json.loads(roh)
            except json.JSONDecodeError:
                continue
            art = ereignis.get("type")
            if art in FLUECHTIG and ergebnis and ergebnis[-1].get("type") == art:
                ergebnis[-1] = ereignis
            else:
                ergebnis.append(ereignis)
        return ergebnis[-200:]

    async def beenden(self) -> None:
        self.beendet = True
        self.geaendert = time.time()
        async with self.bedingung:
            self.bedingung.notify_all()

    def schnappschuss(self) -> dict[str, Any]:
        return {"job": self.job_id, "produkt": self.produkt_id, "status": self.status,
                "fortschritt": self.fortschritt, "tokens": self.tokens,
                "ereignisse": len(self.ereignisse), "beendet": self.beendet}


Ablauf = Callable[[Auftrag], Awaitable[None]]


class Auftragsverwaltung:
    def __init__(self) -> None:
        self.auftraege: dict[str, Auftrag] = {}
        self.herunterfahren = False

    def laufend_fuer(self, produkt_id: str) -> Auftrag | None:
        for auftrag in self.auftraege.values():
            if auftrag.produkt_id == produkt_id and not auftrag.beendet:
                return auftrag
        return None

    def starten(self, auftrag: Auftrag, ablauf: Ablauf) -> None:
        if self.laufend_fuer(auftrag.produkt_id):
            raise ValueError("Für dieses Produkt läuft bereits ein Auftrag.")
        grenze = time.time() - 6 * 3600
        for kennung in [k for k, a in self.auftraege.items() if a.beendet and a.geaendert < grenze]:
            self.auftraege.pop(kennung, None)
        self.auftraege[auftrag.job_id] = auftrag
        auftrag.task = asyncio.create_task(self._laufen(auftrag, ablauf), name=f"joshi-{auftrag.job_id}")

    async def _laufen(self, auftrag: Auftrag, ablauf: Ablauf) -> None:
        try:
            await ablauf(auftrag)
        except asyncio.CancelledError:
            if self.herunterfahren or not auftrag.abbruch.is_set():
                await self._endstand(auftrag, "failed", speicher.NEUSTART_TEXT)
                raise
            await self._endstand(auftrag, "cancelled", "Abgebrochen. Die letzte fertige Version bleibt erhalten.")
        except Exception as fehler:  # noqa: BLE001 – der Auftrag darf nie still sterben
            LOGGER.exception("JOSHI-Auftrag %s fehlgeschlagen", auftrag.job_id)
            await self._endstand(auftrag, "failed", "JOSHI ist auf einen unerwarteten Fehler gestoßen.",
                                 technik=f"{type(fehler).__name__}: {fehler}")
        finally:
            try:
                await asyncio.to_thread(speicher.job_aendern, auftrag.job_id,
                                        ereignisse=auftrag.gespeicherte_ereignisse())
            except Exception:  # noqa: BLE001
                LOGGER.exception("JOSHI-Ereignisse nicht gespeichert")
            await auftrag.beenden()

    async def _endstand(self, auftrag: Auftrag, status: str, text: str, technik: str = "") -> None:
        if auftrag.status in speicher.ENDSTATUS:
            return
        try:
            if auftrag.tokens:
                await auftrag.melde("tokens", **{**auftrag.tokens, "laufend": False})
                job = await asyncio.to_thread(speicher.job, auftrag.user_id, auftrag.job_id)
                if job:
                    await asyncio.to_thread(speicher.job_aendern, auftrag.job_id,
                                            verbrauch={**job["verbrauch"], "tokenstand": auftrag.tokens})
            if status == "failed":
                await auftrag.melde("fehler", text=text, technik=technik)
            await auftrag.melde("status", status=status, text=text)
            await asyncio.to_thread(speicher.job_aendern, auftrag.job_id, status=status, fehler=text)
            produkt = await asyncio.to_thread(speicher.produkt, auftrag.user_id, auftrag.produkt_id)
            if produkt and produkt["status"] == "building":
                produkt_status = await asyncio.to_thread(
                    speicher.status_fuer_version, produkt["id"], produkt["version"])
                await asyncio.to_thread(speicher.produkt_aendern, auftrag.user_id, auftrag.produkt_id,
                                        status=produkt_status)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JOSHI-Endstand nicht gespeichert")

    def holen(self, job_id: str, user_id: str) -> Auftrag | None:
        auftrag = self.auftraege.get(job_id)
        return auftrag if auftrag and auftrag.user_id == user_id else None

    def abbrechen(self, job_id: str, user_id: str) -> bool:
        auftrag = self.holen(job_id, user_id)
        if not auftrag or auftrag.beendet:
            return False
        auftrag.abbruch.set()
        if auftrag.task and not auftrag.task.done():
            auftrag.task.cancel()
        return True

    async def abonnieren(self, job_id: str, user_id: str, ab: int = 0) -> AsyncIterator[bytes]:
        auftrag = self.holen(job_id, user_id)
        if auftrag is None:
            return
        index = max(0, ab)
        while True:
            async with auftrag.bedingung:
                while index >= len(auftrag.ereignisse) and not auftrag.beendet:
                    await auftrag.bedingung.wait()
                neu = auftrag.ereignisse[index:]
                fertig = auftrag.beendet
            for roh in neu:
                index += 1
                yield roh
            if fertig and index >= len(auftrag.ereignisse):
                return

    def aktive(self, user_id: str) -> list[Auftrag]:
        return [a for a in self.auftraege.values() if a.user_id == user_id and not a.beendet]

    async def alle_beenden(self) -> None:
        self.herunterfahren = True
        tasks = [a.task for a in self.auftraege.values() if a.task and not a.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


verwaltung = Auftragsverwaltung()
