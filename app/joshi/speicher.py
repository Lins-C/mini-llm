# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Dauerhafte Ablage für JOSHI: Produkte, Versionen, Aufträge, Bilder.

Eigene Tabellen in derselben SQLite-Datenbank wie der Chat — nichts davon
wird in Chat-Daten gemischt. Versionen liegen komprimiert vor (HTML schrumpft
etwa auf ein Fünftel), Bilder als Dateien im Datenordner.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import shutil
import time
import uuid
import zlib
from pathlib import Path
from typing import Any

from app.database import DATA_DIR, connect

ORDNER = DATA_DIR / "joshi"
AKTIVE_STATUS = {"queued", "understanding", "building", "validating", "repairing"}
# needs_attention is terminal for the current job, even though the product
# remains explicitly unavailable as a validated READY application.
ENDSTATUS = {"ready", "needs_attention", "failed", "cancelled"}
MAX_ZUSTAND_BYTES = 256 * 1024
MAX_BILD_BYTES = 6 * 1024 * 1024
TEMPORAER_TAGE = 30


def tabellen_anlegen() -> None:
    with connect() as verbindung:
        verbindung.executescript(
            """
            CREATE TABLE IF NOT EXISTS joshi_products (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                intent TEXT NOT NULL,
                status TEXT NOT NULL,
                current_version INTEGER NOT NULL DEFAULT 0,
                understanding TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT '{}',
                kept INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS joshi_products_user ON joshi_products(user_id, updated_at);

            CREATE TABLE IF NOT EXISTS joshi_versions (
                product_id TEXT NOT NULL REFERENCES joshi_products(id) ON DELETE CASCADE,
                number INTEGER NOT NULL,
                html BLOB NOT NULL,
                change_request TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                validation TEXT NOT NULL DEFAULT '{}',
                model TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                PRIMARY KEY (product_id, number)
            );

            CREATE TABLE IF NOT EXISTS joshi_jobs (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES joshi_products(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                input TEXT NOT NULL DEFAULT '{}',
                progress TEXT NOT NULL DEFAULT '{}',
                events TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT '{}',
                model TEXT NOT NULL DEFAULT '',
                usage TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                finished_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS joshi_jobs_product ON joshi_jobs(product_id, created_at);
            CREATE INDEX IF NOT EXISTS joshi_jobs_user ON joshi_jobs(user_id, status);

            -- Änderungslinie: Ein Änderungsauftrag behält seinen ursprünglichen
            -- Wunsch und seinen Abnahmevertrag über alle Versuche hinweg.
            CREATE TABLE IF NOT EXISTS joshi_changes (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES joshi_products(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                request TEXT NOT NULL,
                additions TEXT NOT NULL DEFAULT '[]',
                contract TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                base_version INTEGER NOT NULL DEFAULT 0,
                attempts TEXT NOT NULL DEFAULT '[]',
                plan TEXT NOT NULL DEFAULT '{}',
                checkpoint BLOB,
                checkpoint_stage INTEGER NOT NULL DEFAULT 0,
                checkpoint_base INTEGER NOT NULL DEFAULT 0,
                checkpoint_outline TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS joshi_changes_product ON joshi_changes(product_id, created_at);

            -- Einstellungen je Nutzer: Asset-/Eingabeordner und Workspace.
            CREATE TABLE IF NOT EXISTS joshi_settings (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL DEFAULT '{}',
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS joshi_assets (
                product_id TEXT NOT NULL REFERENCES joshi_products(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (product_id, name)
            );
            """
        )


def _jetzt() -> int:
    return int(time.time())


def _json(wert: Any) -> str:
    return json.dumps(wert, ensure_ascii=False)


def _lies(text: str | None, standard: Any) -> Any:
    try:
        wert = json.loads(text or "")
    except (TypeError, json.JSONDecodeError):
        return standard
    return wert if isinstance(wert, type(standard)) else standard


# ------------------------------------------------------------------ Produkte
def _produkt(zeile: Any) -> dict[str, Any]:
    return {
        "id": zeile["id"],
        "titel": zeile["title"],
        "auftrag": zeile["intent"],
        "status": zeile["status"],
        "version": zeile["current_version"],
        "verstaendnis": _lies(zeile["understanding"], {}),
        "zustand": _lies(zeile["state"], {}),
        "quelle": _lies(zeile["source"], {}),
        "behalten": bool(zeile["kept"]),
        "erstellt": zeile["created_at"],
        "geaendert": zeile["updated_at"],
    }


