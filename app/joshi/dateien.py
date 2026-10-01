# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Freigegebene Ordner: Asset-/Eingabeordner und Projekt-Workspace.

Zwei getrennte Wurzeln mit getrennten Rechten:

- **Eingaben** (technisch „inbound“, in der Oberfläche „Asset-/Eingabeordner“):
  Hier darf JOSHI Material *finden* — nur lesen, auflisten, auswählen.
- **Workspace**: Hier darf JOSHI an einem Projekt *arbeiten* — lesen und
  schreiben, aber nur innerhalb der freigegebenen Wurzel.

Eine generierte Anwendung bekommt davon nie etwas zu sehen: Sie läuft im
Sandkasten ohne Dateisystem. Nur JOSHI selbst nutzt diese Schicht, über
wenige, fest definierte Fähigkeiten (`FAEHIGKEITEN`) mit strengem Schema.

Jeder Pfad wird normalisiert und nach dem Auflösen von Symlinks gegen seine
Wurzel geprüft: keine absoluten Pfade, kein `..`, keine versteckten Dateien,
kein Weg aus der Wurzel hinaus. Wurzeln selbst müssen im Benutzerordner
liegen, dürfen nicht der Benutzerordner selbst, nicht `~/Library`, nicht
versteckt und nicht Teil der Mini-LLM-Daten sein — und sie dürfen sich nicht
gegenseitig enthalten.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database import DATA_DIR

PROJEKTORDNER = Path(__file__).resolve().parents[2]

ARTEN: dict[str, set[str]] = {
    "bild": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"},
    "daten": {".csv", ".tsv", ".json", ".xlsx", ".xls"},
    "dokument": {".pdf", ".docx", ".txt", ".md", ".rtf", ".html", ".htm"},
    "medien": {".mp4", ".mov", ".m4v", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
    "archiv": {".zip"},
}
MIME: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".json": "application/json", ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
    ".html": "text/html", ".htm": "text/html", ".rtf": "text/rtf", ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}
MAX_DATEIEN = 300
MAX_LESEN = 50 * 1024 * 1024


class Pfadfehler(ValueError):
    """Ein Pfad verlässt seine Wurzel oder ist als Wurzel nicht erlaubt."""


def art_von(name: str) -> str:
    endung = Path(name).suffix.lower()
    return next((art for art, endungen in ARTEN.items() if endung in endungen), "sonst")


def mime_von(name: str) -> str:
    return MIME.get(Path(name).suffix.lower(), "application/octet-stream")


def _innerhalb(pfad: Path, wurzel: Path) -> bool:
    return pfad == wurzel or wurzel in pfad.parents


def wurzel_pruefen(text: str, *, anlegen: bool = False, andere: Path | None = None) -> Path:
    """Prüft einen Ordner, bevor er Asset-/Eingabeordner oder Workspace werden darf."""
    roh = (text or "").strip()
    if not roh or "\x00" in roh:
        raise Pfadfehler("Bitte einen Ordner angeben.")
    pfad = Path(os.path.expanduser(roh))
    if not pfad.is_absolute():
        pfad = Path.home() / pfad
    pfad = Path(os.path.normpath(pfad))
    heim = Path.home().resolve()
    echt = pfad.resolve() if pfad.exists() else pfad.parent.resolve() / pfad.name
    volumes = Path("/Volumes").resolve()
    cloud_roots = (heim / "Library" / "Mobile Documents", heim / "Library" / "CloudStorage")
    im_heim = echt != heim and heim in echt.parents
    in_cloud = any(_innerhalb(echt, wurzel) and echt != wurzel for wurzel in cloud_roots)
    in_volume = echt != volumes and volumes in echt.parents
    if not (im_heim or in_cloud or in_volume):
        raise Pfadfehler("Der Ordner muss in deinem Benutzerordner, in iCloud/CloudStorage oder auf einem "
                         "eingehängten Laufwerk liegen.")
    if im_heim:
        teile = echt.relative_to(heim).parts
        if teile and teile[0] == "Library" and not in_cloud:
            raise Pfadfehler("System- und versteckte Ordner sind nicht erlaubt.")
    basis = volumes if in_volume else (next((wurzel for wurzel in cloud_roots if _innerhalb(echt, wurzel)), heim))
    try:
        relative_teile = echt.relative_to(basis).parts
    except ValueError:
        relative_teile = ()
    if any(teil.startswith(".") for teil in relative_teile):
        raise Pfadfehler("System- und versteckte Ordner sind nicht erlaubt.")
    for gesperrt in (DATA_DIR.resolve(), PROJEKTORDNER):
        if _innerhalb(echt, gesperrt) or _innerhalb(gesperrt, echt):
            raise Pfadfehler("Die Daten und Programmdateien von Mini LLM sind als Ordner nicht erlaubt.")
    if andere is not None and (_innerhalb(echt, andere.resolve()) or _innerhalb(andere.resolve(), echt)):
        raise Pfadfehler("Asset-/Eingabeordner und Workspace müssen getrennte Ordner sein — "
                         "keiner darf im anderen liegen.")
    if not echt.exists():
        if not anlegen:
            raise Pfadfehler("Diesen Ordner gibt es nicht.")
        echt.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not echt.is_dir():
        raise Pfadfehler("Das ist kein Ordner.")
    return echt


