# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import shutil
import tempfile
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from lxml import html as lxml_html
from pypdf import PdfReader

from app.database import DATA_DIR


ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = DATA_DIR / "context-cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_CACHE_DIR = DATA_DIR / "context-analysis-cache"
ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_CACHE_DIR = ROOT / ".context-cache"
if LEGACY_CACHE_DIR.exists() and LEGACY_CACHE_DIR != CACHE_DIR:
    for legacy_file in LEGACY_CACHE_DIR.glob("*.json"):
        target = CACHE_DIR / legacy_file.name
        if not target.exists():
            try:
                shutil.copy2(legacy_file, target)
            except OSError:
                pass

CHUNK_CHARS = int(os.getenv("CONTEXT_CHUNK_CHARS", "6000"))
CHUNK_OVERLAP = int(os.getenv("CONTEXT_CHUNK_OVERLAP", "700"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WEB_RESULTS = int(os.getenv("WEB_RESULTS", "5"))
WEB_PAGE_CHARS = int(os.getenv("WEB_PAGE_CHARS", "7000"))

MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".opus",
    ".webm", ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg",
}
MEDIA_MIME_PREFIXES = ("audio/", "video/")

YOUTUBE_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/|live/)|youtu\.be/)"
    r"[^\s<>\])]+",
    re.IGNORECASE,
)

_whisper_model: Any = None
_whisper_lock = asyncio.Lock()