def produkt_anlegen(user_id: str, titel: str, auftrag: str, quelle: dict[str, Any] | None = None) -> dict[str, Any]:
    kennung = uuid.uuid4().hex
    jetzt = _jetzt()
    with connect() as verbindung:
        verbindung.execute(
            "INSERT INTO joshi_products (id, user_id, title, intent, status, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'draft', ?, ?, ?)",
            (kennung, user_id, titel[:120] or "Neues Produkt", auftrag[:20000], _json(quelle or {}), jetzt, jetzt),
        )
    return produkt(user_id, kennung) or {}


def produkt(user_id: str, produkt_id: str) -> dict[str, Any] | None:
    with connect() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM joshi_products WHERE id = ? AND user_id = ?", (produkt_id, user_id),
        ).fetchone()
    return _produkt(zeile) if zeile else None


def produkte(user_id: str, grenze: int = 200) -> list[dict[str, Any]]:
    with connect() as verbindung:
        zeilen = verbindung.execute(
            "SELECT * FROM joshi_products WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?", (user_id, grenze),
        ).fetchall()
    return [_produkt(z) for z in zeilen]


_SPALTEN = {
    "titel": ("title", lambda w: str(w)[:120]),
    "status": ("status", str),
    "version": ("current_version", int),
    "verstaendnis": ("understanding", _json),
    "zustand": ("state", _json),
    "behalten": ("kept", lambda w: 1 if w else 0),
    "quelle": ("source", _json),
}


def produkt_aendern(user_id: str, produkt_id: str, **felder: Any) -> dict[str, Any] | None:
    zuweisungen, werte = [], []
    for name, wert in felder.items():
        spalte, umwandeln = _SPALTEN[name]
        zuweisungen.append(f"{spalte} = ?")
        werte.append(umwandeln(wert))
    zuweisungen.append("updated_at = ?")
    werte.append(_jetzt())
    with connect() as verbindung:
        verbindung.execute(
            f"UPDATE joshi_products SET {', '.join(zuweisungen)} WHERE id = ? AND user_id = ?",
            (*werte, produkt_id, user_id),
        )
    return produkt(user_id, produkt_id)


def zustand_speichern(user_id: str, produkt_id: str, zustand: dict[str, Any]) -> bool:
    text = _json(zustand)
    if len(text.encode()) > MAX_ZUSTAND_BYTES:
        return False
    with connect() as verbindung:
        # Kein updated_at: Tippen in der Anwendung soll die Liste nicht umsortieren.
        verbindung.execute("UPDATE joshi_products SET state = ? WHERE id = ? AND user_id = ?",
                           (text, produkt_id, user_id))
    return True


def produkt_loeschen(user_id: str, produkt_id: str) -> bool:
    with connect() as verbindung:
        geloescht = verbindung.execute(
            "DELETE FROM joshi_products WHERE id = ? AND user_id = ?", (produkt_id, user_id),
        ).rowcount
    if geloescht:
        shutil.rmtree(ORDNER / produkt_id, ignore_errors=True)
    return bool(geloescht)


# ------------------------------------------------------------------ Versionen
def version_anlegen(produkt_id: str, html: str, aenderung: str, *, zusammenfassung: str = "",
                    pruefung: dict[str, Any] | None = None, modell: str = "") -> int:
    """Legt eine Version an, ohne sie zu aktivieren (Kandidat)."""
    return version_festschreiben(produkt_id, html, aenderung, zusammenfassung=zusammenfassung,
                                 pruefung=pruefung, modell=modell)[0]


