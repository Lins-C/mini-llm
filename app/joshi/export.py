# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Exportieren und Teilen: ein JOSHI-Produkt verlässt Mini LLM.

- HTML: die Anwendung samt aktuellem Zustand in einer Datei (portabel)
- PNG/JPG: die ganze Seite als Bild, nicht nur der sichtbare Ausschnitt
- PDF: A4-Druckfassung mit echtem Text
- DOCX: der sichtbare Inhalt (Überschriften, Texte, Tabellen, Werte) als
  Word-Dokument — über den bestehenden Word-Export des Chats
- E-Mail: Entwurf mit Betreff, Text und der Anwendung als Anhang
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path
from email.message import EmailMessage
from typing import Any

from app.exports import build_docx, safe_filename
from app.joshi import renderer
from app.joshi.html_werk import abschnitt_dokument, braucht_ki, export_dokument, laufzeit_dokument

FORMATE = {
    "html": "text/html; charset=utf-8",
    "png": "image/png",
    "jpg": "image/jpeg",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "eml": "message/rfc822",
    "zip": "application/zip",
}


class ExportFehler(RuntimeError):
    pass


def dateiname(produkt: dict[str, Any], endung: str) -> str:
    return f"{safe_filename(produkt.get('titel') or 'JOSHI-Produkt')}.{endung}"


def portables_html(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str]) -> bytes:
    meta = {
        "joshi": 1,
        "titel": produkt.get("titel"),
        "zweck": (produkt.get("verstaendnis") or {}).get("zweck", ""),
        "version": version["nummer"],
        "produkt": produkt["id"],
        "schluessel": f"{produkt['id'][:12]}-v{version['nummer']}-{int(time.time())}",
        "exportiert": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return export_dokument(version["html"], zustand=produkt.get("zustand"), meta=meta, assets=assets).encode("utf-8")


def _gerendert(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str]) -> str:
    return laufzeit_dokument(version["html"], modus="pruefung", zustand=produkt.get("zustand"), assets=assets)


async def bild(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str], *,
               format_: str = "png", breite: int = 1280) -> bytes:
    try:
        messung = await renderer.rendern(_gerendert(produkt, version, assets), bild=True,
                                         breite=breite, hoehe=900 if breite > 600 else 844, skala=2.0, warten=0.9)
    except renderer.RendererFehlt as fehlt:
        raise ExportFehler(f"Bildexport nicht verfügbar: {fehlt}") from fehlt
    if not messung.png:
        raise ExportFehler(messung.fehler or "Das Bild konnte nicht erzeugt werden.")
    return messung.png if format_ == "png" else _als_jpeg(messung.png)


async def pdf(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str]) -> bytes:
    try:
        messung = await renderer.rendern(_gerendert(produkt, version, assets), pdf=True, seiten_pdf=True,
                                         breite=1024, warten=0.9, probe=DRUCK_JS)
    except renderer.RendererFehlt as fehlt:
        raise ExportFehler(f"PDF-Export nicht verfügbar: {fehlt}") from fehlt
    # A4-Druckfassung bevorzugt; sonst die ganze Seite als eine lange PDF-Seite.
    ergebnis = messung.seiten_pdf or messung.pdf
    if not ergebnis:
        raise ExportFehler(messung.fehler or "Das PDF konnte nicht erzeugt werden.")
    return ergebnis


async def inhalt(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str]) -> dict[str, Any]:
    """Gliederung und sichtbarer Inhalt mit dem aktuellen Zustand."""
    try:
        messung = await renderer.rendern(_gerendert(produkt, version, assets), probe=renderer.inhaltsskript(),
                                         timeout=15)
    except renderer.RendererFehlt:
        return {"markdown": statischer_text(version["html"]), "statisch": True}
    return messung.probe or {"markdown": statischer_text(version["html"]), "statisch": True}


def statischer_text(dokument: str) -> str:
    """Rückfall ohne Browser: Überschriften, Absätze und Tabellen aus dem Quelltext."""
    from lxml import html as lxml_html

    try:
        baum = lxml_html.fromstring(dokument)
    except Exception:  # noqa: BLE001
        return ""
    for knoten in baum.xpath("//script|//style|//noscript|//template"):
        knoten.drop_tree()
    zeilen: list[str] = []
    for knoten in baum.iter("h1", "h2", "h3", "h4", "p", "li", "label", "tr"):
        text = re.sub(r"\s+", " ", knoten.text_content()).strip()
        if not text:
            continue
        if knoten.tag in {"h1", "h2", "h3", "h4"}:
            zeilen += ["", "#" * int(knoten.tag[1]) + " " + text, ""]
        elif knoten.tag == "li":
            zeilen.append(f"- {text}")
        elif knoten.tag == "tr":
            zellen = [re.sub(r"\s+", " ", z.text_content()).strip() for z in knoten.xpath("./th|./td")]
            zeilen.append("| " + " | ".join(zellen) + " |")
        else:
            zeilen += [text, ""]
    return "\n".join(zeilen).strip()[:60000]


