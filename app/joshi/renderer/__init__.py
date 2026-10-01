# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""WebKit-Renderer für JOSHI.

Ein kleines Swift-Programm (joshi_render.swift) lädt eine HTML-Datei in
WebKit — dieselbe Engine wie Safari —, führt ein Prüfskript aus und erzeugt
auf Wunsch ein Gesamtbild und ein PDF. Es wird beim ersten Bedarf mit den
Command Line Tools übersetzt und nach dem Quelltext-Hash zwischengespeichert.

Fehlt swiftc (anderer Rechner, keine Command Line Tools), ist der Renderer
nicht verfügbar: JOSHI prüft dann nur statisch und sagt das auch.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("mini-llm.joshi")
ORDNER = Path(__file__).resolve().parent
QUELLE = ORDNER / "joshi_render.swift"
PRUEFUNG_JS = (ORDNER / "pruefung.js").read_text(encoding="utf-8")
INHALT_JS = (ORDNER / "inhalt.js").read_text(encoding="utf-8")
SZENARIO_JS = (ORDNER / "szenario.js").read_text(encoding="utf-8")
ZWISCHENSPEICHER = Path(os.path.expanduser(os.getenv(
    "JOSHI_RENDERER_CACHE", str(Path.home() / "Library" / "Caches" / "MiniLLM"),
)))
_zustand: dict[str, Any] = {"pfad": None, "fehler": "", "fehler_zeit": 0.0}


_sperren: dict[int, tuple[asyncio.Semaphore, asyncio.Lock]] = {}


def _sperre() -> tuple[asyncio.Semaphore, asyncio.Lock]:
    """Höchstens zwei Browserprozesse gleichzeitig — der Mac mini rechnet
    nebenbei noch ein lokales Modell. Je Ereignisschleife eigene Sperren."""
    schleife = id(asyncio.get_running_loop())
    if schleife not in _sperren:
        _sperren.clear()
        _sperren[schleife] = (asyncio.Semaphore(2), asyncio.Lock())
    return _sperren[schleife]


def _quellhash() -> str:
    return hashlib.sha256(QUELLE.read_bytes()).hexdigest()[:12]


def _ziel() -> Path:
    return ZWISCHENSPEICHER / f"joshi-render-{_quellhash()}"


def status() -> dict[str, Any]:
    ausdruecklich = os.getenv("JOSHI_RENDERER", "").strip()
    if ausdruecklich.lower() in {"aus", "off", "0"}:
        return {"verfuegbar": False, "grund": "abgeschaltet"}
    ziel = Path(ausdruecklich) if ausdruecklich else _ziel()
    if ziel.is_file() and os.access(ziel, os.X_OK):
        return {"verfuegbar": True, "pfad": str(ziel)}
    return {
        "verfuegbar": False,
        "grund": _zustand["fehler"] or "noch nicht übersetzt",
        "uebersetzbar": bool(shutil.which("swiftc")),
    }