def version_festschreiben(produkt_id: str, html: str, aenderung: str, *, zusammenfassung: str = "",
                          pruefung: dict[str, Any] | None = None, modell: str = "",
                          aktivieren: bool = False, status: str = "") -> tuple[int, bool]:
    """Schreibt einen Kandidaten und macht ihn auf Wunsch in einem Zug aktiv.

    Beides in derselben Transaktion: Eine Änderung darf die laufende Version
    nie halb ersetzen. Rückgabe: (Versionsnummer, aktiviert).
    """
    jetzt = _jetzt()
    with connect() as verbindung:
        zeile = verbindung.execute(
            "SELECT COALESCE(MAX(number), 0) AS n FROM joshi_versions WHERE product_id = ?", (produkt_id,),
        ).fetchone()
        nummer = int(zeile["n"]) + 1
        verbindung.execute(
            "INSERT INTO joshi_versions (product_id, number, html, change_request, summary, validation, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (produkt_id, nummer, zlib.compress(html.encode("utf-8"), 6), aenderung[:4000], zusammenfassung[:2000],
             _json(pruefung or {}), modell[:200], jetzt),
        )
        if aktivieren:
            verbindung.execute(
                "UPDATE joshi_products SET current_version = ?, status = ?, updated_at = ? WHERE id = ?",
                (nummer, status or "ready", jetzt, produkt_id),
            )
    return nummer, aktivieren


def recovery_commit(user_id: str, produkt_id: str, aenderung_id: str, job_id: str, *,
                    basis: int, html: str, aenderung: str, zusammenfassung: str,
                    pruefung: dict[str, Any], modell: str, versuch: dict[str, Any],
                    eingabe: dict[str, Any], ergebnis: dict[str, Any],
                    verbrauch: dict[str, Any], ereignisse: list[dict[str, Any]] | None = None) -> int:
    """Schreibt eine bereits separat nachgeprüfte Recovery-Fassung atomar.

    Dieser Pfad ist für eine technische Nachprüfung eines vorhandenen
    Kandidaten gedacht: Version, Produktstatus, Änderungszeile und der
    erfolgreiche Auftrag werden gemeinsam geschrieben. Ein Absturz kann damit
    keine halb aktivierte Version hinterlassen.
    """
    jetzt = _jetzt()
    with connect() as verbindung:
        produkt = verbindung.execute(
            "SELECT current_version, user_id FROM joshi_products WHERE id = ? AND user_id = ?",
            (produkt_id, user_id),
        ).fetchone()
        if not produkt or int(produkt["current_version"]) != int(basis):
            raise ValueError("Das Produkt hat sich seit der Nachprüfung geändert.")
        linie = verbindung.execute(
            "SELECT product_id, user_id, status, attempts FROM joshi_changes WHERE id = ?",
            (aenderung_id,),
        ).fetchone()
        if not linie or linie["product_id"] != produkt_id or linie["user_id"] != user_id \
                or linie["status"] not in {"open", "abgebrochen"}:
            raise ValueError("Der Änderungsauftrag ist nicht mehr offen.")
        nummer = int(verbindung.execute(
            "SELECT COALESCE(MAX(number), 0) AS n FROM joshi_versions WHERE product_id = ?", (produkt_id,)
        ).fetchone()["n"]) + 1
        verbindung.execute(
            "INSERT INTO joshi_versions (product_id, number, html, change_request, summary, validation, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (produkt_id, nummer, zlib.compress(html.encode("utf-8"), 6), aenderung[:4000],
             zusammenfassung[:2000], _json(pruefung), modell[:200], jetzt),
        )
        verbindung.execute(
            "UPDATE joshi_products SET current_version = ?, status = 'ready', updated_at = ? WHERE id = ? AND user_id = ?",
            (nummer, jetzt, produkt_id, user_id),
        )
        versuche = _lies(linie["attempts"], [])
        if not isinstance(versuche, list):
            versuche = []
        versuche.append(versuch)
        verbindung.execute(
            "UPDATE joshi_changes SET status = 'umgesetzt', attempts = ?, checkpoint = NULL, "
            "checkpoint_stage = 0, checkpoint_base = 0, checkpoint_outline = '{}', updated_at = ? WHERE id = ?",
            (_json(versuche), jetzt, aenderung_id),
        )
        verbindung.execute(
            "INSERT INTO joshi_jobs (id, product_id, user_id, kind, status, input, progress, events, error, result, model, usage, created_at, updated_at, finished_at) "
            "VALUES (?, ?, ?, 'recovery', 'ready', ?, ?, ?, '', ?, ?, ?, ?, ?, ?)",
            (job_id, produkt_id, user_id, _json(eingabe), _json({"schritt": "fertig", "zustand": "fertig", "text": "Nachprüfung bestanden"}),
             _json(ereignisse or []), _json(ergebnis), modell[:200], _json(verbrauch), jetzt, jetzt, jetzt),
        )
    return nummer