def ohne_doppelten_titel(markdown: str, titel: str) -> str:
    """build_docx setzt den Titel selbst; die gleiche Überschrift stünde sonst doppelt."""
    erste = re.match(r"#{1,3}\s+(.+)\n?", markdown)
    if erste and erste.group(1).strip().lower() == (titel or "").strip().lower():
        return markdown[erste.end():].lstrip()
    return markdown


async def word(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str]) -> bytes:
    daten = await inhalt(produkt, version, assets)
    markdown = str(daten.get("markdown") or "").strip()
    titel = produkt.get("titel") or "JOSHI-Produkt"
    zweck = (produkt.get("verstaendnis") or {}).get("zweck", "")
    markdown = ohne_doppelten_titel(markdown, titel)
    kopf = f"{zweck}\n\n" if zweck else ""
    fuss = f"\n\n---\n\nErstellt mit JOSHI in Mini LLM · Version {version['nummer']} · {time.strftime('%d.%m.%Y')}"
    return build_docx(titel, (kopf + (markdown or "Die Anwendung enthält keinen statischen Text.") + fuss).strip())


# ------------------------------------------- Export aus der laufenden Anwendung
MAX_ABSCHNITT_BYTES = 12 * 1024 * 1024


# Druckfassung lesbar und kompakt (29.09.2026, PC-Konfigurator): Dunkle Designs
# verlieren beim Druck ihre Hintergründe, helle Schrift wurde auf Weiß fast
# unsichtbar; eine einzige überzählige Zeile erzeugte eine zweite Seite.
# Läuft im Renderer direkt vor dem Druck — ohne Modell, ohne die App zu ändern.
DRUCK_JS = r"""
const farbe = (t) => { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(t || "");
  return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null; };
const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const hintergrund = (el) => { let schicht = [255, 255, 255];
  const kette = []; for (let e = el; e && e.nodeType === 1; e = e.parentElement) kette.push(e);
  for (const e of kette.reverse()) { const c = farbe(getComputedStyle(e).backgroundColor);
    if (c && c[3] > 0) schicht = schicht.map((w, i) => Math.round(c[i] * c[3] + w * (1 - c[3]))); }
  return schicht; };
const kontrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
let angepasst = 0;
for (const el of document.body ? document.body.querySelectorAll("*") : []) {
  if (["SCRIPT", "STYLE", "svg", "path"].includes(el.tagName)) continue;
  const text = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  if (!text) continue;
  const fg = farbe(getComputedStyle(el).color); if (!fg) continue;
  const bg = hintergrund(el);
  if (kontrast(fg, bg) < 3.2) { el.style.setProperty("color", lum(bg) > 0.4 ? "#1f2937" : "#f8fafc", "important"); angepasst++; }
}
// Eine A4-Druckseite (786 pt nutzbare Höhe, 1 px = 0,75 pt) fasst gemessen gut
// 1.000 CSS-Pixel — unabhängig von der Fensterbreite (29.09.2026 nachgemessen).
const seite = 1000;
const hoehe = Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0);
let zoom = 1;
// Bis zu gut einer halben Seite zu viel: verkleinern statt einer fast leeren zweiten Seite.
if (hoehe > seite && hoehe <= seite * 1.7) { zoom = Math.floor((seite / hoehe) * 0.97 * 100) / 100; document.body.style.zoom = String(zoom); }
return JSON.stringify({ angepasst, hoehe, seite: Math.round(seite), zoom });
"""


async def aus_abschnitt(*, format_: str, html: str, css: str = "", titel: str = "",
                        breite: int = 1024) -> bytes:
    """Erzeugt PDF, Word oder Bild aus einem Ausschnitt der laufenden Anwendung.

    Die Anwendung im Sandkasten darf selbst nichts Privilegiertes tun; sie
    schickt nur den Ausschnitt. Gerendert und gebaut wird mit denselben
    Exportern wie sonst — kein zweiter Renderer, keine zweite Word-Engine.
    """
    dokument = abschnitt_dokument(html, css, titel)
    if format_ == "docx":
        daten = await inhalt_aus_dokument(dokument)
        markdown = str(daten.get("markdown") or "").strip() or statischer_text(dokument)
        if not markdown:
            raise ExportFehler("In diesem Bereich steht kein Text für ein Word-Dokument.")
        return build_docx(titel or "Dokument", ohne_doppelten_titel(markdown, titel))
    try:
        if format_ in {"png", "jpg"}:
            messung = await renderer.rendern(dokument, bild=True, breite=breite, hoehe=900, skala=2.0, warten=0.6)
            roh = messung.png
        else:
            messung = await renderer.rendern(dokument, pdf=True, seiten_pdf=True, breite=breite, warten=0.6,
                                             probe=DRUCK_JS)
            roh = messung.seiten_pdf or messung.pdf
    except renderer.RendererFehlt as fehlt:
        raise ExportFehler(f"Export nicht verfügbar: {fehlt}") from fehlt
    if not roh:
        raise ExportFehler(messung.fehler or "Die Datei konnte nicht erzeugt werden.")
    if format_ == "jpg":
        return _als_jpeg(roh)
    return roh