async def programm() -> Path | None:
    """Pfad zum Renderer; übersetzt ihn beim ersten Aufruf (rund 30 Sekunden)."""
    ausdruecklich = os.getenv("JOSHI_RENDERER", "").strip()
    if ausdruecklich.lower() in {"aus", "off", "0"}:
        return None
    if ausdruecklich:
        pfad = Path(ausdruecklich)
        return pfad if pfad.is_file() else None
    ziel = _ziel()
    if ziel.is_file():
        return ziel
    async with _sperre()[1]:
        if ziel.is_file():
            return ziel
        if _zustand["fehler"] and time.time() - _zustand["fehler_zeit"] < 600:
            return None
        swiftc = shutil.which("swiftc") or ("/usr/bin/swiftc" if Path("/usr/bin/swiftc").exists() else None)
        if not swiftc:
            _zustand.update(fehler="swiftc fehlt (Xcode Command Line Tools)", fehler_zeit=time.time())
            return None
        ZWISCHENSPEICHER.mkdir(parents=True, exist_ok=True)
        zwischen = ziel.with_name(ziel.name + f".{os.getpid()}.tmp")
        LOGGER.info("JOSHI-Renderer wird übersetzt …")
        prozess = await asyncio.create_subprocess_exec(
            swiftc, "-O", "-swift-version", "5", str(QUELLE), "-o", str(zwischen),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, fehler = await asyncio.wait_for(prozess.communicate(), timeout=420)
        except asyncio.TimeoutError:
            prozess.kill()
            await prozess.wait()
            zwischen.unlink(missing_ok=True)
            _zustand.update(fehler="Übersetzen dauerte zu lange", fehler_zeit=time.time())
            return None
        except asyncio.CancelledError:
            prozess.kill()
            await prozess.wait()
            zwischen.unlink(missing_ok=True)
            raise
        if prozess.returncode != 0 or not zwischen.is_file():
            zwischen.unlink(missing_ok=True)
            _zustand.update(fehler=fehler.decode(errors="replace")[-600:] or "swiftc fehlgeschlagen",
                            fehler_zeit=time.time())
            LOGGER.warning("JOSHI-Renderer nicht übersetzbar: %s", _zustand["fehler"])
            return None
        os.replace(zwischen, ziel)
        _zustand.update(fehler="", fehler_zeit=0.0)
        for alt in ZWISCHENSPEICHER.glob("joshi-render-*"):
            if alt != ziel and not alt.name.endswith(".tmp"):
                alt.unlink(missing_ok=True)
        return ziel


async def selbsttest() -> str:
    """Übersetzt bei Bedarf und lädt eine Mini-Seite — für das Startprotokoll."""
    beginn = time.monotonic()
    try:
        messung = await rendern(
            "<!DOCTYPE html><html><head><title>t</title></head><body><button onclick=\"this.textContent='ja'\">x</button></body></html>",
            probe=INHALT_JS, timeout=15)
    except RendererFehlt as fehlt:
        return f"JOSHI-Renderer nicht verfügbar: {fehlt} — JOSHI prüft nur statisch."
    if not messung.ok:
        return f"JOSHI-Renderer startet nicht: {messung.fehler}"
    return f"JOSHI-Renderer bereit ({time.monotonic() - beginn:.1f} s)."


@dataclass
class Messung:
    ok: bool
    geladen: bool = False
    fehler: str = ""
    probe: dict[str, Any] | None = None
    dialoge: list[str] = field(default_factory=list)
    navigation: list[str] = field(default_factory=list)
    png: bytes | None = None
    pdf: bytes | None = None
    seiten_pdf: bytes | None = None
    seitenhoehe: float = 0
    abgeschnitten: bool = False
    dauer: float = 0.0
    roh: dict[str, Any] = field(default_factory=dict)


class RendererFehlt(RuntimeError):
    pass


async def rendern(
    dokument: str,
    *,
    probe: str | None = None,
    breite: int = 1280,
    hoehe: int = 900,
    bild: bool = False,
    pdf: bool = False,
    seiten_pdf: bool = False,
    skala: float = 2.0,
    timeout: float = 25.0,
    warten: float = 0.6,
) -> Messung:
    """Lädt ein fertiges Laufzeit-Dokument in WebKit und misst es."""
    pfad = await programm()
    if pfad is None:
        raise RendererFehlt(status().get("grund") or "Renderer nicht verfügbar")
    async with _sperre()[0]:
        with tempfile.TemporaryDirectory(prefix="joshi-") as ordner:
            basis = Path(ordner)
            (basis / "seite.html").write_text(dokument, encoding="utf-8")
            argumente = [
                str(pfad), "--html", str(basis / "seite.html"),
                "--breite", str(breite), "--hoehe", str(hoehe),
                "--timeout", str(timeout), "--warten", str(warten), "--skala", str(skala),
            ]
            if probe:
                (basis / "probe.js").write_text(probe, encoding="utf-8")
                argumente += ["--probe", str(basis / "probe.js")]
            if bild:
                argumente += ["--png", str(basis / "bild.png")]
            if pdf:
                argumente += ["--pdf", str(basis / "seite.pdf")]
            if seiten_pdf:
                argumente += ["--seiten-pdf", str(basis / "druck.pdf")]
            beginn = time.monotonic()
            prozess = await asyncio.create_subprocess_exec(
                *argumente, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                ausgabe, _ = await asyncio.wait_for(prozess.communicate(), timeout=timeout + 20)
            except asyncio.TimeoutError:
                prozess.kill()
                await prozess.wait()
                return Messung(ok=False, fehler="Der Renderer antwortete nicht (Zeitüberschreitung).",
                               dauer=time.monotonic() - beginn)
            except asyncio.CancelledError:
                prozess.kill()
                await prozess.wait()
                raise
            dauer = time.monotonic() - beginn
            zeile = ausgabe.decode(errors="replace").strip().splitlines()
            try:
                roh = json.loads(zeile[-1]) if zeile else {}
            except json.JSONDecodeError:
                roh = {}
            if not roh:
                return Messung(ok=False, fehler="Der Renderer lieferte kein Ergebnis.", dauer=dauer)

            def lies(name: str) -> bytes | None:
                datei = basis / name
                return datei.read_bytes() if datei.is_file() and datei.stat().st_size else None

            return Messung(
                ok=bool(roh.get("ok")),
                geladen=bool(roh.get("geladen")),
                fehler=str(roh.get("fehler") or roh.get("probeFehler") or ""),
                probe=roh.get("probe") if isinstance(roh.get("probe"), dict) else None,
                dialoge=[str(d) for d in roh.get("dialoge") or []],
                navigation=[str(n) for n in roh.get("navigation") or []],
                png=lies("bild.png") if bild else None,
                pdf=lies("seite.pdf") if pdf else None,
                seiten_pdf=lies("druck.pdf") if seiten_pdf else None,
                seitenhoehe=float(roh.get("seitenhoehe") or 0),
                abgeschnitten=bool(roh.get("abgeschnitten")),
                dauer=dauer,
                roh={k: v for k, v in roh.items() if k != "probe"},
            )


def pruefskript(fokus: list[str] | None = None) -> str:
    """Gliederung vor der Bedienung, dann die Bedienprobe.

    `fokus` sind Wörter aus dem Abnahmevertrag: Knöpfe, deren Beschriftung,
    Beschreibung oder Klasse dazu passt, klickt die Probe zuerst.
    """
    worte = json.dumps([str(w)[:40] for w in (fokus or [])[:40]], ensure_ascii=True).replace("</", "<\\/")
    return (f"const __fokus = {worte};\n"
            f"const __vorher = await (async () => {{\n{INHALT_JS}\n}})().then((t) => JSON.parse(t));\n{PRUEFUNG_JS}")


def inhaltsskript() -> str:
    return INHALT_JS


def szenarioskript(auftrag: dict[str, Any]) -> str:
    """Aktionsproben oder eine Szenario-Phase. Der Auftrag ist reines JSON."""
    daten = json.dumps(auftrag, ensure_ascii=True).replace("</", "<\\/")
    return f"const __auftrag = {daten};\n{SZENARIO_JS}"
