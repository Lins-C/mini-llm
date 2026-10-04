# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""HTTP-Schnittstelle von JOSHI (/api/joshi/*).

Mini LLM bindet diesen Router ein und reicht über `einrichten()` herein, was
JOSHI von der Anwendung braucht: Anmeldung, Modellzugang, Dateilese- und
Anhanglogik, gespeicherte Chat-Dokumente. JOSHI selbst kennt weder Ollama
noch die Chat-Datenbank.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Annotated, Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.exports import safe_filename
from app import database
from app.joshi import projektdateien, bruecke, eingaben, export, projekt, renderer, speicher
from app.joshi import dateien as dateischicht
from app.joshi.html_werk import laufzeit_dokument
from app.joshi.jobs import Auftrag, verwaltung, zeile
from app.joshi.modell import Modellzugang
from app.joshi.pipeline import Eingabe, Lauf

router = APIRouter(prefix="/api/joshi")
MODELLNAME = re.compile(r"^[\w.:\-/@+]{1,200}$")
MAX_TEXT = 20000
MAX_MATERIAL = 60000
MAX_ORDNER_IMPORT_DATEIEN = 300
MAX_ORDNER_IMPORT_BYTES = int(os.getenv("MAX_UPLOAD_MB", "250") or 250) * 1024 * 1024
BILDENDUNGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                ".gif": "image/gif", ".svg": "image/svg+xml"}
MODI = {"", "einzeldatei", "workspace"}


@dataclass
class Anbindung:
    nutzer: Callable[[Request], dict[str, Any]]
    zugang: Modellzugang
    anhaenge: Callable[[list[Any]], Awaitable[tuple[str, list[str], list[dict[str, Any]]]]]
    lese_upload: Callable[[UploadFile], Awaitable[bytes]]
    kontexte: Callable[[str, list[str]], Awaitable[str]]


_anbindung: Anbindung | None = None


def einrichten(anbindung: Anbindung) -> None:
    global _anbindung
    _anbindung = anbindung


def _a() -> Anbindung:
    if _anbindung is None:
        raise HTTPException(status_code=503, detail="JOSHI ist noch nicht bereit.")
    return _anbindung


def _nutzer(request: Request) -> dict[str, Any]:
    return _a().nutzer(request)


def _produkt_oder_404(user_id: str, produkt_id: str) -> dict[str, Any]:
    produkt = speicher.produkt(user_id, produkt_id)
    if not produkt:
        raise HTTPException(status_code=404, detail="Dieses Produkt gibt es nicht (mehr).")
    return produkt


def _modell(wert: str) -> str:
    wert = (wert or "").strip()
    if not MODELLNAME.match(wert):
        raise HTTPException(status_code=422, detail="Bitte zuerst ein Modell wählen.")
    return wert


class _Datei:
    """Gepufferte Datei für die Anhanglogik des Chats."""

    def __init__(self, filename: str, content_type: str, daten: bytes, quelle: str = "") -> None:
        self.filename = filename
        self.content_type = content_type
        self._daten = daten
        self.quelle = quelle

    async def read(self, size: int = -1) -> bytes:
        return self._daten if size < 0 else self._daten[:size]


def _bild_verkleinern(daten: bytes, mime: str) -> tuple[bytes, str]:
    """Große Fotos werden für Produkt und Modell auf 1600 px begrenzt."""
    if mime == "image/gif" or len(daten) < 400_000:
        return daten, mime
    try:
        from PIL import Image

        bild = Image.open(io.BytesIO(daten))
        bild.thumbnail((1600, 1600))
        ausgabe = io.BytesIO()
        if bild.mode in {"RGBA", "LA", "P"} and mime == "image/png":
            bild.save(ausgabe, format="PNG", optimize=True)
            return ausgabe.getvalue(), "image/png"
        bild.convert("RGB").save(ausgabe, format="JPEG", quality=86, optimize=True)
        return ausgabe.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 – dann eben das Original
        return daten, mime