async def inhalt_aus_dokument(dokument: str) -> dict[str, Any]:
    try:
        messung = await renderer.rendern(dokument, probe=renderer.inhaltsskript(), timeout=15)
    except renderer.RendererFehlt:
        return {}
    return messung.probe or {}


def _als_jpeg(png: bytes) -> bytes:
    from PIL import Image

    mit_alpha = Image.open(io.BytesIO(png))
    hintergrund = Image.new("RGB", mit_alpha.size, (255, 255, 255))
    hintergrund.paste(mit_alpha, mask=mit_alpha.split()[-1] if mit_alpha.mode in {"RGBA", "LA"} else None)
    ausgabe = io.BytesIO()
    hintergrund.save(ausgabe, format="JPEG", quality=90, optimize=True, progressive=True)
    return ausgabe.getvalue()


def ist_gueltig(daten: bytes, format_: str) -> bool:
    """Ist wirklich eine brauchbare Datei entstanden?"""
    if not daten or len(daten) < 200:
        return False
    if format_ == "pdf":
        return daten.startswith(b"%PDF")
    if format_ == "png":
        return daten.startswith(b"\x89PNG")
    if format_ == "jpg":
        return daten.startswith(b"\xff\xd8")
    if format_ == "docx":
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(daten)) as archiv:
                return "word/document.xml" in archiv.namelist()
        except zipfile.BadZipFile:
            return False
    if format_ == "html":
        return b"<html" in daten[:2000].lower()
    return False


def email_vorlage(produkt: dict[str, Any], version: dict[str, Any], gliederung: dict[str, Any] | None) -> dict[str, str]:
    titel = produkt.get("titel") or "JOSHI-Produkt"
    verstaendnis = produkt.get("verstaendnis") or {}
    zweck = verstaendnis.get("zweck") or ""
    funktionen = verstaendnis.get("funktionen") or []
    zeilen = ["Hallo,", "", f"anbei „{titel}“ — eine kleine Anwendung, die direkt im Browser läuft."]
    if zweck:
        zeilen += ["", zweck]
    if funktionen:
        zeilen += ["", "Das kann sie:"] + [f"• {f}" for f in funktionen[:6]]
    werte = [f for f in (gliederung or {}).get("felder", []) if f.get("wert") and f.get("label")][:6]
    if werte:
        zeilen += ["", "Aktueller Stand:"] + [f"• {f['label']}: {f['wert']}" for f in werte]
    zeilen += [
        "",
        f"Zum Öffnen einfach die angehängte Datei „{dateiname(produkt, 'html')}“ doppelklicken — "
        "sie funktioniert ohne Installation und ohne Internetverbindung, auch auf dem Smartphone.",
        "",
        "Viele Grüße",
    ]
    return {"betreff": titel, "text": "\n".join(zeilen)}


def email(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str],
          gliederung: dict[str, Any] | None) -> tuple[bytes, dict[str, str]]:
    vorlage = email_vorlage(produkt, version, gliederung)
    nachricht = EmailMessage()
    nachricht["Subject"] = vorlage["betreff"]
    nachricht["X-Unsent"] = "1"
    nachricht.set_content(vorlage["text"])
    if hat_ki(version):
        # Mit KI-Funktion läuft die Anwendung beim Empfänger nur über die Startdatei.
        nachricht.add_attachment(paket_zip(produkt, version, assets), maintype="application", subtype="zip",
                                 filename=dateiname(produkt, "zip"))
    else:
        nachricht.add_attachment(portables_html(produkt, version, assets), maintype="text", subtype="html",
                                 filename=dateiname(produkt, "html"))
    return bytes(nachricht), vorlage


def projekt_zip(ordner: "Path") -> bytes:
    """Das Produkt aus dem internen Arbeitsordner als ZIP: index.html samt assets/, data/, medien/.

    Nur, wenn neben der HTML-Datei weitere Dateien nötig sind — sonst reicht die eine Datei.
    """
    import io
    import zipfile
    from pathlib import Path

    ordner = Path(ordner)
    if not (ordner / "index.html").is_file():
        raise ExportFehler("Der Arbeitsordner dieses Produkts ist noch nicht angelegt.")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        for name in ("index.html", "README.md"):
            if (ordner / name).is_file():
                archiv.write(ordner / name, f"{ordner.name}/{name}")
        for bereich in ("assets", "data", "medien"):
            for datei in sorted((ordner / bereich).rglob("*")) if (ordner / bereich).is_dir() else []:
                if datei.is_file() and not datei.is_symlink():
                    archiv.write(datei, f"{ordner.name}/{datei.relative_to(ordner)}")
    return puffer.getvalue()