def version(produkt_id: str, nummer: int) -> dict[str, Any] | None:
    with connect() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM joshi_versions WHERE product_id = ? AND number = ?", (produkt_id, nummer),
        ).fetchone()
    if not zeile:
        return None
    return {
        "nummer": zeile["number"],
        "html": zlib.decompress(zeile["html"]).decode("utf-8"),
        "aenderung": zeile["change_request"],
        "zusammenfassung": zeile["summary"],
        "pruefung": _lies(zeile["validation"], {}),
        "modell": zeile["model"],
        "erstellt": zeile["created_at"],
    }


def status_fuer_version(produkt_id: str, nummer: int) -> str:
    """Ermittelt den ehrlichen Produktstatus für eine aktive Version.

    Ein abgebrochener Folgeauftrag darf eine zuvor nur teilweise geprüfte
    Version nicht versehentlich als „ready“ markieren.
    """
    if not nummer:
        return "failed"
    eintrag = version(produkt_id, nummer)
    return "ready" if eintrag and bool(eintrag.get("pruefung", {}).get("ok")) else "needs_attention"


def versionen(produkt_id: str) -> list[dict[str, Any]]:
    with connect() as verbindung:
        zeilen = verbindung.execute(
            "SELECT number, change_request, summary, validation, model, created_at, LENGTH(html) AS groesse "
            "FROM joshi_versions WHERE product_id = ? ORDER BY number", (produkt_id,),
        ).fetchall()
    ergebnis = []
    for zeile in zeilen:
        pruefung = _lies(zeile["validation"], {})
        ergebnis.append({
            "nummer": zeile["number"],
            "aenderung": zeile["change_request"],
            "zusammenfassung": zeile["summary"],
            "ok": bool(pruefung.get("ok")),
            "kurz": pruefung.get("kurz", ""),
            # Ein abgelehnter Kandidat war nie freigegeben — die Oberfläche
            # darf ihn nicht wie eine frühere gute Version anbieten.
            "abgelehnt": bool(pruefung.get("abgelehnt")),
            "modell": zeile["model"],
            "erstellt": zeile["created_at"],
            "gespeichert_bytes": zeile["groesse"],
        })
    return ergebnis


def ist_abgelehnt(produkt_id: str, nummer: int) -> bool:
    eintrag = version(produkt_id, nummer)
    return bool(eintrag and eintrag.get("pruefung", {}).get("abgelehnt"))


# ----------------------------------------------------------- Änderungslinie
def _aenderung(zeile: Any) -> dict[str, Any]:
    checkpoint = zeile["checkpoint"]
    return {
        "id": zeile["id"],
        "produkt": zeile["product_id"],
        "wunsch": zeile["request"],
        "ergaenzungen": _lies(zeile["additions"], []),
        "vertrag": _lies(zeile["contract"], {}),
        "status": zeile["status"],
        "basis": zeile["base_version"],
        "versuche": _lies(zeile["attempts"], []),
        "plan": _lies(zeile["plan"], {}),
        "checkpoint": zlib.decompress(checkpoint).decode("utf-8") if checkpoint else "",
        "checkpoint_stufe": zeile["checkpoint_stage"],
        "checkpoint_basis": zeile["checkpoint_base"],
        "checkpoint_gliederung": _lies(zeile["checkpoint_outline"], {}),
        "erstellt": zeile["created_at"],
        "geaendert": zeile["updated_at"],
    }


def aenderung_anlegen(user_id: str, produkt_id: str, wunsch: str, vertrag: dict[str, Any],
                      basis: int) -> dict[str, Any]:
    kennung = uuid.uuid4().hex
    jetzt = _jetzt()
    with connect() as verbindung:
        verbindung.execute(
            "INSERT INTO joshi_changes (id, product_id, user_id, request, contract, base_version, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kennung, produkt_id, user_id, wunsch[:20000], _json(vertrag), basis, jetzt, jetzt),
        )
    return aenderung(kennung) or {}


def aenderung(aenderung_id: str) -> dict[str, Any] | None:
    with connect() as verbindung:
        zeile = verbindung.execute("SELECT * FROM joshi_changes WHERE id = ?", (aenderung_id,)).fetchone()
    return _aenderung(zeile) if zeile else None


