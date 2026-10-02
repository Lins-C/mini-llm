# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Bekannte JavaScript-Bibliotheken: JOSHI stellt sie bereit, die App bleibt offline.

Gefunden am 02.10.2026 am 3D-Sonnensystem: Ein Modell band three.js von
cdn.jsdelivr.net ein. Die Sandbox blockt das Netz, die Seite blieb schwarz, und
zwei Reparaturen schrieben dieselbe Einbindung erneut — eine echte 3D-Ansicht ohne
Bibliothek bekommt kaum ein Modell hin.

Jetzt gilt:
- Skripte von jsdelivr, unpkg oder cdnjs lädt JOSHI beim Bauen EINMAL herunter
  (höchstens 3 MB, nur JavaScript) und legt sie im Datenordner ab.
- Im gespeicherten Code steht nur ein kurzer Platzhalter
  `<script data-joshi-bibliothek="…"></script>` — spätere Änderungen schicken dem
  Modell keine hunderte Kilobyte Bibliothekscode.
- Vorschau, Prüfung, Export und Teilen betten die Bibliothek ein: Die fertige
  Datei läuft ohne Internet.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ERLAUBT = ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com")
MAX_BYTES = 3 * 1024 * 1024
_SKRIPT = re.compile(
    r"<script\b(?P<vor>[^>]*?)\bsrc\s*=\s*[\"'](?P<url>(?:https?:)?//(?P<host>[^/\"']+)/[^\"']+)[\"'](?P<nach>[^>]*)>"
    r"\s*</script\s*>", re.IGNORECASE)
_PLATZHALTER = re.compile(r'<script data-joshi-bibliothek="(?P<schluessel>[a-z0-9._@-]+)"'
                         r'(?: data-quelle="(?P<url>[^"]+)")?></script>', re.IGNORECASE)


def _ordner() -> Path:
    from app.database import DATA_DIR

    ordner = Path(DATA_DIR) / "joshi-bibliotheken"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def urlparse_host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url if url.startswith("http") else "https:" + url).hostname or "").lower()


def schluessel(url: str) -> str:
    """Stabiler, lesbarer Name: „three@0.152.2-3f2a9c1b“."""
    teil = re.search(r"/npm/((?:@[^/]+/)?[^/@]+@[^/]+)|/ajax/libs/([^/]+/[^/]+)|unpkg\.com/((?:@[^/]+/)?[^/@]+@[^/]+)", url)
    name = next((g for g in (teil.groups() if teil else ()) if g), "bibliothek")
    name = re.sub(r"[^a-z0-9._@-]+", "-", name.lower()).strip("-")[:48] or "bibliothek"
    return f"{name}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _laden(url: str) -> bytes | None:
    import httpx

    try:
        antwort = httpx.get(url if url.startswith("http") else "https:" + url, timeout=30, follow_redirects=True)
        antwort.raise_for_status()
    except httpx.HTTPError:
        return None
    art = antwort.headers.get("content-type", "")
    if len(antwort.content) > MAX_BYTES or ("javascript" not in art and "text/plain" not in art):
        return None
    return antwort.content


def einbinden(html: str, laden=_laden) -> tuple[str, list[str], list[str]]:
    """Ersetzt erlaubte CDN-Skripte durch Platzhalter. Rückgabe: (HTML, eingebunden, nicht ladbar)."""
    eingebunden: list[str] = []
    fehlgeschlagen: list[str] = []

    def ersetzen(treffer: re.Match[str]) -> str:
        url, host = treffer.group("url"), treffer.group("host").lower()
        if host not in ERLAUBT or "type=\"module\"" in treffer.group(0).lower() or not url.split("?")[0].endswith(".js"):
            return treffer.group(0)
        name = schluessel(url)
        datei = _ordner() / f"{name}.js"
        if not datei.is_file():
            inhalt = laden(url)
            if inhalt is None:
                fehlgeschlagen.append(url)
                return treffer.group(0)
            datei.write_bytes(inhalt)
            verzeichnis = _ordner() / "verzeichnis.json"
            try:
                daten = json.loads(verzeichnis.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                daten = {}
            daten[name] = url
            verzeichnis.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
        eingebunden.append(name)
        return f'<script data-joshi-bibliothek="{name}" data-quelle="{url}"></script>'

    return _SKRIPT.sub(ersetzen, html or ""), eingebunden, fehlgeschlagen


def einsetzen(html: str, laden=_laden) -> str:
    """Bettet die Bibliotheken für Vorschau, Prüfung und Export ein.

    Fehlt eine Bibliothek im Datenordner (Umzug, anderer Rechner), lädt JOSHI sie
    über die gemerkte Quelle einmal nach.
    """
    def ersetzen(treffer: re.Match[str]) -> str:
        datei = _ordner() / f"{treffer.group('schluessel')}.js"
        url = treffer.group("url") or ""
        if not datei.is_file() and urlparse_host(url) in ERLAUBT:
            inhalt = laden(url)
            if inhalt is not None:
                datei.write_bytes(inhalt)
        if not datei.is_file():
            return treffer.group(0)
        code = datei.read_text(encoding="utf-8", errors="replace").replace("</script", "<\\/script")
        return f"<script>/* {treffer.group('schluessel')} – von JOSHI eingebettet */\n{code}\n</script>"

    return _PLATZHALTER.sub(ersetzen, html or "")