# ----------------------------------------------------------- Teilen als ZIP
# Eine Anwendung mit KI-Funktion braucht beim Empfänger mehr als eine Datei:
# Doppelgeklickt meldet sich die Seite bei Ollama mit Herkunft „null“ und wird
# abgelehnt; über http://localhost lässt Ollama sie ab Werk zu. Das Paket
# bringt deshalb einen winzigen lokalen Start mit (nur 127.0.0.1).
PAKET = Path(__file__).with_name("paket")
STARTDATEIEN = ("start.py", "Starten (Mac).command", "Starten (Windows).bat")


def hat_ki(version: dict[str, Any]) -> bool:
    return braucht_ki(version.get("html") or "")


def liesmich(produkt: dict[str, Any], ki: bool) -> str:
    titel = produkt.get("titel") or "JOSHI-Anwendung"
    zeilen = [f"{titel}", "=" * len(titel), "", "Erstellt mit JOSHI · Mini LLM (powered by AI-Implements · C. Lins)", ""]
    if ki:
        zeilen += [
            "Diese Anwendung enthält KI-Funktionen. Sie nutzt das KI-Modell auf DEINEM Rechner (Ollama).",
            "",
            "1. Ollama installieren und starten: https://ollama.com/download",
            "2. Ein Modell laden: in der Ollama-App oder im Terminal mit  ollama pull <modellname>",
            "3. ZIP entpacken und starten:",
            "   Mac:     „Starten (Mac).command“ doppelklicken.",
            "            Beim ersten Mal meldet macOS „nicht geöffnet“ (die Datei ist nicht bei Apple",
            "            registriert). Dann: „Fertig“ → Systemeinstellungen → Datenschutz & Sicherheit →",
            "            ganz unten „Dennoch öffnen“ → nochmals doppelklicken → „Öffnen“. Nur einmal nötig.",
            "            Alternative ohne Freigabe: Terminal öffnen, „python3 “ tippen, start.py ins",
            "            Fenster ziehen, Enter.",
            "   Windows: „Starten (Windows).bat“ doppelklicken",
            "4. Der Browser öffnet die Anwendung. Vor der ersten KI-Anfrage fragt sie um Erlaubnis.",
            "",
            "Warum die Startdatei? Eine doppelgeklickte HTML-Datei lässt Ollama aus Sicherheitsgründen",
            "nicht zu. Die Startdatei öffnet die Anwendung über http://localhost – nur auf diesem Rechner,",
            "nichts geht ins Internet. Dafür wird Python 3 benötigt (Mac meist vorhanden).",
            "",
            "Ohne Ollama funktioniert alles außer den KI-Funktionen; index.html lässt sich dann auch direkt öffnen.",
        ]
    else:
        zeilen += ["index.html im Browser öffnen – die Anwendung läuft ohne Internet."]
    return "\n".join(zeilen) + "\n"


def _ablegen(archiv: Any, pfad: str, daten: bytes, ausfuehrbar: bool = False) -> None:
    import zipfile

    info = zipfile.ZipInfo(pfad, time.localtime()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100755 if ausfuehrbar else 0o100644) << 16
    archiv.writestr(info, daten)


def paket_zip(produkt: dict[str, Any], version: dict[str, Any], assets: dict[str, str],
              ordner: "Path | None" = None) -> bytes:
    """Anwendung als ZIP: index.html (+ Projektdateien) und bei KI-Funktion die Startdateien."""
    import io
    import zipfile

    ki = hat_ki(version)
    projekt = ordner is not None and (Path(ordner) / "index.html").is_file()
    wurzel = Path(ordner).name if projekt else safe_filename(produkt.get("titel") or "JOSHI-Anwendung")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        if projekt:
            with zipfile.ZipFile(io.BytesIO(projekt_zip(ordner))) as quelle:
                for eintrag in quelle.infolist():
                    teile = eintrag.filename.split("/", 1)
                    if len(teile) == 2 and teile[1]:
                        _ablegen(archiv, f"{wurzel}/{teile[1]}", quelle.read(eintrag))
        else:
            _ablegen(archiv, f"{wurzel}/index.html", portables_html(produkt, version, assets))
        _ablegen(archiv, f"{wurzel}/LIESMICH.txt", liesmich(produkt, ki).encode("utf-8"))
        if ki:
            for name in STARTDATEIEN:
                _ablegen(archiv, f"{wurzel}/{name}", (PAKET / name).read_bytes(), name.endswith(".command"))
    return puffer.getvalue()