def aenderungen(produkt_id: str) -> list[dict[str, Any]]:
    with connect() as verbindung:
        zeilen = verbindung.execute(
            "SELECT * FROM joshi_changes WHERE product_id = ? ORDER BY created_at, rowid", (produkt_id,),
        ).fetchall()
    return [_aenderung(z) for z in zeilen]


def offene_aenderung(produkt_id: str) -> dict[str, Any] | None:
    """Der jüngste Änderungsauftrag, der noch nicht umgesetzt oder verworfen ist.

    Auch ein abgebrochener Auftrag bleibt offen: „versuch es erneut“ setzt ihn fort.
    """
    offen = [a for a in aenderungen(produkt_id) if a["status"] in {"open", "abgebrochen"}]
    return offen[-1] if offen else None


_AENDERUNG_SPALTEN = {
    "wunsch": ("request", lambda w: str(w)[:20000]),
    "ergaenzungen": ("additions", _json),
    "vertrag": ("contract", _json),
    "status": ("status", str),
    "basis": ("base_version", int),
    "versuche": ("attempts", _json),
    "plan": ("plan", _json),
    "checkpoint_stufe": ("checkpoint_stage", int),
    "checkpoint_basis": ("checkpoint_base", int),
    "checkpoint_gliederung": ("checkpoint_outline", _json),
    "checkpoint": ("checkpoint", lambda w: zlib.compress(str(w).encode("utf-8"), 6) if w else None),
}


def aenderung_aendern(aenderung_id: str, **felder: Any) -> dict[str, Any] | None:
    zuweisungen, werte = [], []
    for name, wert in felder.items():
        spalte, umwandeln = _AENDERUNG_SPALTEN[name]
        zuweisungen.append(f"{spalte} = ?")
        werte.append(umwandeln(wert))
    zuweisungen.append("updated_at = ?")
    werte.append(_jetzt())
    with connect() as verbindung:
        verbindung.execute(f"UPDATE joshi_changes SET {', '.join(zuweisungen)} WHERE id = ?",
                           (*werte, aenderung_id))
    return aenderung(aenderung_id)


# ------------------------------------------------------------------ Aufträge
def _job(zeile: Any) -> dict[str, Any]:
    return {
        "id": zeile["id"],
        "produkt": zeile["product_id"],
        "art": zeile["kind"],
        "status": zeile["status"],
        "eingabe": _lies(zeile["input"], {}),
        "fortschritt": _lies(zeile["progress"], {}),
        "ereignisse": _lies(zeile["events"], []),
        "fehler": zeile["error"],
        "ergebnis": _lies(zeile["result"], {}),
        "modell": zeile["model"],
        "verbrauch": _lies(zeile["usage"], {}),
        "erstellt": zeile["created_at"],
        "geaendert": zeile["updated_at"],
        "beendet": zeile["finished_at"],
    }


def job_anlegen(user_id: str, produkt_id: str, art: str, eingabe: dict[str, Any], modell: str) -> dict[str, Any]:
    kennung = uuid.uuid4().hex
    jetzt = _jetzt()
    with connect() as verbindung:
        verbindung.execute(
            "INSERT INTO joshi_jobs (id, product_id, user_id, kind, status, input, model, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
            (kennung, produkt_id, user_id, art, _json(eingabe), modell[:200], jetzt, jetzt),
        )
    return job(user_id, kennung) or {}


def job(user_id: str, job_id: str) -> dict[str, Any] | None:
    with connect() as verbindung:
        zeile = verbindung.execute("SELECT * FROM joshi_jobs WHERE id = ? AND user_id = ?", (job_id, user_id)).fetchone()
    return _job(zeile) if zeile else None


def job_aendern(job_id: str, **felder: Any) -> None:
    spalten = {"status": "status", "fortschritt": "progress", "ereignisse": "events", "fehler": "error",
               "ergebnis": "result", "verbrauch": "usage", "eingabe": "input"}
    zuweisungen, werte = [], []
    for name, wert in felder.items():
        zuweisungen.append(f"{spalten[name]} = ?")
        werte.append(wert if isinstance(wert, str) and name in {"status", "fehler"} else _json(wert))
    jetzt = _jetzt()
    zuweisungen.append("updated_at = ?")
    werte.append(jetzt)
    if felder.get("status") in ENDSTATUS:
        zuweisungen.append("finished_at = ?")
        werte.append(jetzt)
    with connect() as verbindung:
        verbindung.execute(f"UPDATE joshi_jobs SET {', '.join(zuweisungen)} WHERE id = ?", (*werte, job_id))