async def _dateien_verarbeiten(produkt_id: str, dateien: list[Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Bilder werden Produktbilder (einbettbar), alles andere Material (Text)."""
    anbindung = _a()
    bilder: list[dict[str, Any]] = []
    andere: list[_Datei] = []
    uebersicht: list[dict[str, Any]] = []
    for datei in dateien or []:
        daten = await anbindung.lese_upload(datei)
        name = (datei.filename or "datei").replace("\\", "/").split("/")[-1][:200]
        mime = (datei.content_type or "").lower()
        endung = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if mime in speicher.BILDTYPEN or endung in BILDENDUNGEN:
            mime = mime if mime in speicher.BILDTYPEN else BILDENDUNGEN[endung]
            daten, mime = await asyncio.to_thread(_bild_verkleinern, daten, mime)
            try:
                gespeichert = await asyncio.to_thread(speicher.bild_speichern, produkt_id, daten, mime, name)
            except ValueError as fehler:
                raise HTTPException(status_code=422, detail=str(fehler)) from fehler
            bilder.append({**gespeichert, "b64": base64.b64encode(daten).decode("ascii")})
            uebersicht.append({"name": name, "art": "bild", "als": gespeichert["name"],
                               **({"quelle": datei.quelle} if getattr(datei, "quelle", "") else {})})
        else:
            andere.append(_Datei(name, mime, daten))
            uebersicht.append({"name": name, "art": "datei",
                               **({"quelle": datei.quelle} if getattr(datei, "quelle", "") else {})})
    material = ""
    if andere:
        material, weitere_bilder, _ = await anbindung.anhaenge(andere)
        for nummer, b64 in enumerate(weitere_bilder[:4], 1):
            daten = base64.b64decode(b64)
            gespeichert = await asyncio.to_thread(speicher.bild_speichern, produkt_id, daten, "image/png",
                                                  f"aus-archiv-{nummer}.png")
            bilder.append({**gespeichert, "b64": b64})
    return material[:MAX_MATERIAL], bilder, uebersicht


# --------------------------------------------- Asset-/Eingabeordner, Workspace
def _eingabe_wurzel(einstellungen: dict[str, Any]) -> dateischicht.Wurzel | None:
    bereich = einstellungen["eingaben"]
    if not bereich.get("aktiv"):
        return None
    try:
        pfad = dateischicht.wurzel_pruefen(bereich["pfad"],
                                      andere=dateischicht.vorhandene_wurzel(einstellungen["workspace"]["pfad"]))
    except dateischicht.Pfadfehler:
        return None
    return dateischicht.Wurzel(pfad, schreibbar=False, name="Asset-/Eingabeordner")


@dataclass
class Eingabewahl:
    auswahl: list[eingaben.Auswahl]
    bedarf: projekt.Bedarf
    workspace_aktiv: bool


async def _eingaben_fuer(user_id: str, text: str, bestehend_zeichen: int = 0) -> Eingabewahl:
    """Welche Dateien aus dem Asset-/Eingabeordner dieser Auftrag braucht — sonst keine."""
    einstellungen = await asyncio.to_thread(speicher.einstellungen, user_id)
    wurzel = await asyncio.to_thread(_eingabe_wurzel, einstellungen)
    auswahl: list[eingaben.Auswahl] = []
    if wurzel is not None and text.strip():
        vorhanden = await asyncio.to_thread(wurzel.liste)
        auswahl = eingaben.auswaehlen(text, vorhanden, set(einstellungen["eingaben"]["deaktiviert"]))
        try:
            await asyncio.to_thread(eingaben.einlesen, auswahl, wurzel.lesen)
        except (OSError, dateischicht.Pfadfehler) as fehler:
            raise HTTPException(status_code=422, detail=f"Eine Eingabedatei ließ sich nicht lesen: {fehler}") from fehler
    return Eingabewahl(auswahl, projekt.bedarf(text, auswahl, bestehend_zeichen=bestehend_zeichen),
                       bool(einstellungen["workspace"].get("aktiv")))


def _als_upload(auswahl: list[eingaben.Auswahl]) -> list[Any]:
    """Eingabedateien laufen durch dieselbe Verarbeitung wie hochgeladene Dateien.

    Projektdateien (Video, sehr große Daten) bekommt das Modell nicht — sie
    bleiben eigene Dateien und sind nur in der Rollenübersicht genannt.
    """
    return [_Datei(a.datei.name, dateischicht.mime_von(a.datei.name), a.daten, quelle="eingaben")
            for a in auswahl if a.rolle != "project_file" and a.daten]


def _bedarf_mit_uploads(wahl: Eingabewahl, dateien: list[UploadFile] | None,
                        text: str, bestehend_zeichen: int = 0) -> Eingabewahl:
    """Ergänzt die Workspace-Erkennung um direkt angehängte Dateien.

    Uploads werden hier nur anhand von Name, Typ und – sofern der Webserver es
    kennt – Größe bewertet. Der Inhalt wird weiterhin genau einmal in
    `_dateien_verarbeiten` gelesen.
    """
    anhaenge = []
    for datei in dateien or []:
        name = str(getattr(datei, "filename", "") or "datei")
        groesse = int(getattr(datei, "size", 0) or 0)
        anhaenge.append({"name": name, "art": dateischicht.art_von(name), "groesse": groesse})
    bedarf = projekt.bedarf(text, wahl.auswahl, bestehend_zeichen=bestehend_zeichen, anhaenge=anhaenge)
    return Eingabewahl(wahl.auswahl, bedarf, wahl.workspace_aktiv)


def _empfehlung(art: str, bedarf: projekt.Bedarf, workspace_aktiv: bool) -> dict[str, Any]:
    return {"empfehlung": {
        "art": art, "workspace_aktiv": workspace_aktiv, "gruende": bedarf.gruende,
        "text": projekt.EMPFEHLUNG_BESTEHEND if art == "ueberfuehren" else projekt.EMPFEHLUNG_NEU,
    }}


def ablauf(ereignisse: list[dict[str, Any]]) -> dict[str, Any]:
    """Die Schritte eines Auftrags mit ihrem Endzustand — für die fertige Antwort.

    Gestufte Änderungen zeigen ihre Stufen, alle anderen die Phasen
    (Verstehen, Umsetzen, Prüfen …). So bleibt sichtbar, was JOSHI getan hat.
    """
    stufen: dict[int, dict[str, Any]] = {}
    phasen: dict[str, dict[str, Any]] = {}
    for e in ereignisse or []:
        art = e.get("type")
        if art == "plan":
            phasen = {s["id"]: {"id": s["id"], "text": s.get("text", ""), "zustand": "offen", "detail": ""}
                      for s in e.get("schritte") or [] if isinstance(s, dict) and s.get("id")}
        elif art == "schritt" and e.get("schritt") in phasen:
            phasen[e["schritt"]].update(zustand=e.get("zustand", ""), detail=str(e.get("text") or "")[:200])
        elif art == "stufen":
            for s in e.get("stufen") or []:
                stufen[int(s.get("nummer") or 0)] = {"nummer": s.get("nummer"), "titel": s.get("titel", ""),
                                                     "zustand": s.get("zustand", "planned"), "grund": ""}
        elif art == "stufe" and int(e.get("nummer") or 0) in stufen:
            stufen[int(e["nummer"])].update(zustand=e.get("zustand", ""), grund=str(e.get("grund") or "")[:200])
    return {"stufen": [stufen[n] for n in sorted(stufen)], "schritte": list(phasen.values())}


def _job_fuer_ui(job: dict[str, Any]) -> dict[str, Any]:
    eingabe = job.get("eingabe") or {}
    ergebnis = job.get("ergebnis") or {}
    return {
        "id": job["id"], "art": job["art"], "status": job["status"],
        "text": eingabe.get("text", ""), "dateien": eingabe.get("dateien", []),
        "herkunft": eingabe.get("herkunft", ""),
        "antwort": ergebnis.get("text") or job.get("fehler") or "",
        "warnungen": ergebnis.get("warnungen", []),
        "version": ergebnis.get("version"),
        "fortschritt": job.get("fortschritt") or {},
        "modell": job.get("modell", ""), "verbrauch": job.get("verbrauch") or {},
        "tokenstand": (job.get("verbrauch") or {}).get("tokenstand"),
        "diagnose": ergebnis.get("diagnose") or {},
        "eingaben": eingabe.get("eingaben", []), "modus": eingabe.get("modus", ""),
        "aenderung": eingabe.get("aenderung", ""), "versuch": eingabe.get("versuch", 0),
        "erstellt": job["erstellt"], "beendet": job.get("beendet"),
        "ablauf": ablauf(job.get("ereignisse") or []),
    }


async def _starten(user_id: str, produkt: dict[str, Any], art: str, eingabe: Eingabe, modell: str,
                   meta: dict[str, Any]) -> dict[str, Any]:
    if verwaltung.laufend_fuer(produkt["id"]):
        raise HTTPException(status_code=409, detail="JOSHI arbeitet gerade an diesem Produkt. Warte kurz oder brich ab.")
    job = await asyncio.to_thread(speicher.job_anlegen, user_id, produkt["id"], art, meta, modell)
    produkt = await asyncio.to_thread(speicher.produkt_aendern, user_id, produkt["id"], status="building") or produkt
    auftrag = Auftrag(job["id"], produkt["id"], user_id)
    zugang = _a().zugang

    async def ablauf(laufender: Auftrag) -> None:
        await Lauf(laufender, user_id=user_id, produkt=produkt, art=art, eingabe=eingabe,
                   modell=modell, zugang=zugang).ausfuehren()

    verwaltung.starten(auftrag, ablauf)
    return {"produkt": produkt, "job": _job_fuer_ui(job)}


# ------------------------------------------------------------------ Routen
@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    user = _nutzer(request)
    aktiv = []
    for auftrag in verwaltung.aktive(user["id"]):
        produkt = await asyncio.to_thread(speicher.produkt, user["id"], auftrag.produkt_id)
        aktiv.append({**auftrag.schnappschuss(), "titel": (produkt or {}).get("titel", "")})
    return {"renderer": renderer.status(), "aktiv": aktiv}


@router.get("/produkte")
async def produkte(request: Request) -> dict[str, Any]:
    user = _nutzer(request)
    liste = await asyncio.to_thread(speicher.produkte, user["id"])
    laufend = {a.produkt_id: a.job_id for a in verwaltung.aktive(user["id"])}
    return {"produkte": [
        {k: p[k] for k in ("id", "titel", "status", "version", "behalten", "erstellt", "geaendert")}
        | {"laeuft": laufend.get(p["id"], "")}
        for p in liste
    ]}


@router.post("/produkte")
async def produkt_erstellen(
    request: Request,
    text: Annotated[str, Form()] = "",
    modell: Annotated[str, Form()] = "",
    chat: Annotated[str, Form()] = "",
    modus: Annotated[str, Form()] = "",
    web: Annotated[str, Form()] = "",
    dateien: Annotated[list[UploadFile] | None, File()] = None,
) -> dict[str, Any]:
    user = _nutzer(request)
    modell = _modell(modell)
    text = text.strip()[:MAX_TEXT]
    modus = modus if modus in MODI else ""
    try:
        chatdaten = json.loads(chat) if chat.strip() else {}
    except json.JSONDecodeError:
        chatdaten = {}
    chatdaten = chatdaten if isinstance(chatdaten, dict) else {}
    antwort = str(chatdaten.get("antwort") or "")[:400_000]
    frage = str(chatdaten.get("frage") or "")[:8000]
    if not text and not antwort and not dateien:
        raise HTTPException(status_code=422, detail="Beschreibe kurz, was JOSHI erstellen soll.")
    ursprung = str(chatdaten.get("produkt_id") or "")
    if ursprung and antwort:
        vorhandenes = speicher.produkt(user["id"], ursprung)
        if vorhandenes and vorhandenes["version"]:
            # Der Chat bespricht ein bestehendes Produkt: Seine Vorschläge
            # werden zur nächsten Version, nicht zu einem neuen Produkt.
            wunsch = bruecke.aenderung_aus_chat(frage, antwort)
            eingabe = Eingabe(text=wunsch)
            meta = {"text": wunsch, "dateien": [], "herkunft": "chat"}
            return await _starten(user["id"], vorhandenes, "aendern", eingabe, modell, meta)
    importiertes_html = bruecke.html_im_chat(antwort) if antwort else ""
    # Asset-/Eingabeordner: nur, was dieser Auftrag braucht. Wird das Vorhaben
    # zu groß für eine Datei und ist der Workspace aus, entscheidet der Nutzer.
    wahl = await _eingaben_fuer(user["id"], text) if text and not antwort else Eingabewahl(
        [], projekt.Bedarf(False, 0), False)
    wahl = _bedarf_mit_uploads(wahl, dateien, text)
    # Kein Workspace-Schalter mehr (29.09.2026): Jedes Produkt hat intern einen
    # Arbeitsordner, und JOSHI erkennt selbst, wann es in Projektdateien arbeitet.
    workspace = False
    auftrag = text or (bruecke.auftrag_aus_chat(frage, antwort) if antwort else "Erstelle eine Anwendung aus den Dateien.")
    quelle: dict[str, Any] = {"titel_auto": True}
    if chatdaten:
        quelle["chat"] = {k: str(chatdaten.get(k) or "")[:200] for k in ("chat_id", "message_id", "titel")}
    titel = " ".join(auftrag.split()[:5])[:60] or "Neues Produkt"
    if chatdaten.get("titel") and antwort:
        titel = str(chatdaten["titel"])[:60]
    produkt = await asyncio.to_thread(speicher.produkt_anlegen, user["id"], titel, auftrag, quelle)
    try:
        material, bilder, uebersicht = await _dateien_verarbeiten(produkt["id"], [*(dateien or []),
                                                                                  *_als_upload(wahl.auswahl)])
        if wahl.auswahl:
            material = (eingaben.rollen_text(wahl.auswahl) + "\n\n" + material).strip()[:MAX_MATERIAL]
        if chatdaten.get("context_ids"):
            ids = [str(i) for i in chatdaten.get("context_ids") or [] if isinstance(i, str)][:12]
            dokumente = await _a().kontexte(user["id"], ids)
            material = (material + "\n\n" + dokumente).strip()[:MAX_MATERIAL]
    except Exception:
        await asyncio.to_thread(speicher.produkt_loeschen, user["id"], produkt["id"])
        raise
    chat_text = bruecke.chat_kontext("" if importiertes_html else antwort, frage, str(chatdaten.get("titel") or ""))
    art = "importieren" if importiertes_html and not text else "bauen"
    eingabe = Eingabe(text=auftrag, material=material, chat=chat_text if antwort else "", bilder=bilder,
                      html=importiertes_html, eingaben=wahl.auswahl, workspace=workspace, web=web == "1")
    meta = {"text": text or auftrag, "dateien": uebersicht, "herkunft": "chat" if antwort else "",
            "material_zeichen": len(material), "eingaben": [a.snapshot() for a in wahl.auswahl],
            "modus": "workspace" if workspace else "einzeldatei", "web": web == "1"}
    return await _starten(user["id"], produkt, art, eingabe, modell, meta)


@router.post("/produkte/{produkt_id}/auftrag")
async def auftrag_starten(
    request: Request,
    produkt_id: str,
    text: Annotated[str, Form()] = "",
    modell: Annotated[str, Form()] = "",
    art: Annotated[str, Form()] = "aendern",
    fehler: Annotated[str, Form()] = "",
    modus: Annotated[str, Form()] = "",
    web: Annotated[str, Form()] = "",
    dateien: Annotated[list[UploadFile] | None, File()] = None,
) -> dict[str, Any]:
    user = _nutzer(request)
    modell = _modell(modell)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    modus = modus if modus in MODI else ""
    if art not in {"aendern", "reparieren"}:
        raise HTTPException(status_code=422, detail="Unbekannte Auftragsart.")
    text = text.strip()[:MAX_TEXT]
    fehler = fehler.strip()[:4000]
    if art == "aendern" and not text and not dateien:
        raise HTTPException(status_code=422, detail="Beschreibe, was sich ändern soll.")
    if art == "reparieren" and not fehler:
        raise HTTPException(status_code=422, detail="Es wurde kein Fehler gemeldet.")
    if not produkt["version"]:
        # Ohne Version gibt es nichts zu ändern: Der neue Text wird zum Bauauftrag.
        art = "bauen"
    im_workspace = bool((produkt.get("quelle") or {}).get("workspace"))
    wahl = Eingabewahl([], projekt.Bedarf(False, 0), False)
    if art == "aendern" and text:
        aktiv = await asyncio.to_thread(speicher.version, produkt_id, produkt["version"]) if produkt["version"] else None
        wahl = await _eingaben_fuer(user["id"], text, bestehend_zeichen=len((aktiv or {}).get("html") or ""))
        wahl = _bedarf_mit_uploads(wahl, dateien, text,
                                   bestehend_zeichen=len((aktiv or {}).get("html") or ""))
    material, bilder, uebersicht = await _dateien_verarbeiten(produkt_id, [*(dateien or []), *_als_upload(wahl.auswahl)])
    if wahl.auswahl:
        material = (eingaben.rollen_text(wahl.auswahl) + "\n\n" + material).strip()[:MAX_MATERIAL]
    if bilder and art == "aendern" and not text:
        text = "Baue das neue Bild passend in die Anwendung ein."
    workspace = False
    eingabe = Eingabe(text=text or produkt["auftrag"], material=material, bilder=bilder, fehler=fehler,
                      eingaben=wahl.auswahl, workspace=workspace, web=web == "1")
    meta = {"text": text if art != "reparieren" else "Fehler beheben: " + fehler[:300],
            "dateien": uebersicht, "herkunft": "browser" if art == "reparieren" else "",
            "eingaben": [a.snapshot() for a in wahl.auswahl], "modus": "workspace" if workspace else "einzeldatei", "web": web == "1"}
    return await _starten(user["id"], produkt, art, eingabe, modell, meta)


@router.get("/produkte/{produkt_id}")
async def produkt_lesen(request: Request, produkt_id: str) -> dict[str, Any]:
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    versionen = await asyncio.to_thread(speicher.versionen, produkt_id)
    jobs = await asyncio.to_thread(speicher.jobs_des_produkts, user["id"], produkt_id)
    laufend = verwaltung.laufend_fuer(produkt_id)
    aktuelle = next((v for v in versionen if v["nummer"] == produkt["version"]), None)
    pruefung = {}
    if aktuelle:
        gespeichert = await asyncio.to_thread(speicher.version, produkt_id, produkt["version"])
        pruefung = (gespeichert or {}).get("pruefung", {})
    return {
        "produkt": produkt,
        "versionen": versionen,
        "pruefung": pruefung,
        "auftraege": [_job_fuer_ui(j) for j in jobs],
        "laufend": laufend.schnappschuss() if laufend else None,
        "bilder": [{k: b[k] for k in ("name", "datei", "mime", "groesse")}
                   for b in await asyncio.to_thread(speicher.bilder, produkt_id)],
    }


@router.patch("/produkte/{produkt_id}")
async def produkt_aendern(request: Request, produkt_id: str, daten: dict[str, Any]) -> dict[str, Any]:
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    felder: dict[str, Any] = {}
    if "titel" in daten:
        titel = str(daten.get("titel") or "").strip()[:80]
        if not titel:
            raise HTTPException(status_code=422, detail="Der Name darf nicht leer sein.")
        felder["titel"] = titel
        felder["quelle"] = {**produkt.get("quelle", {}), "titel_auto": False}
    if "behalten" in daten:
        felder["behalten"] = bool(daten.get("behalten"))
    if not felder:
        return {"produkt": produkt}
    return {"produkt": await asyncio.to_thread(speicher.produkt_aendern, user["id"], produkt_id, **felder)}


@router.delete("/produkte/{produkt_id}")
async def produkt_loeschen(request: Request, produkt_id: str) -> dict[str, bool]:
    user = _nutzer(request)
    laufend = verwaltung.laufend_fuer(produkt_id)
    if laufend and laufend.user_id == user["id"]:
        verwaltung.abbrechen(laufend.job_id, user["id"])
    return {"ok": await asyncio.to_thread(speicher.produkt_loeschen, user["id"], produkt_id)}


async def _version_aktivieren(user_id: str, produkt_id: str, nummer: int, bewusst: bool = False) -> dict[str, Any]:
    if verwaltung.laufend_fuer(produkt_id):
        raise HTTPException(status_code=409, detail="Während JOSHI arbeitet, bleibt die Version fest.")
    version = await asyncio.to_thread(speicher.version, produkt_id, nummer)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {nummer} gibt es nicht.")
    if version["pruefung"].get("abgelehnt") and not bewusst:
        # Ein abgelehnter Kandidat war nie freigegeben. Er wird nur aktiv, wenn
        # der Nutzer es ausdrücklich will — nie mit einem beiläufigen Klick.
        raise HTTPException(status_code=409, detail=(
            f"Version {nummer} hat JOSHIs Prüfung nicht bestanden und war nie freigegeben. "
            "Sie lässt sich nur ausdrücklich trotzdem verwenden."))
    status = "ready" if version["pruefung"].get("ok") else "needs_attention"
    produkt = await asyncio.to_thread(speicher.produkt_aendern, user_id, produkt_id, version=nummer, status=status)
    return {"produkt": produkt}


@router.post("/produkte/{produkt_id}/rueckgaengig")
async def rueckgaengig(request: Request, produkt_id: str) -> dict[str, Any]:
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    # Rückgängig führt zur letzten freigegebenen Version — nie auf einen
    # abgelehnten Kandidaten.
    frueher = [v["nummer"] for v in await asyncio.to_thread(speicher.versionen, produkt_id)
               if v["nummer"] < produkt["version"] and not v.get("abgelehnt")]
    if not frueher:
        raise HTTPException(status_code=409, detail="Es gibt keine frühere Version.")
    return await _version_aktivieren(user["id"], produkt_id, max(frueher))


@router.post("/produkte/{produkt_id}/versionen/{nummer}/aktivieren")
async def version_aktivieren(request: Request, produkt_id: str, nummer: int, bewusst: bool = False) -> dict[str, Any]:
    user = _nutzer(request)
    _produkt_oder_404(user["id"], produkt_id)
    return await _version_aktivieren(user["id"], produkt_id, nummer, bewusst=bewusst)


@router.put("/produkte/{produkt_id}/zustand")
async def zustand_speichern(request: Request, produkt_id: str, zustand: dict[str, Any]) -> dict[str, bool]:
    user = _nutzer(request)
    _produkt_oder_404(user["id"], produkt_id)
    sauber = {
        "v": 1,
        "felder": zustand.get("felder") if isinstance(zustand.get("felder"), dict) else {},
        "speicher": {str(k)[:200]: str(v)[:100_000] for k, v in (zustand.get("speicher") or {}).items()}
        if isinstance(zustand.get("speicher"), dict) else {},
    }
    if not await asyncio.to_thread(speicher.zustand_speichern, user["id"], produkt_id, sauber):
        raise HTTPException(status_code=413, detail="Der Zustand der Anwendung ist zu groß zum Speichern.")
    return {"ok": True}


async def _version_des_produkts(user_id: str, produkt_id: str, nummer: int | None) -> tuple[dict[str, Any], dict[str, Any]]:
    produkt = _produkt_oder_404(user_id, produkt_id)
    version = await asyncio.to_thread(speicher.version, produkt_id, nummer or produkt["version"])
    if not version:
        raise HTTPException(status_code=404, detail="Für dieses Produkt gibt es noch keine Version.")
    return produkt, version


@router.get("/produkte/{produkt_id}/laufzeit")
async def laufzeit(request: Request, produkt_id: str, version: int | None = None) -> dict[str, Any]:
    user = _nutzer(request)
    produkt, gewaehlt = await _version_des_produkts(user["id"], produkt_id, version)
    assets = await asyncio.to_thread(speicher.bild_data_uris, produkt_id)
    dokument = laufzeit_dokument(gewaehlt["html"], modus="vorschau", zustand=produkt.get("zustand"),
                                 schluessel=produkt_id, assets=assets)
    return {"dokument": dokument, "version": gewaehlt["nummer"]}


@router.get("/produkte/{produkt_id}/quelltext")
async def quelltext(request: Request, produkt_id: str, version: int | None = None) -> dict[str, Any]:
    user = _nutzer(request)
    _, gewaehlt = await _version_des_produkts(user["id"], produkt_id, version)
    return {"html": gewaehlt["html"], "version": gewaehlt["nummer"], "pruefung": gewaehlt["pruefung"]}


def _download(daten: bytes, format_: str, name: str) -> Response:
    from urllib.parse import quote

    return Response(daten, media_type=export.FORMATE[format_], headers={
        "Content-Disposition": f"attachment; filename=\"{name.encode('ascii', 'ignore').decode() or 'joshi'}\"; "
                               f"filename*=UTF-8''{quote(name)}",
        "Cache-Control": "no-store",
    })


@router.get("/produkte/{produkt_id}/export/{format_}")
async def exportieren(request: Request, produkt_id: str, format_: str, version: int | None = None,
                      breite: int = 1280) -> Response:
    user = _nutzer(request)
    if format_ not in export.FORMATE:
        raise HTTPException(status_code=404, detail="Unbekanntes Exportformat.")
    produkt, gewaehlt = await _version_des_produkts(user["id"], produkt_id, version)
    assets = await asyncio.to_thread(speicher.bild_data_uris, produkt_id)
    breite = 390 if breite < 600 else 1280
    try:
        intern = (produkt.get("quelle") or {}).get("intern") or {}
        if format_ == "html" and intern.get("zip") and gewaehlt["nummer"] == produkt["version"]:
            # Gehören Daten- oder Mediendateien dazu, teilt JOSHI ein ZIP.
            ordner = projektdateien.ordner(database.DATA_DIR, produkt)
            daten = await asyncio.to_thread(export.projekt_zip, ordner)
            return _download(daten, "zip", export.dateiname(produkt, "zip"))
        if format_ == "html":
            daten = export.portables_html(produkt, gewaehlt, assets)
        elif format_ in {"png", "jpg"}:
            daten = await export.bild(produkt, gewaehlt, assets, format_=format_, breite=breite)
        elif format_ == "pdf":
            daten = await export.pdf(produkt, gewaehlt, assets)
        elif format_ == "docx":
            daten = await export.word(produkt, gewaehlt, assets)
        else:
            gliederung = await export.inhalt(produkt, gewaehlt, assets)
            daten, _ = export.email(produkt, gewaehlt, assets, gliederung)
    except export.ExportFehler as fehler:
        raise HTTPException(status_code=503, detail=str(fehler)) from fehler
    return _download(daten, format_, export.dateiname(produkt, format_))


# ------------------------------------------------- Export aus der Anwendung
# Die laufende Anwendung im Sandkasten darf selbst nichts Privilegiertes tun.
# Sie beschreibt nur, was exportiert werden soll; hier wird geprüft und mit den
# vorhandenen Exportern erzeugt.
ANWENDUNGSFORMATE = {"pdf", "docx", "png", "jpg"}
MAX_ABSCHNITT = 1_000_000
MAX_STIL = 400_000
GLEICHZEITIGE_EXPORTE = 2
_laufende_exporte: dict[str, int] = {}


def _dateiname(wunsch: str, format_: str, produkt: dict[str, Any]) -> str:
    """Nur ein sicherer Downloadname — keine Pfade, keine Sonderzeichen."""
    roh = (wunsch or "").replace("\\", "/").split("/")[-1].replace("\x00", "")
    stamm = re.sub(r"\.(pdf|docx|png|jpe?g|html?)$", "", roh, flags=re.IGNORECASE).strip()
    name = safe_filename(stamm or produkt.get("titel") or "joshi")[:80].strip("-") or "joshi"
    return f"{name}.{format_}"


@router.post("/produkte/{produkt_id}/export/{format_}")
async def export_aus_anwendung(request: Request, produkt_id: str, format_: str,
                               daten: dict[str, Any]) -> Response:
    """Dokumentexport, den die laufende Anwendung angefordert hat."""
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    if format_ not in ANWENDUNGSFORMATE:
        raise HTTPException(status_code=403, detail="Dieser Export ist aus der Anwendung nicht erlaubt.")
    version = int(daten.get("version") or 0)
    if not produkt["version"] or version != produkt["version"]:
        raise HTTPException(status_code=409, detail="Diese Version ist nicht die aktive Version.")
    html = str(daten.get("html") or "")
    if not html.strip():
        raise HTTPException(status_code=422, detail="Der zu exportierende Bereich ist leer.")
    if len(html) > MAX_ABSCHNITT or len(str(daten.get("css") or "")) > MAX_STIL:
        raise HTTPException(status_code=413, detail="Der zu exportierende Bereich ist zu groß.")
    if _laufende_exporte.get(produkt_id, 0) >= GLEICHZEITIGE_EXPORTE:
        raise HTTPException(status_code=429, detail="Es laufen schon Exporte für dieses Produkt.")
    name = _dateiname(str(daten.get("dateiname") or ""), format_, produkt)
    titel = str(daten.get("titel") or produkt.get("titel") or "Dokument")[:120]
    _laufende_exporte[produkt_id] = _laufende_exporte.get(produkt_id, 0) + 1
    try:
        inhalt = await export.aus_abschnitt(format_=format_, html=html,
                                            css=str(daten.get("css") or ""), titel=titel)
    except export.ExportFehler as fehler:
        raise HTTPException(status_code=503, detail=str(fehler)) from fehler
    finally:
        _laufende_exporte[produkt_id] = max(0, _laufende_exporte.get(produkt_id, 1) - 1)
        if not _laufende_exporte[produkt_id]:
            _laufende_exporte.pop(produkt_id, None)
    if not export.ist_gueltig(inhalt, format_):
        raise HTTPException(status_code=503, detail="Die Datei konnte nicht erzeugt werden.")
    return _download(inhalt, format_, name)


# ------------------------------------------------- KI aus der Anwendung
# Anwendungen mit Figuren, Chats oder Geschichten fragen über window.JOSHI.ki()
# ein Sprachmodell an. Der Nutzer hat in der Oberfläche vorher zugestimmt; die
# Anfrage läuft über dieselbe Modellschicht wie der Chat — die Anwendung sieht
# weder Ollama-Adresse noch Zugangsdaten, nur die Antwort.
KI_ROLLEN = {"system", "user", "assistant"}
KI_MAX_NACHRICHTEN = 60
KI_MAX_ZEICHEN = 120_000
KI_GLEICHZEITIG = 2
KI_MAX_ANTWORT = 40_000
_laufende_ki: dict[str, int] = {}


def ki_nachrichten(roh: Any) -> list[dict[str, str]]:
    """Nur Rollen und Text, begrenzt — alles andere aus der Anwendung fällt weg."""
    if not isinstance(roh, list) or not roh:
        raise HTTPException(status_code=422, detail="Die KI-Anfrage ist leer.")
    nachrichten = [{"role": str(n.get("role")), "content": str(n.get("content") or "")}
                   for n in roh[-KI_MAX_NACHRICHTEN:] if isinstance(n, dict) and n.get("role") in KI_ROLLEN]
    if not any(n["role"] == "user" for n in nachrichten):
        raise HTTPException(status_code=422, detail="Die KI-Anfrage enthält keine Nutzernachricht.")
    if sum(len(n["content"]) for n in nachrichten) > KI_MAX_ZEICHEN:
        raise HTTPException(status_code=413, detail="Die KI-Anfrage ist zu lang.")
    return nachrichten


@router.post("/produkte/{produkt_id}/ki")
async def ki_aus_anwendung(request: Request, produkt_id: str, daten: dict[str, Any]) -> dict[str, Any]:
    user = _nutzer(request)
    _produkt_oder_404(user["id"], produkt_id)
    modell = _modell(str(daten.get("modell") or ""))
    nachrichten = ki_nachrichten(daten.get("nachrichten"))
    if daten.get("format") == "json":
        nachrichten.insert(0, {"role": "system", "content": "Antworte ausschließlich mit gültigem JSON, ohne Erklärtext."})
    temperatur = daten.get("temperatur")
    temperatur = min(max(float(temperatur), 0.0), 1.5) if isinstance(temperatur, (int, float)) else 0.8
    if _laufende_ki.get(user["id"], 0) >= KI_GLEICHZEITIG:
        raise HTTPException(status_code=429, detail="Es laufen schon KI-Anfragen dieser Anwendung.")
    _laufende_ki[user["id"]] = _laufende_ki.get(user["id"], 0) + 1
    teile: list[str] = []
    try:
        verbrauch = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "eval_duration_ns": 0, "timed_calls": 0}
        async for stueck in _a().zugang.strom(modell, nachrichten, temperatur=temperatur, verbrauch=verbrauch):
            if stueck.get("text"):
                teile.append(stueck["text"])
                if sum(map(len, teile)) > KI_MAX_ANTWORT:
                    break
    except Exception as fehler:  # Modellschicht liefert verständliche Meldungen
        raise HTTPException(status_code=503, detail=str(fehler) or "Das KI-Modell ist nicht erreichbar.") from fehler
    finally:
        _laufende_ki[user["id"]] = max(0, _laufende_ki.get(user["id"], 1) - 1)
        if not _laufende_ki[user["id"]]:
            _laufende_ki.pop(user["id"], None)
    return {"ok": True, "text": "".join(teile)[:KI_MAX_ANTWORT], "modell": modell}


@router.get("/produkte/{produkt_id}/email")
async def email_vorlage(request: Request, produkt_id: str) -> dict[str, str]:
    user = _nutzer(request)
    produkt, gewaehlt = await _version_des_produkts(user["id"], produkt_id, None)
    assets = await asyncio.to_thread(speicher.bild_data_uris, produkt_id)
    gliederung = await export.inhalt(produkt, gewaehlt, assets)
    return export.email_vorlage(produkt, gewaehlt, gliederung)


@router.get("/produkte/{produkt_id}/uebergabe")
async def uebergabe(request: Request, produkt_id: str) -> dict[str, str]:
    user = _nutzer(request)
    produkt, gewaehlt = await _version_des_produkts(user["id"], produkt_id, None)
    assets = await asyncio.to_thread(speicher.bild_data_uris, produkt_id)
    gliederung = await export.inhalt(produkt, gewaehlt, assets)
    versionen = await asyncio.to_thread(speicher.versionen, produkt_id)
    return {"titel": produkt["titel"], "text": bruecke.uebergabe(produkt, versionen, gliederung)}


@router.get("/auftraege/{job_id}/ereignisse")
async def ereignisse(request: Request, job_id: str, ab: int = 0) -> StreamingResponse:
    user = _nutzer(request)
    if verwaltung.holen(job_id, user["id"]):
        quelle = verwaltung.abonnieren(job_id, user["id"], ab)
    else:
        job = await asyncio.to_thread(speicher.job, user["id"], job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Diesen Auftrag gibt es nicht.")

        async def gespeichert() -> AsyncIterator[bytes]:
            for ereignis in job["ereignisse"][ab:]:
                yield (json.dumps(ereignis, ensure_ascii=False) + "\n").encode()
            yield zeile("abgeschlossen", status=job["status"], text=job["fehler"] or (job["ergebnis"] or {}).get("text", ""))

        quelle = gespeichert()
    return StreamingResponse(quelle, media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/auftraege/{job_id}/abbrechen")
async def abbrechen(request: Request, job_id: str) -> JSONResponse:
    user = _nutzer(request)
    return JSONResponse({"ok": verwaltung.abbrechen(job_id, user["id"])})

# ------------------------------------------- Einstellungen: Eingaben, Workspace
def _anzeigepfad(pfad: str) -> str:
    from pathlib import Path

    for heim in (str(Path.home().resolve()), str(Path.home())):
        if pfad == heim or pfad.startswith(heim + "/"):
            return "~" + pfad[len(heim):]
    return pfad


def _einstellungen_fuer_ui(einstellungen: dict[str, Any]) -> dict[str, Any]:
    ergebnis: dict[str, Any] = {}
    for bereich in ("eingaben", "workspace"):
        eintrag = dict(einstellungen[bereich])
        andere = "workspace" if bereich == "eingaben" else "eingaben"
        try:
            pfad = dateischicht.wurzel_pruefen(eintrag["pfad"], andere=dateischicht.vorhandene_wurzel(
                einstellungen[andere]["pfad"]))
            eintrag.update(gueltig=True, fehler="", anzeige=_anzeigepfad(str(pfad)))
        except dateischicht.Pfadfehler as fehler:
            eintrag.update(gueltig=False, fehler=str(fehler), anzeige=eintrag["pfad"])
        ergebnis[bereich] = eintrag
    return ergebnis


@router.get("/einstellungen")
async def einstellungen_lesen(request: Request) -> dict[str, Any]:
    user = _nutzer(request)
    return _einstellungen_fuer_ui(await asyncio.to_thread(speicher.einstellungen, user["id"]))


@router.put("/einstellungen")
async def einstellungen_aendern(request: Request, daten: dict[str, Any]) -> dict[str, Any]:
    """Asset-/Eingabeordner und Workspace — jeder mit eigenem Schalter und Pfad, strikt getrennt."""
    user = _nutzer(request)
    aktuell = await asyncio.to_thread(speicher.einstellungen, user["id"])
    neu = {bereich: dict(werte) for bereich, werte in aktuell.items()}
    for bereich in ("eingaben", "workspace"):
        wunsch = daten.get(bereich)
        if not isinstance(wunsch, dict):
            continue
        if "pfad" in wunsch:
            neu[bereich]["pfad"] = str(wunsch["pfad"] or "").strip()[:500]
        if "aktiv" in wunsch:
            neu[bereich]["aktiv"] = bool(wunsch["aktiv"])
    a = dateischicht.vorhandene_wurzel(neu["eingaben"]["pfad"])
    b = dateischicht.vorhandene_wurzel(neu["workspace"]["pfad"])
    if a is not None and b is not None and (a == b or a in b.parents or b in a.parents):
        raise HTTPException(status_code=422, detail="Asset-/Eingabeordner und Workspace müssen getrennte Ordner "
                                                    "sein — keiner darf im anderen liegen.")
    for bereich in ("eingaben", "workspace"):
        if not neu[bereich]["aktiv"]:
            continue
        andere = "workspace" if bereich == "eingaben" else "eingaben"
        try:
            pfad = await asyncio.to_thread(dateischicht.wurzel_pruefen, neu[bereich]["pfad"], anlegen=True,
                                           andere=dateischicht.vorhandene_wurzel(neu[andere]["pfad"]))
        except dateischicht.Pfadfehler as fehler:
            raise HTTPException(status_code=422, detail=str(fehler)) from fehler
        neu[bereich]["pfad"] = _anzeigepfad(str(pfad))
    gespeichert = await asyncio.to_thread(speicher.einstellungen_speichern, user["id"], neu)
    return _einstellungen_fuer_ui(gespeichert)


@router.get("/eingaben")
async def eingaben_lesen(request: Request) -> dict[str, Any]:
    """Was im Asset-/Eingabeordner liegt — nur auflisten, nichts auswerten."""
    user = _nutzer(request)
    einstellungen = await asyncio.to_thread(speicher.einstellungen, user["id"])
    if not einstellungen["eingaben"].get("aktiv"):
        return {"aktiv": False, "dateien": []}
    wurzel = await asyncio.to_thread(_eingabe_wurzel, einstellungen)
    if wurzel is None:
        return {"aktiv": True, "dateien": [], "fehler": "Der Asset-/Eingabeordner ist nicht erreichbar."}
    aus = set(einstellungen["eingaben"]["deaktiviert"])
    liste = await asyncio.to_thread(wurzel.liste)
    return {"aktiv": True, "pfad": _anzeigepfad(str(wurzel.pfad)),
            "dateien": [{**d.als_dict(), "aktiv": d.name not in aus} for d in liste]}


@router.put("/eingaben/datei")
async def eingabe_umschalten(request: Request, daten: dict[str, Any]) -> dict[str, Any]:
    user = _nutzer(request)
    name = str(daten.get("name") or "")[:255]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=422, detail="Unbekannte Datei.")
    einstellungen = await asyncio.to_thread(speicher.einstellungen, user["id"])
    aus = [n for n in einstellungen["eingaben"]["deaktiviert"] if n != name]
    if not daten.get("aktiv"):
        aus.append(name)
    einstellungen["eingaben"]["deaktiviert"] = aus
    await asyncio.to_thread(speicher.einstellungen_speichern, user["id"], einstellungen)
    return {"name": name, "aktiv": bool(daten.get("aktiv"))}


def _oeffnen(pfad: str) -> None:
    """Zeigt einen freigegebenen Ordner im Finder des Mac mini — nichts sonst."""
    if sys.platform != "darwin":
        raise HTTPException(status_code=501, detail="Ordner öffnen gibt es nur auf dem Mac.")
    subprocess.run(["/usr/bin/open", pfad], check=False, timeout=10)


def _ordner_dialog(bereich: str) -> str | None:
    """Öffnet auf dem Mac den nativen Ordnerdialog und liefert den Pfad.

    Der Browser darf aus Sicherheitsgründen keinen lokalen absoluten Pfad
    zurückgeben. Der Dialog läuft deshalb beim Mini-LLM-Dienst auf demselben
    Mac wie die freigegebenen Ordner. Abbrechen ist ein normaler, leerer
    Rückgabewert.
    """
    if sys.platform != "darwin":
        raise RuntimeError("Die native Ordnerauswahl ist nur auf dem Mac verfügbar.")
    bezeichnung = "Assets / Eingaben" if bereich == "eingaben" else "Projekt-Workspace"
    prompt = f"JOSHI – {bezeichnung} auswählen"
    # AppleScript-String sicher begrenzen/quoten; der Text stammt nur aus dem
    # festen Bereichsnamen, nie aus einer Benutzereingabe.
    skript = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        ergebnis = subprocess.run(
            ["/usr/bin/osascript", "-e", skript],
            check=False, capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as fehler:
        raise RuntimeError("Der macOS-Ordnerdialog konnte nicht geöffnet werden.") from fehler
    if ergebnis.returncode != 0:
        # Abbrechen beendet osascript mit einem Fehlercode. Das ist kein
        # Serverfehler und darf die bisherige Einstellung nicht verändern.
        return None
    pfad = ergebnis.stdout.strip().rstrip("/")
    return pfad or None


def _import_name(name: str, belegt: set[str], *, verschachtelt: bool = False) -> str:
    """Erzeugt einen sicheren, konfliktfreien Namen für Geräte-Uploads."""
    teile = [teil.strip() for teil in re.split(r"[/\\]+", str(name or "datei")) if teil.strip()]
    roh = (teile[-1] if teile else "datei").strip()
    if not roh or roh in {".", ".."} or roh.startswith("."):
        roh = "datei"
    stamm, punkt, endung = roh.rpartition(".")
    stamm = safe_filename(stamm or roh)[:70] or "datei"
    endung = re.sub(r"[^A-Za-z0-9]", "", endung.lower())[:10]
    basis = f"{stamm}.{endung}" if punkt and endung else stamm
    if verschachtelt and len(teile) > 1:
        ordner = [safe_filename(teil) for teil in teile[:-1]
                  if teil not in {".", ".."} and not teil.startswith(".")]
        basis = "/".join([*ordner, basis]) if ordner else basis
    kandidat, nummer = basis, 2
    while kandidat in belegt:
        ordner, _, dateiname = kandidat.rpartition("/")
        stamm, punkt, endung = dateiname.rpartition(".")
        if not stamm:
            stamm, punkt, endung = dateiname, "", ""
        if punkt and endung:
            dateiname = f"{stamm}-{nummer}.{endung}"
        else:
            dateiname = f"{stamm}-{nummer}"
        kandidat = f"{ordner}/{dateiname}" if ordner else dateiname
        nummer += 1
    belegt.add(kandidat)
    return kandidat


async def _import_wurzel(user_id: str, bereich: str) -> dateischicht.Wurzel:
    """Lese-/Schreibwurzel für einen bewusst gestarteten Geräte-Import."""
    einstellungen = await asyncio.to_thread(speicher.einstellungen, user_id)
    if not einstellungen[bereich].get("aktiv"):
        name = "Asset-/Eingabeordner" if bereich == "eingaben" else "Projekt-Workspace"
        raise HTTPException(status_code=409, detail=f"Bitte zuerst den {name} einschalten.")
    andere = "workspace" if bereich == "eingaben" else "eingaben"
    try:
        pfad = await asyncio.to_thread(
            dateischicht.wurzel_pruefen,
            einstellungen[bereich]["pfad"],
            anlegen=True,
            andere=dateischicht.vorhandene_wurzel(einstellungen[andere]["pfad"]),
        )
    except dateischicht.Pfadfehler as fehler:
        raise HTTPException(status_code=422, detail=str(fehler)) from fehler
    name = "Asset-/Eingabeordner" if bereich == "eingaben" else "Workspace"
    return dateischicht.Wurzel(pfad, schreibbar=True, name=name)


@router.post("/ordner/{bereich}/importieren")
async def ordner_importieren(request: Request, bereich: str,
                             dateien: Annotated[list[UploadFile] | None, File()] = None) -> dict[str, Any]:
    """Kopiert bewusst ausgewählte Dateien vom iPhone/iPad/Browser in eine Wurzel.

    Das ist kein Dateisystemzugriff des Browsers: Die Dateien werden als Upload
    übertragen und serverseitig in die bereits freigegebene Wurzel geschrieben.
    Unterordner und versteckte Namen werden auf sichere Dateinamen reduziert.
    """
    user = _nutzer(request)
    if bereich not in {"eingaben", "workspace"}:
        raise HTTPException(status_code=404, detail="Unbekannter Ordner.")
    if not dateien:
        raise HTTPException(status_code=422, detail="Bitte mindestens eine Datei auswählen.")
    if len(dateien) > MAX_ORDNER_IMPORT_DATEIEN:
        raise HTTPException(status_code=413, detail=f"Es können höchstens {MAX_ORDNER_IMPORT_DATEIEN} Dateien auf einmal importiert werden.")
    wurzel = await _import_wurzel(user["id"], bereich)
    verschachtelt = bereich == "workspace"
    if verschachtelt:
        def vorhandene_pfade() -> set[str]:
            try:
                return {str(p.relative_to(wurzel.pfad)).replace(os.sep, "/")
                        for p in wurzel.pfad.rglob("*") if p.is_file() and not p.is_symlink()}
            except OSError:
                return set()
        belegt = await asyncio.to_thread(vorhandene_pfade)
    else:
        belegt = {datei.name for datei in await asyncio.to_thread(wurzel.liste)}
    gesamt = 0
    uebernommen: list[dict[str, Any]] = []
    for upload in dateien:
        daten = await _a().lese_upload(upload)
        gesamt += len(daten)
        if gesamt > MAX_ORDNER_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Der Geräte-Import ist zu groß.")
        name = _import_name(upload.filename or "datei", belegt, verschachtelt=verschachtelt)
        try:
            ziel = await asyncio.to_thread(wurzel.schreiben, name, daten)
        except (OSError, PermissionError, dateischicht.Pfadfehler) as fehler:
            raise HTTPException(status_code=422, detail=f"{name} ließ sich nicht speichern: {fehler}") from fehler
        uebernommen.append({"name": name, "groesse": len(daten), "pfad": str(ziel.relative_to(wurzel.pfad))})
    return {"ok": True, "bereich": bereich, "dateien": uebernommen,
            "bytes": gesamt, "pfad": _anzeigepfad(str(wurzel.pfad))}


@router.post("/ordner/{bereich}/oeffnen")
async def ordner_oeffnen(request: Request, bereich: str) -> dict[str, bool]:
    user = _nutzer(request)
    if bereich not in {"eingaben", "workspace"}:
        raise HTTPException(status_code=404, detail="Unbekannter Ordner.")
    einstellungen = await asyncio.to_thread(speicher.einstellungen, user["id"])
    andere = "workspace" if bereich == "eingaben" else "eingaben"
    try:
        pfad = await asyncio.to_thread(dateischicht.wurzel_pruefen, einstellungen[bereich]["pfad"], anlegen=True,
                                       andere=dateischicht.vorhandene_wurzel(einstellungen[andere]["pfad"]))
    except dateischicht.Pfadfehler as fehler:
        raise HTTPException(status_code=422, detail=str(fehler)) from fehler
    await asyncio.to_thread(_oeffnen, str(pfad))
    return {"ok": True}


@router.post("/ordner/{bereich}/auswaehlen")
async def ordner_auswaehlen(request: Request, bereich: str) -> dict[str, Any]:
    """Lässt den Nutzer eine lokale Ordnerwurzel auswählen und speichert sie.

    Assets/Eingaben bleiben lesbar, der Workspace bleibt schreibbar. Die
    bestehende Trennungs- und Sicherheitsprüfung läuft anschließend über
    `einstellungen_aendern`; ein ungültiger oder gleicher Ordner wird damit
    nicht gespeichert.
    """
    user = _nutzer(request)
    if bereich not in {"eingaben", "workspace"}:
        raise HTTPException(status_code=404, detail="Unbekannter Ordner.")
    try:
        pfad = await asyncio.to_thread(_ordner_dialog, bereich)
    except RuntimeError as fehler:
        raise HTTPException(status_code=501, detail=str(fehler)) from fehler
    if not pfad:
        aktuell = await asyncio.to_thread(speicher.einstellungen, user["id"])
        return {"ok": False, "abgebrochen": True, "einstellungen": _einstellungen_fuer_ui(aktuell)}
    # „Auswählen“ ist eine bewusste Freigabe: Der gewählte Ordner wird sofort
    # aktiviert, damit die Anzeige nicht scheinbar unverändert auf „aus“ bleibt.
    # Das lässt sich jederzeit über den Schalter wieder deaktivieren.
    daten = {bereich: {"pfad": pfad, "aktiv": True}}
    try:
        einstellungen = await einstellungen_aendern(request, daten)
    except HTTPException:
        raise
    return {"ok": True, "abgebrochen": False, "bereich": bereich,
            "pfad": einstellungen[bereich].get("anzeige") or pfad,
            "einstellungen": einstellungen}


def _workspace_wurzel(einstellungen: dict[str, Any]) -> dateischicht.Wurzel:
    if not einstellungen["workspace"].get("aktiv"):
        raise HTTPException(status_code=409, detail="Bitte zuerst den Projekt-Workspace einschalten.")
    try:
        pfad = dateischicht.wurzel_pruefen(einstellungen["workspace"]["pfad"], anlegen=True,
                                           andere=dateischicht.vorhandene_wurzel(einstellungen["eingaben"]["pfad"]))
    except dateischicht.Pfadfehler as fehler:
        raise HTTPException(status_code=422, detail=str(fehler)) from fehler
    return dateischicht.Wurzel(pfad, schreibbar=True, name="Workspace")


def _ueberfuehren(user_id: str, produkt: dict[str, Any]) -> dict[str, Any]:
    """Prototyp → Projekt: die aktive, geprüfte Version wird ein Workspace-Projekt."""
    einstellungen = speicher.einstellungen(user_id)
    wurzel = _workspace_wurzel(einstellungen)
    version = speicher.version(produkt["id"], produkt["version"])
    if not version:
        raise HTTPException(status_code=409, detail="Es gibt noch keine Version, die überführt werden könnte.")
    versionen = speicher.versionen(produkt["id"])
    # Eingaben früherer Builds: Kopie nur, wenn die Datei im Eingabeordner noch
    # genau der damalige Stand ist — sonst nur dokumentiert.
    schnappschuesse: dict[str, dict[str, Any]] = {}
    for eintrag in versionen:
        if eintrag["nummer"] > produkt["version"] or eintrag.get("abgelehnt"):
            continue
        for s in (speicher.version(produkt["id"], eintrag["nummer"]) or {}).get("pruefung", {}).get("eingaben") or []:
            schnappschuesse[s["name"]] = s
    eingabe_wurzel = _eingabe_wurzel(einstellungen)
    auswahl: list[eingaben.Auswahl] = []
    nur_dokumentiert: list[dict[str, Any]] = []
    for name, s in schnappschuesse.items():
        if s.get("rolle") not in {"data", "project_file"}:
            nur_dokumentiert.append(s)
            continue
        try:
            daten = eingabe_wurzel.lesen(name) if eingabe_wurzel else b""
        except (OSError, dateischicht.Pfadfehler):
            daten = b""
        if daten and dateischicht.pruefsumme(daten) == s.get("sha256"):
            datei = dateischicht.Datei(name, s.get("art", "daten"), len(daten), float(s.get("geaendert") or 0),
                                       eingabe_wurzel.pfad / name)
            auswahl.append(eingaben.Auswahl(datei, s["rolle"], s.get("grund", ""), daten, s["sha256"]))
        else:
            nur_dokumentiert.append({**s, "hinweis": "die Datei im Eingabeordner hat sich seitdem geändert "
                                                     "oder fehlt — nicht kopiert"})

    def bild_bytes(name: str) -> bytes | None:
        treffer = speicher.bild_bytes(produkt["id"], name)
        return treffer[0] if treffer else None

    meta = projekt.schreiben(wurzel, produkt=produkt, version=version, versionen=versionen,
                             bilder=speicher.bilder(produkt["id"]), bild_bytes=bild_bytes, auswahl=auswahl,
                             meta={"eingaben": nur_dokumentiert})
    return speicher.produkt_aendern(user_id, produkt["id"], quelle={**produkt.get("quelle", {}), "workspace": meta}) \
        or produkt


@router.post("/produkte/{produkt_id}/workspace")
async def workspace_ueberfuehren(request: Request, produkt_id: str) -> dict[str, Any]:
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    if verwaltung.laufend_fuer(produkt_id):
        raise HTTPException(status_code=409, detail="Während JOSHI arbeitet, bleibt das Produkt, wie es ist.")
    try:
        produkt = await asyncio.to_thread(_ueberfuehren, user["id"], produkt)
    except (OSError, dateischicht.Pfadfehler) as fehler:
        raise HTTPException(status_code=422, detail=f"Das Projekt ließ sich nicht anlegen: {fehler}") from fehler
    meta = produkt["quelle"]["workspace"]
    return {"produkt": produkt, "workspace": {"ordner": meta["ordner"],
                                              "pfad": _anzeigepfad(f"{meta['wurzel']}/{meta['ordner']}")}}


@router.post("/produkte/{produkt_id}/workspace/oeffnen")
async def workspace_oeffnen(request: Request, produkt_id: str) -> dict[str, bool]:
    user = _nutzer(request)
    produkt = _produkt_oder_404(user["id"], produkt_id)
    meta = (produkt.get("quelle") or {}).get("workspace")
    if not meta:
        raise HTTPException(status_code=404, detail="Dieses Produkt ist kein Workspace-Projekt.")
    wurzel = await asyncio.to_thread(_workspace_wurzel, await asyncio.to_thread(speicher.einstellungen, user["id"]))
    try:
        ziel = wurzel.aufloesen(meta["ordner"])
    except dateischicht.Pfadfehler as fehler:
        raise HTTPException(status_code=422, detail=str(fehler)) from fehler
    await asyncio.to_thread(_oeffnen, str(ziel))
    return {"ok": True}