def vorhandene_wurzel(text: str) -> Path | None:
    """Der aufgelöste Pfad einer Wurzel für den Trennungsvergleich — ohne etwas anzulegen."""
    try:
        pfad = Path(os.path.normpath(Path(os.path.expanduser((text or "").strip())))) if text else None
    except (TypeError, ValueError):
        return None
    if pfad is None or not str(pfad).strip():
        return None
    if not pfad.is_absolute():
        pfad = Path.home() / pfad
    return pfad.resolve() if pfad.exists() else pfad.parent.resolve() / pfad.name


@dataclass
class Datei:
    name: str
    art: str
    groesse: int
    geaendert: float
    pfad: Path

    def als_dict(self) -> dict[str, Any]:
        return {"name": self.name, "art": self.art, "groesse": self.groesse, "geaendert": round(self.geaendert, 3)}


def pruefsumme(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


class Wurzel:
    """Eine freigegebene Wurzel. Alle Pfade sind relativ und bleiben darin."""

    def __init__(self, pfad: Path, *, schreibbar: bool, name: str) -> None:
        self.pfad = pfad.resolve()
        self.schreibbar = schreibbar
        self.name = name

    def aufloesen(self, relativ: str) -> Path:
        roh = str(relativ or "")
        if not roh or "\x00" in roh or "\\" in roh or roh.startswith(("/", "~")):
            raise Pfadfehler(f"Ungültiger Pfad: {roh[:80]!r}")
        teile = Path(roh).parts
        if any(teil in {"..", "."} or teil.startswith(".") for teil in teile):
            raise Pfadfehler(f"Ungültiger Pfad: {roh[:80]!r}")
        ziel = (self.pfad / roh).resolve()
        if not _innerhalb(ziel, self.pfad) or ziel == self.pfad:
            raise Pfadfehler(f"Der Pfad verlässt den {self.name}.")
        return ziel

    # ------------------------------------------------------------- lesen
    def liste(self, grenze: int = MAX_DATEIEN) -> list[Datei]:
        """Dateien direkt in der Wurzel — keine Unterordner, nichts Verstecktes."""
        dateien: list[Datei] = []
        try:
            eintraege = sorted(os.scandir(self.pfad), key=lambda e: e.name.lower())
        except OSError:
            return []
        for eintrag in eintraege:
            if eintrag.name.startswith(".") or len(dateien) >= grenze:
                continue
            try:
                echt = Path(eintrag.path).resolve()
                if not _innerhalb(echt, self.pfad) or not echt.is_file():
                    continue          # Symlink hinaus oder kein normales Dokument
                stat = echt.stat()
            except OSError:
                continue
            dateien.append(Datei(eintrag.name, art_von(eintrag.name), stat.st_size, stat.st_mtime, echt))
        return dateien

    def lesen(self, relativ: str, grenze: int = MAX_LESEN) -> bytes:
        ziel = self.aufloesen(relativ)
        if not ziel.is_file():
            raise FileNotFoundError(relativ)
        if ziel.stat().st_size > grenze:
            raise Pfadfehler(f"{relativ} ist größer als {grenze // 1024 // 1024} MB.")
        return ziel.read_bytes()

    def existiert(self, relativ: str) -> bool:
        try:
            return self.aufloesen(relativ).exists()
        except Pfadfehler:
            return False

    # ---------------------------------------------------------- schreiben
    def _schreibrecht(self) -> None:
        if not self.schreibbar:
            raise PermissionError(f"Der {self.name} ist schreibgeschützt.")

    def ordner(self, relativ: str) -> Path:
        self._schreibrecht()
        ziel = self.aufloesen(relativ)
        ziel.mkdir(parents=True, exist_ok=True)
        if not _innerhalb(ziel.resolve(), self.pfad):
            raise Pfadfehler(f"Der Pfad verlässt den {self.name}.")
        return ziel

    def schreiben(self, relativ: str, daten: bytes | str) -> Path:
        """Atomar schreiben: erst eine Zwischendatei, dann austauschen."""
        self._schreibrecht()
        ziel = self.aufloesen(relativ)
        if ziel.is_symlink():
            raise Pfadfehler("Über einen Symlink wird nicht geschrieben.")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if not _innerhalb(ziel.parent.resolve(), self.pfad):
            raise Pfadfehler(f"Der Pfad verlässt den {self.name}.")
        inhalt = daten.encode("utf-8") if isinstance(daten, str) else daten
        griff, zwischen = tempfile.mkstemp(prefix=".joshi-", dir=ziel.parent)
        try:
            with os.fdopen(griff, "wb") as datei:
                datei.write(inhalt)
            os.replace(zwischen, ziel)
        except BaseException:
            Path(zwischen).unlink(missing_ok=True)
            raise
        return ziel

    def loeschen(self, relativ: str) -> bool:
        self._schreibrecht()
        ziel = self.aufloesen(relativ)
        if ziel.is_file():
            ziel.unlink()
            return True
        return False


# Die internen Host-Fähigkeiten — fest definiert, mit Schema. Sie sind kein
# RPC für generierte Anwendungen; nur JOSHI selbst ruft sie auf.
FAEHIGKEITEN: dict[str, tuple[str, set[str]]] = {
    "inbound.list": ("eingaben", set()),
    "inbound.read": ("eingaben", {"pfad"}),
    "workspace.list": ("workspace", set()),
    "workspace.read": ("workspace", {"pfad"}),
    "workspace.write": ("workspace", {"pfad", "daten"}),
    "workspace.mkdir": ("workspace", {"pfad"}),
    "workspace.copy": ("workspace", {"quelle", "pfad"}),
    "workspace.delete": ("workspace", {"pfad"}),
}


def ausfuehren(wurzeln: dict[str, Wurzel], name: str, argumente: dict[str, Any]) -> Any:
    """Führt eine Fähigkeit aus — nur bekannte Namen, nur die erlaubten Argumente."""
    if name not in FAEHIGKEITEN:
        raise PermissionError(f"Unbekannte Fähigkeit: {name}")
    bereich, erlaubt = FAEHIGKEITEN[name]
    if set(argumente) != erlaubt:
        raise ValueError(f"{name} erwartet genau: {', '.join(sorted(erlaubt)) or 'nichts'}")
    wurzel = wurzeln.get(bereich)
    if wurzel is None:
        raise PermissionError(f"Der {'Workspace' if bereich == 'workspace' else 'Asset-/Eingabeordner'} ist nicht freigegeben.")
    aktion = name.split(".", 1)[1]
    if aktion == "list":
        return [d.als_dict() for d in wurzel.liste()]
    if aktion == "read":
        return wurzel.lesen(str(argumente["pfad"]))
    if aktion == "write":
        return str(wurzel.schreiben(str(argumente["pfad"]), argumente["daten"]).relative_to(wurzel.pfad))
    if aktion == "mkdir":
        return str(wurzel.ordner(str(argumente["pfad"])).relative_to(wurzel.pfad))
    if aktion == "copy":
        quelle = wurzeln.get("eingaben")
        if quelle is None:
            raise PermissionError("Der Asset-/Eingabeordner ist nicht freigegeben.")
        daten = quelle.lesen(str(argumente["quelle"]))
        return str(wurzel.schreiben(str(argumente["pfad"]), daten).relative_to(wurzel.pfad))
    if aktion == "delete":
        return wurzel.loeschen(str(argumente["pfad"]))
    raise PermissionError(name)