def letzter_job(user_id: str, produkt_id: str) -> dict[str, Any] | None:
    with connect() as verbindung:
        zeile = verbindung.execute(
            "SELECT * FROM joshi_jobs WHERE product_id = ? AND user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (produkt_id, user_id),
        ).fetchone()
    return _job(zeile) if zeile else None


def jobs_des_produkts(user_id: str, produkt_id: str, grenze: int = 40) -> list[dict[str, Any]]:
    with connect() as verbindung:
        zeilen = verbindung.execute(
            "SELECT * FROM joshi_jobs WHERE product_id = ? AND user_id = ? ORDER BY created_at, rowid LIMIT ?",
            (produkt_id, user_id, grenze),
        ).fetchall()
    return [_job(z) for z in zeilen]


def aktive_jobs(user_id: str) -> list[dict[str, Any]]:
    platzhalter = ",".join("?" for _ in AKTIVE_STATUS)
    with connect() as verbindung:
        zeilen = verbindung.execute(
            f"SELECT * FROM joshi_jobs WHERE user_id = ? AND status IN ({platzhalter}) ORDER BY created_at",
            (user_id, *sorted(AKTIVE_STATUS)),
        ).fetchall()
    return [_job(z) for z in zeilen]


# ------------------------------------------------------------- Einstellungen
STANDARD_EINSTELLUNGEN: dict[str, Any] = {
    "eingaben": {"aktiv": False, "pfad": "~/JOSHI-Eingaben", "deaktiviert": []},
    "workspace": {"aktiv": False, "pfad": "~/JOSHI-Workspace"},
}


def einstellungen(user_id: str) -> dict[str, Any]:
    """Asset-/Eingabeordner und Workspace — zwei getrennte Einstellungen."""
    with connect() as verbindung:
        zeile = verbindung.execute("SELECT data FROM joshi_settings WHERE user_id = ?", (user_id,)).fetchone()
    gespeichert = _lies(zeile["data"], {}) if zeile else {}
    ergebnis = {}
    for bereich, standard in STANDARD_EINSTELLUNGEN.items():
        wert = gespeichert.get(bereich) if isinstance(gespeichert.get(bereich), dict) else {}
        ergebnis[bereich] = {**standard, **{k: v for k, v in wert.items() if k in standard}}
    ergebnis["eingaben"]["deaktiviert"] = [str(n)[:255] for n in ergebnis["eingaben"]["deaktiviert"]
                                           if isinstance(n, str)][:500]
    return ergebnis


def einstellungen_speichern(user_id: str, daten: dict[str, Any]) -> dict[str, Any]:
    with connect() as verbindung:
        verbindung.execute(
            "INSERT INTO joshi_settings (user_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (user_id, _json(daten), _jetzt()),
        )
    return einstellungen(user_id)


# -------------------------------------------------------------------- Bilder
BILDTYPEN = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}


def bild_speichern(produkt_id: str, daten: bytes, mime: str, dateiname: str) -> dict[str, Any]:
    if len(daten) > MAX_BILD_BYTES:
        raise ValueError(f"{dateiname} ist größer als {MAX_BILD_BYTES // 1024 // 1024} MB.")
    mime = (mime or mimetypes.guess_type(dateiname)[0] or "").lower()
    if mime not in BILDTYPEN:
        raise ValueError(f"{dateiname} ist kein unterstütztes Bild.")
    pruefsumme = hashlib.sha256(daten).hexdigest()
    ordner = ORDNER / produkt_id
    ordner.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ORDNER, 0o700)
    except OSError:
        pass
    with connect() as verbindung:
        vorhanden = verbindung.execute(
            "SELECT name FROM joshi_assets WHERE product_id = ? AND sha256 = ?", (produkt_id, pruefsumme),
        ).fetchone()
        if vorhanden:
            return {"name": vorhanden["name"], "datei": dateiname, "mime": mime, "groesse": len(daten), "neu": False}
        anzahl = verbindung.execute(
            "SELECT COUNT(*) AS n FROM joshi_assets WHERE product_id = ?", (produkt_id,),
        ).fetchone()["n"]
        name = f"bild-{int(anzahl) + 1}"
        endung = mimetypes.guess_extension(mime) or ".bin"
        pfad = ordner / f"{name}{endung}"
        pfad.write_bytes(daten)
        verbindung.execute(
            "INSERT INTO joshi_assets (product_id, name, filename, mime, size, sha256, path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (produkt_id, name, dateiname[:200], mime, len(daten), pruefsumme, pfad.name, _jetzt()),
        )
    return {"name": name, "datei": dateiname, "mime": mime, "groesse": len(daten), "neu": True}