def split_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        target = min(len(text), start + size)
        end = target
        if target < len(text):
            candidates = [
                text.rfind("\n\n", start + size // 2, target),
                text.rfind("\n", start + size // 2, target),
                text.rfind(". ", start + size // 2, target),
            ]
            best = max(candidates)
            if best > start:
                end = min(target, best + (2 if text[best:best + 2] == ". " else 1))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def cache_context(name: str, text: str, kind: str = "document") -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{digest}.json"
    payload = {
        "version": 3,
        "id": digest,
        "name": name,
        "kind": kind,
        "created_at": int(time.time()),
        "characters": len(text),
        "text": text,
        "chunks": [
            {
                "index": index,
                "text": chunk,
                "characters": len(chunk),
            }
            for index, chunk in enumerate(split_text(text))
        ],
    }
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return {
        "id": digest,
        "name": name,
        "kind": kind,
        "chunks": len(payload["chunks"]),
        "characters": len(text),
    }


def context_source_text(context: dict[str, Any]) -> str:
    """Return one cached source without duplicating the overlap between chunks."""
    stored = context.get("text")
    if isinstance(stored, str) and stored:
        return stored

    chunks: list[str] = []
    for item in context.get("chunks") or []:
        text = item.get("text") if isinstance(item, dict) else item
        if isinstance(text, str) and text:
            chunks.append(text)
    if not chunks:
        return ""

    merged = chunks[0]
    for chunk in chunks[1:]:
        overlap = 0
        upper = min(len(merged), len(chunk), max(CHUNK_OVERLAP * 3, 2000))
        for size in range(upper, 0, -1):
            if merged.endswith(chunk[:size]):
                overlap = size
                break
        merged += chunk[overlap:]
    return merged


def _analysis_cache_key(
    chunks: list[tuple[str, str]],
    query: str,
    model: str,
) -> str:
    normalized_query = re.sub(r"\s+", " ", query.lower()).strip()
    source_fingerprint = "\n".join(
        f"{label}\0{hashlib.sha256(chunk.encode('utf-8')).hexdigest()}"
        for label, chunk in chunks
    )
    return hashlib.sha256(
        f"{model}\0{normalized_query}\0{source_fingerprint}".encode("utf-8")
    ).hexdigest()


def load_query_analysis(
    chunks: list[tuple[str, str]],
    query: str,
    model: str,
) -> str:
    if not chunks:
        return ""
    path = ANALYSIS_CACHE_DIR / f"{_analysis_cache_key(chunks, query, model)}.txt"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def cache_query_analysis(
    chunks: list[tuple[str, str]],
    query: str,
    model: str,
    analysis: str,
) -> None:
    analysis = analysis.strip()
    if not chunks or not analysis:
        return
    path = ANALYSIS_CACHE_DIR / f"{_analysis_cache_key(chunks, query, model)}.txt"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(analysis, encoding="utf-8")
    temporary.replace(path)


def load_contexts(context_ids: list[str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context_id in context_ids[:80]:
        if not re.fullmatch(r"[a-f0-9]{64}", str(context_id)) or context_id in seen:
            continue
        seen.add(context_id)
        path = CACHE_DIR / f"{context_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload.get("chunks"), list):
            contexts.append(payload)
    return contexts


def find_youtube_urls(text: str) -> list[str]:
    return list(dict.fromkeys(match.rstrip(".,;!?") for match in YOUTUBE_RE.findall(text)))


def _validate_youtube_url(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        raise ValueError("Nur YouTube-Links werden für die Transkription akzeptiert.")


async def transcribe_media(data: bytes, filename: str) -> str:
    global _whisper_model
    suffix = Path(filename).suffix.lower() or ".webm"

    async with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            _whisper_model = await asyncio.to_thread(
                WhisperModel,
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(data)
            temporary_path = Path(handle.name)
        try:
            def run() -> str:
                segments, _ = _whisper_model.transcribe(
                    str(temporary_path),
                    beam_size=5,
                    vad_filter=True,
                )
                return " ".join(segment.text.strip() for segment in segments).strip()

            return await asyncio.to_thread(run)
        finally:
            temporary_path.unlink(missing_ok=True)


async def transcribe_youtube(url: str) -> tuple[str, str]:
    _validate_youtube_url(url)
    with tempfile.TemporaryDirectory(prefix="mini-llm-youtube-") as folder:
        output_template = str(Path(folder) / "%(id)s.%(ext)s")

        def download() -> tuple[str, str]:
            from yt_dlp import YoutubeDL

            options = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "max_filesize": int(os.getenv("YOUTUBE_MAX_MB", "500")) * 1024 * 1024,
            }
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
                requested = info.get("requested_downloads") or []
                filepath = requested[0].get("filepath") if requested else None
                if not filepath:
                    filepath = downloader.prepare_filename(info)
                return str(filepath), str(info.get("title") or "YouTube-Video")

        filepath, title = await asyncio.to_thread(download)
        media = Path(filepath).read_bytes()
        return title, await transcribe_media(media, filepath)


def current_local_time() -> datetime:
    return datetime.now(ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Berlin")))


def current_date_label() -> str:
    return current_local_time().strftime("%d.%m.%Y")


ANLEITUNGSSEITEN = re.compile(
    r"(?i)(bericht|aufsatz|text|essay)\s*(schreiben|verfassen)|wie\s+(man|schreibt)"
    r"|schritt[- ]für[- ]schritt|vorlage|übungen|klasse\s*\d"
)


def _source_score(item: dict[str, str], query: str) -> float:
    host = (urlparse(item.get("url", "")).hostname or "").lower()
    trusted = (
        "fifa.com", "uefa.com", "bundesliga.com", "dfb.de", "rfef.es",
        "afa.com.ar", "sportschau.de", "zdf.de", "apnews.com", "reuters.com",
        "finanzamt.nrw.de", "finanzverwaltung.nrw.de",
        "bundesfinanzministerium.de",
    )
    score = 5.0 if any(host == domain or host.endswith(f".{domain}") for domain in trusted) else 0.0
    if any(term in query.lower() for term in ("adresse", "anschrift", "kontaktdaten")):
        if host.endswith((".bund.de", ".nrw.de")):
            score += 6.0
    today = current_local_time()
    haystack = " ".join(str(item.get(key, "")) for key in ("title", "snippet", "date")).lower()
    if str(today.year) in haystack:
        score += 2.0
    if today.strftime("%d.%m.%Y") in haystack or today.strftime("%Y-%m-%d") in haystack:
        score += 2.0
    if any(term in query.lower() for term in ("meister", "champion")) and any(
        term in haystack for term in ("meister", "champion")
    ):
        score += 3.0
    terms = set(re.findall(r"[\wäöüß-]{4,}", query.lower()))
    score += min(4.0, sum(1 for term in terms if term in haystack) * 0.35)
    # Schreibratgeber sind fast nie die gesuchte Quelle.
    if ANLEITUNGSSEITEN.search(haystack) and not ANLEITUNGSSEITEN.search(query.lower()):
        score -= 6.0
    return score


AUFTRAGSFLOSKELN = re.compile(
    r"(?i)^\s*(?:und\s+|dann\s+|bitte\s+|jetzt\s+|ok\s+|okay\s+)*"
    r"(?:kannst\s+du\s+|könntest\s+du\s+|würdest\s+du\s+)?"
    r"(?:schreib(?:e|st)?|verfass(?:e)?|erstell(?:e)?|mach(?:e)?|bau(?:e)?|"
    r"formulier(?:e)?|entwirf|liefer(?:e)?)\s+"
    r"(?:du\s+|mir\s+|uns\s+)*"
    r"(?:bitte\s+)?(?:ein(?:en|e)?\s+|den\s+|die\s+|das\s+)?"
    r"(?:(?:ausführlich|umfangreich|detailliert|tief|sachlich|lang|kurz|"
    r"vollständig|gründlich|fundiert)(?:e|en|es|er|em)?\s+)*"
    r"(?:bericht|aufsatz|text|artikel|dokument|zusammenfassung|analyse|protokoll|"
    r"anleitung|erklärung|erlaeuterung|abhandlung|studie)\s*"
    r"(?:über|ueber|zum|zur|zu|vom|von)?\s*"
)
UMFANGSFLOSKELN = re.compile(
    r"(?i)\b(?:so\s+)?(?:ausführlich|umfangreich|detailliert|tief|lang|kurz|kompakt)"
    r"(?:\s+und\s+(?:lang|ausführlich|umfangreich|tief|kurz))?"
    r"(?:\s*,?\s*wie\s+(?:du|es)\s+(?:kannst|geht|möglich\s+ist))?"
    r"|\büber\s+\d+\s*seiten?\b|\bmit\s+\d+\s*seiten?\b|\b\d+\s*seiten?\b"
    r"|\bschreibe?\s+(?:tief|lang|ausführlich|umfangreich)\b"
)
SUCHFLOSKELN = re.compile(
    r"(?i)\b(?:such(?:e|st)?|recherchier(?:e|st)?|prüf(?:e)?|schau)\b"
    r"(?:\s+(?:du|mal|bitte))?"
    r"(?:\s+im\s+(?:internet|netzt|netz|web|www))?"
    r"(?:\s+nach)?\s*"
    r"(?:korrekte[nr]?\s+|richtige[nr]?\s+|aktuelle[nr]?\s+|genaue[nr]?\s+)?"
    r"(?:angaben|informationen|infos|daten|quellen|fakten)?\s*"
    r"(?:zum|zur|zu|über|ueber|nach)?\s*"
)


def search_topic(prompt: str) -> str:
    """Zieht das Thema aus einem Auftrag heraus.

    „Schreib einen ausführlichen Bericht über 49 Seiten. Such im Netz nach
    Angaben zum Lager Holzen“ ergibt sonst eine Suche nach Anleitungen zum
    Berichtschreiben — genau das ist passiert.
    """

    text = re.sub(r"\s+", " ", prompt or "").strip()
    if not text:
        return ""
    teile = [teil.strip() for teil in re.split(r"(?<=[.!?])\s+", text) if teil.strip()]
    themen: list[str] = []
    for teil in teile:
        ohne = AUFTRAGSFLOSKELN.sub("", teil)
        ohne = SUCHFLOSKELN.sub("", ohne)
        ohne = UMFANGSFLOSKELN.sub(" ", ohne)
        ohne = re.sub(r"\s+", " ", ohne).strip(" ,.;:-–—?!")
        # Was übrig bleibt, muss noch Inhalt tragen.
        # Übrig bleibende Füllwörter sind kein Thema.
        ohne = re.sub(
            r"(?i)^(?:bitte|mal|doch|noch|dazu|davon|und|so)\b\s*", "", ohne
        ).strip(" ,.;:-–—?!")
        traegt_inhalt = len(ohne) >= 6 and len(ohne.split()) >= 2
        if traegt_inhalt and re.search(r"[A-Za-zÄÖÜäöüß]{3,}", ohne):
            themen.append(ohne)
    if not themen:
        return ""
    # Der längste verbleibende Teil trägt in aller Regel das Thema.
    return max(themen, key=len)[:300]


SUCHHINWEIS = re.compile(
    r"(?i)\b(?:such\w*|recherch\w*|googl\w*|nachschlag\w*)\b"
    r"|\bim\s+(?:web|internet|netz)\b|\bonline\b"
)
# Wörter, die den Auftrag beschreiben, nicht den Suchgegenstand. Großgeschrieben
# sind im Deutschen alle Nomen — auch „Beispiel", „Buttons" oder „Einpflegen".
FUELLWOERTER = frozenset("""
der die das den dem des ein eine einen einem einer eines und oder aber auch nur
noch nun jetzt bitte mal doch dies diese dieser dieses hier dort ich du wir ihr
sie es mir mich uns dir dich kannst könntest würdest soll sollst mach mache
machen schreib schreibe erstelle erstellen ergänze ergänzen erweitere verwende
verwenden nutze nutzen such suche suchen recherchiere recherchieren finde finden
gib nenne zeig zeige pflege einpflegen systematisch innerhalb im in von vom zum
zur mit für auf an aus bei nach über unter ok okay wie was wer wo wann welche
welcher welches bzw usw etc je sowie als dass damit web internet netz online
google beispiel beispiele funktion funktionen button buttons knopf knöpfe html
css code seite webseite website datei dateien liste tabelle vorschau version
anwendung app ergebnis ergebnisse info infos informationen daten quellen text
""".split())


def suchbegriffe(prompt: str) -> str:
    """Wenige Stichwörter für die Suchmaschine statt eines ganzen Satzes.

    „mach ein Beispiel verwende innerhalb Musterstadt NRW die Ärzte dies kannst du im
    web Suchen und systematisch Einpflegen, ergänze die html" ergab als
    Suchanfrage ein Pizza-Video, Schulferien und eine Bank — keinen einzigen
    Arzt. „Musterstadt NRW Ärzte" liefert das Ärztezentrum Musterstadt und die Praxisliste
    der Stadt.
    """
    text = re.sub(r"\s+", " ", prompt or "").strip()
    if not text:
        return ""
    saetze = [satz for satz in re.split(r"(?<=[.!?])\s+", text) if satz.strip()]
    mit_hinweis = [satz for satz in saetze if SUCHHINWEIS.search(satz)]
    quelle = max(mit_hinweis, key=len) if mit_hinweis else (search_topic(text) or text)
    woerter = re.findall(r"[A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9-]*", quelle)
    inhalt = [wort for wort in woerter if wort.lower() not in FUELLWOERTER]
    stichwoerter = [wort for wort in inhalt if wort[0].isupper() or wort[0].isdigit()]
    if len(stichwoerter) < 2:
        # Klein geschrieben („ärzte in musterstadt"): dann alle tragenden Wörter.
        stichwoerter = [wort for wort in inhalt if len(wort) >= 4 or wort[0].isdigit()]
    eindeutig = list(dict.fromkeys(stichwoerter))[:6]
    return " ".join(eindeutig) if len(eindeutig) >= 2 else ""


async def web_search(query: str, conversation_context: str = "") -> list[dict[str, str]]:
    today = current_local_time()
    clean_query = re.sub(r"\s+", " ", query).strip()
    needs_context = len(clean_query) < 70 or bool(re.search(
        r"(?i)\b(das|dazu|davon|dort|hier|eben|vorher|passt|stimmt|wer|wann|welche)\b",
        clean_query,
    ))
    combined = clean_query
    if needs_context and conversation_context:
        combined = re.sub(
            r"\s+",
            " ",
            f"{conversation_context[-900:]} {clean_query}",
        ).strip()
    focused = re.sub(
        r"(?i)\b(?:suche|such|recherchiere)(?:\s+bitte)?(?:\s+im\s+internet|\s+im\s+web)?"
        r"(?:\s+nach)?\b",
        "",
        combined,
    ).strip(" ?.,")
    thema = search_topic(clean_query)
    # Ein langes „Thema" ist meist noch ein halber Auftrag. Dann treffen wenige
    # Stichwörter besser als der ganze Satz — und der Satz selbst bringt nur
    # Rauschen (Pizza-Video, Schulferien, Bank statt Ärzten in Musterstadt).
    stichwoerter = suchbegriffe(clean_query) if len((thema or clean_query).split()) > 7 else ""
    if stichwoerter:
        # Das lange „Thema" bleibt draußen — es brachte genau das Rauschen.
        query_variants = [stichwoerter, f"{stichwoerter} offiziell {today.year}"]
    else:
        query_variants = [
            # Das Thema steht vorn: Es entscheidet, was die Suchmaschine liefert.
            thema,
            f"{thema} Geschichte" if thema and len(thema.split()) <= 6 else "",
            combined,
            focused,
            f"{focused} aktuell {today.strftime('%d. %B %Y')}",
            f"{focused} offiziell {today.year}",
        ]
    lowered = combined.lower()
    query_terms = {
        term for term in re.findall(r"[\wäöüß-]{4,}", clean_query.lower())
        if term not in {
            "bitte", "prüfe", "pruefe", "suche", "internet", "websuche",
            "tatsächlich", "tatsaechlich", "passt", "wurde", "werden",
            "einen", "einem", "einer", "dieser", "dieses", "diese",
        }
    }
    if "bundesliga" in lowered:
        season_start = today.year if today.month >= 8 else today.year - 1
        season = f"{season_start}/{str(season_start + 1)[-2:]}"
        query_variants.extend([
            f"Bundesliga {season} Meister",
            f"site:bundesliga.com/de/bundesliga/news Meister {season}",
            f"site:bundesliga.com/de/bundesliga/news Deutscher Meister {season} Fußball",
            f"site:bundesliga.com/en/bundesliga/news champions {season_start}-{str(season_start + 1)[-2:]}",
            f"site:bundesliga.com/en/bundesliga/news crowned champions {season}",
            f"Bundesliga champions {today.year}",
        ])
    if any(term in lowered for term in ("wm-finale", "wm finale", "weltmeisterschaft", "world cup")):
        query_variants.extend([
            f"WM Finale {today.year} Mannschaften {today.strftime('%d.%m.%Y')}",
            f"site:fifa.com/de WM Finale {today.year} Mannschaften",
            f"World Cup final {today.year} teams today",
        ])
    authority_match = re.search(
        r"\b(finanzamt)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+"
        r"(?:\s+(?:am|an\s+der|im)\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+)?)\b",
        combined,
        flags=re.IGNORECASE,
    )
    if authority_match:
        authority = f"{authority_match.group(1)} {authority_match.group(2)}"
        query_variants.extend([
            f"site:finanzamt.nrw.de {authority} Anschrift",
            f"site:finanzamt.nrw.de {authority} Adresse Kontakt",
            f"{authority} offizielle Anschrift",
        ])
    query_variants = list(dict.fromkeys(item for item in query_variants if item))

    # Bewertet wird gegen das Thema: Sonst gewinnen bei „Schreibe einen Bericht
    # über X“ die Seiten, die erklären, wie man Berichte schreibt.
    bewertungstext = stichwoerter or thema or clean_query

    def search() -> list[dict[str, str]]:
        from ddgs import DDGS

        clean: list[dict[str, str]] = []
        engine = DDGS()
        for search_query in query_variants:
            try:
                text_results = engine.text(
                    search_query,
                    region="de-de",
                    safesearch="moderate",
                    max_results=max(WEB_RESULTS, 6),
                )
            except Exception:
                text_results = []
            try:
                news_results = engine.news(
                    search_query,
                    region="de-de",
                    safesearch="moderate",
                    max_results=max(WEB_RESULTS, 6),
                )
            except Exception:
                news_results = []
            for kind, results in (("web", text_results), ("news", news_results)):
                for item in results or []:
                    url = str(item.get("href") or item.get("url") or "")
                    if not url.startswith(("http://", "https://")):
                        continue
                    candidate = {
                        "title": str(item.get("title") or url),
                        "url": url,
                        "snippet": str(item.get("body") or item.get("description") or ""),
                        "date": str(item.get("date") or ""),
                        "source": str(item.get("source") or ""),
                        "kind": kind,
                    }
                    candidate_text = " ".join(candidate.values()).lower()
                    if query_terms and not any(term in candidate_text for term in query_terms):
                        continue
                    if "bundesliga" in lowered and not (
                        "bundesliga" in candidate_text or "deutscher meister" in candidate_text
                    ):
                        continue
                    if "bundesliga" in lowered and any(
                        term in candidate_text for term in (
                            "efootball", "frauen-bundesliga", "2. bundesliga",
                            "champions league", "champions-league",
                        )
                    ):
                        continue
                    if any(
                        term in lowered for term in ("wm-finale", "wm finale", "weltmeisterschaft", "world cup")
                    ) and not any(
                        term in candidate_text for term in ("wm", "world cup", "fifa", "weltmeisterschaft")
                    ):
                        continue
                    clean.append(candidate)

        deduplicated: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in clean:
            normalized = item["url"].split("#", 1)[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            item["_score"] = str(_source_score(item, bewertungstext))
            deduplicated.append(item)
        deduplicated.sort(key=lambda item: float(item["_score"]), reverse=True)
        for item in deduplicated:
            item.pop("_score", None)
        return deduplicated[: max(WEB_RESULTS + 3, 8)]

    return await asyncio.to_thread(search)


def _is_public_web_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        return False
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return True


def _extract_page_text(markup: str) -> tuple[str, str]:
    try:
        document = lxml_html.fromstring(markup)
    except (ValueError, TypeError):
        return "", ""
    for element in document.xpath(
        "//script|//style|//noscript|//svg|//nav|//footer|//header|//form|//aside"
    ):
        element.drop_tree()
    title_nodes = document.xpath("//title/text()")
    title = re.sub(r"\s+", " ", title_nodes[0]).strip() if title_nodes else ""
    candidates = document.xpath("//main|//article")
    container = candidates[0] if candidates else document
    text = re.sub(r"\s+", " ", container.text_content()).strip()
    return title, text[:WEB_PAGE_CHARS]


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages[:10]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
        if sum(len(item) for item in parts) >= WEB_PAGE_CHARS:
            break
    return re.sub(r"\s+", " ", "\n".join(parts)).strip()[:WEB_PAGE_CHARS]


def _is_official_authority_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        host == "finanzamt.nrw.de"
        or host.endswith(".finanzamt.nrw.de")
        or host.endswith(".bund.de")
        or host.endswith(".nrw.de")
    )


def extract_verified_authority_recipient(
    prompt: str,
    results: list[dict[str, str]],
) -> dict[str, str]:
    """Extract a German authority address only from an official primary source."""
    target = re.search(
        r"\b(finanzamt)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+"
        r"(?:\s+(?:am|an\s+der|im)\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]+)?)\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if not target:
        return {}
    authority_type = target.group(1).capitalize()
    city = re.sub(r"\s+", " ", target.group(2)).strip()
    authority_name = f"{authority_type} {city}"
    street_pattern = (
        r"(?P<street>(?:"
        r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]*?"
        r"(?:straße|strasse|weg|ring|platz|allee|damm|ufer|gasse|chaussee|"
        r"markt|wall|stieg|kamp|pfad)"
        r"|"
        r"(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.-]*\s+){1,2}"
        r"(?:Feld|Markt|Platz)"
        r")\s+\d+\s*[A-Za-z]?)"
    )
    address_pattern = re.compile(
        street_pattern
        + r"[\s,;|-]+(?P<postal>\d{5})\s+"
        + re.escape(city)
        + r"\b",
        flags=re.IGNORECASE,
    )
    for item in results:
        url = str(item.get("url") or "")
        if not _is_official_authority_url(url):
            continue
        evidence = " ".join(
            str(item.get(key) or "")
            for key in ("title", "snippet", "content")
        )
        evidence = re.sub(r"\s+", " ", evidence)
        match = address_pattern.search(evidence)
        if not match:
            continue
        return {
            "name": authority_name,
            "department": "",
            "street": re.sub(r"\s+", " ", match.group("street")).strip(),
            "postal_code": match.group("postal"),
            "city": city,
            "country": "",
            "source_url": url,
        }
    return {}


async def enrich_web_results(
    results: list[dict[str, str]],
    client: httpx.AsyncClient,
) -> list[dict[str, str]]:
    semaphore = asyncio.Semaphore(4)

    async def fetch(item: dict[str, str]) -> dict[str, str]:
        enriched = dict(item)
        if not await asyncio.to_thread(_is_public_web_url, item["url"]):
            return enriched
        try:
            async with semaphore:
                response = await client.get(
                    item["url"],
                    timeout=httpx.Timeout(12.0),
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 Chrome/125 Safari/537.36"
                        )
                    },
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if len(response.content) > 10 * 1024 * 1024:
                return enriched
            if "pdf" in content_type or item["url"].lower().endswith(".pdf"):
                content = await asyncio.to_thread(_extract_pdf_text, response.content)
                if content:
                    enriched["content"] = content
            elif "html" in content_type:
                page_title, content = await asyncio.to_thread(_extract_page_text, response.text)
                if page_title and not enriched.get("title"):
                    enriched["title"] = page_title
                if content:
                    enriched["content"] = content
        except (httpx.HTTPError, ValueError):
            pass
        return enriched

    return await asyncio.gather(*(fetch(item) for item in results[:8]))


def context_ids_from_json(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def is_media(filename: str, content_type: str = "") -> bool:
    return Path(filename).suffix.lower() in MEDIA_EXTENSIONS or content_type.startswith(
        MEDIA_MIME_PREFIXES
    )