def bilder(produkt_id: str) -> list[dict[str, Any]]:
    with connect() as verbindung:
        zeilen = verbindung.execute(
            "SELECT name, filename, mime, size, path FROM joshi_assets WHERE product_id = ? ORDER BY created_at, name",
            (produkt_id,),
        ).fetchall()
    return [{"name": z["name"], "datei": z["filename"], "mime": z["mime"], "groesse": z["size"], "pfad": z["path"]}
            for z in zeilen]


def bild_bytes(produkt_id: str, name: str) -> tuple[bytes, str] | None:
    for bild in bilder(produkt_id):
        if bild["name"] == name:
            pfad = ORDNER / produkt_id / bild["pfad"]
            if pfad.is_file():
                return pfad.read_bytes(), bild["mime"]
    return None


def bild_data_uris(produkt_id: str) -> dict[str, str]:
    ergebnis = {}
    for bild in bilder(produkt_id):
        pfad = ORDNER / produkt_id / bild["pfad"]
        if pfad.is_file():
            ergebnis[bild["name"]] = f"data:{bild['mime']};base64,{base64.b64encode(pfad.read_bytes()).decode('ascii')}"
    return ergebnis


# ----------------------------------------------------------------- Aufräumen
NEUSTART_TEXT = (
    "Der Mini-LLM-Dienst wurde während dieses Auftrags neu gestartet. Die letzte fertige Version "
    "bleibt erhalten; schick den Auftrag einfach noch einmal."
)


def nach_neustart_aufraeumen() -> None:
    """Aufträge laufen im Serverprozess. Nach einem Neustart sind sie beendet."""
    platzhalter = ",".join("?" for _ in AKTIVE_STATUS)
    jetzt = _jetzt()
    with connect() as verbindung:
        verbindung.execute(
            f"UPDATE joshi_jobs SET status = 'failed', error = ?, updated_at = ?, finished_at = ? "
            f"WHERE status IN ({platzhalter})",
            (NEUSTART_TEXT, jetzt, jetzt, *sorted(AKTIVE_STATUS)),
        )
        laufende = verbindung.execute(
            "SELECT id, current_version FROM joshi_products WHERE status = 'building'"
        ).fetchall()
        for produkt in laufende:
            neuer_status = "failed"
            if produkt["current_version"]:
                version_zeile = verbindung.execute(
                    "SELECT validation FROM joshi_versions WHERE product_id = ? AND number = ?",
                    (produkt["id"], produkt["current_version"]),
                ).fetchone()
                try:
                    pruefung = json.loads(version_zeile["validation"]) if version_zeile else {}
                except (TypeError, json.JSONDecodeError):
                    pruefung = {}
                neuer_status = "ready" if bool(pruefung.get("ok")) else "needs_attention"
            verbindung.execute("UPDATE joshi_products SET status = ? WHERE id = ?",
                               (neuer_status, produkt["id"]))
        # Nicht behaltene Entwürfe verschwinden nach TEMPORAER_TAGE Tagen.
        alte = [z["id"] for z in verbindung.execute(
            "SELECT id FROM joshi_products WHERE kept = 0 AND updated_at < ?", (jetzt - TEMPORAER_TAGE * 86400,),
        ).fetchall()]
        for kennung in alte:
            verbindung.execute("DELETE FROM joshi_products WHERE id = ?", (kennung,))
    for kennung in alte:
        shutil.rmtree(ORDNER / kennung, ignore_errors=True)
