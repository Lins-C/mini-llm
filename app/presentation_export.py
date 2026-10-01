# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


TEMPLATE_PATH = (
    Path(__file__).resolve().parent
    / "assets"
    / "mini-llm-presentation-template.pptx"
)
TARGET_CONTENT_SLIDES = 7
EMU_PER_PIXEL = 9525

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
R_ID = f"{{{NS['r']}}}id"
SLIDE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
)


@dataclass
class Metric:
    label: str
    value: float
    display: str
    unit: str


@dataclass
class ContentSlide:
    title: str
    points: list[str]
    metrics: list[Metric]
    closing: bool = False


@dataclass
class DeckContent:
    title: str
    subtitle: str
    slides: list[ContentSlide]


def _plain(value: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value or "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _clip(value: str, limit: int) -> str:
    text = _plain(value)
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened} …"


def _clean_slide_title(value: str, fallback: str) -> str:
    text = re.sub(
        r"(?i)^\s*(?:folie|slide)\s*\d*\s*[:.–—-]?\s*",
        "",
        _plain(value),
    )
    return _clip(text or fallback, 80)


def _short_slide_title(value: str, limit: int = 60) -> str:
    text = _plain(value).strip(" .,:;–—-")
    if len(text) <= limit:
        return text
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    words: list[str] = []
    for word in text.split():
        candidate = " ".join([*words, word])
        if words and len(candidate) > limit:
            break
        words.append(word)
    return " ".join(words).strip(" .,:;–—-") or text[:limit].rstrip()


def _takeaway_title(
    title: str,
    points: list[str],
    metrics: list[Metric],
) -> str:
    text = _plain(title)
    lowered = text.lower()
    first_point = points[0] if points else ""
    if re.search(r"\b(?:ausgangslage|ist-zustand|status quo)\b", lowered):
        text = first_point or text
    elif re.search(r"\b(?:belege|kennzahlen|zahlen|analyse)\b", lowered):
        text = first_point or text
    elif re.search(r"\b(?:lösung|vorgehen|pilotkonzept)\b", lowered):
        text = first_point or text
    elif re.search(r"\b(?:risiken?|schutzmaßnahmen|datenschutz)\b", lowered):
        text = "Kontrollen begrenzen die Datenschutzrisiken"
    elif re.search(r"\b(?:kriterien|erfolg|kpi)\b", lowered):
        text = "Klare Zielwerte machen den Piloten messbar"
    elif re.search(r"\b(?:entscheidung|nächste schritte|empfehlung)\b", lowered):
        weeks = next(
            (metric for metric in metrics if metric.unit.startswith("woche")),
            None,
        )
        text = (
            f"Nach {weeks.display} folgt die Skalierungsentscheidung"
            if weeks
            else first_point or text
        )
    return _short_slide_title(text)


def _split_point(value: str, limit: int) -> list[str]:
    text = _plain(value)
    if not text:
        return []
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9])", text)
        if sentence.strip()
    ] or [text]
    result: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        current: list[str] = []
        for word in words:
            candidate = " ".join([*current, word])
            if current and len(candidate) > limit:
                result.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            result.append(" ".join(current))
    return result


NUMBER_PATTERN = re.compile(
    r"(?<![\w/])"
    r"([+-]?(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,\d+)?|[+-]?\d+\.\d+)"
    r"\s*"
    r"(Mrd\.?\s*€|Mio\.?\s*€|Tsd\.?\s*€|Mrd\.?|Mio\.?|Tsd\.?|"
    r"%|€|EUR|USD|km|m²|m3|kg|t|Stunden?|Minuten?|Tage?|Wochen?|"
    r"Monate?|Jahre?|Dokumente?(?:/E-?Mails?)?|E-?Mails?|Vorgänge?|"
    r"Mitarbeitende?|Personen?|Prozesse?)?",
    re.IGNORECASE,
)


def _number_value(raw: str) -> float | None:
    value = raw.replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def _metric_from_text(value: str, table_value: bool = False) -> Metric | None:
    text = re.sub(
        r"^\s*(?:[-+*]|\d+[.)])\s+",
        "",
        _plain(value),
    )
    candidates: list[tuple[re.Match[str], float, str]] = []
    for match in NUMBER_PATTERN.finditer(text):
        number = _number_value(match.group(1))
        unit = re.sub(r"\s+", " ", match.group(2) or "").strip()
        if number is None:
            continue
        if not unit and 1900 <= number <= 2100 and float(number).is_integer():
            continue
        if not unit and not table_value and ":" not in text:
            continue
        prefix = text[max(0, match.start() - 28):match.start()]
        if not unit and re.search(
            r"(?i)\b(?:phase|schritt|kapitel|folie|slide|woche)\s*"
            r"(?:\d+\s*(?:&|und|bis|[-–—])\s*)?$",
            prefix,
        ):
            continue
        candidates.append((match, number, unit))
    if not candidates:
        return None
    match, number, unit = next(
        (item for item in candidates if item[2]),
        candidates[-1],
    )
    label = _plain((text[:match.start()] + " " + text[match.end():]).strip(" :–—-"))
    label = re.sub(
        r"(?i)\b(?:beträgt|liegt bei|von|auf|unter|über)\s*$",
        "",
        label,
    ).strip()
    label = re.sub(
        r"(?i)\b(?:mindestens|maximal|rund|ca\.?|weniger|mehr)\b",
        " ",
        label,
    )
    label = re.sub(r"\s+", " ", label).strip(" :–—-")
    label = re.sub(
        r"(?i)\bautomatisierungsgrad\b",
        "Automatisierung",
        label,
    )
    lowered_unit = unit.lower()
    if lowered_unit.startswith("mitarbeit"):
        label = "Beteiligte am Pilot"
    elif lowered_unit.startswith("woche") and re.search(
        r"(?i)\b(?:auswertung|zeitraum|zeitrahmen|rahmen|dauer|pilot)\b",
        label,
    ):
        label = "Dauer des Pilotbetriebs"
    elif lowered_unit.startswith("dokument"):
        label = re.sub(
            r"(?i)\b(?:volumen|eingänge?|anzahl)\s*:?\s*",
            "",
            label,
        ).strip(" :–—-")
        if not label:
            label = "pro Woche"
    if not label:
        label = "Kennzahl"
    display = _plain(match.group(0))
    return Metric(
        label=_clip(label, 28),
        value=number,
        display=_clip(display, 32),
        unit=lowered_unit,
    )


def _extract_metrics(lines: list[str]) -> list[Metric]:
    metrics: list[Metric] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if "|" in stripped:
            cells = [
                _plain(cell)
                for cell in stripped.strip("|").split("|")
            ]
            if len(cells) > 1 and all(
                re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells
            ):
                in_table = True
                continue
            if in_table or len(cells) > 1:
                for cell in cells[1:]:
                    metric = _metric_from_text(
                        f"{cells[0]}: {cell}",
                        table_value=True,
                    )
                    if metric:
                        metrics.append(metric)
                        break
                in_table = True
                continue
        metric = _metric_from_text(stripped)
        if metric:
            metrics.append(metric)
    deduplicated: list[Metric] = []
    seen: set[tuple[str, str]] = set()
    for metric in metrics:
        key = (metric.label.lower(), metric.display.lower())
        if key not in seen:
            seen.add(key)
            deduplicated.append(metric)
    if not deduplicated:
        return []
    unit_counts: dict[str, int] = {}
    for metric in deduplicated:
        unit_counts[metric.unit] = unit_counts.get(metric.unit, 0) + 1
    preferred_unit = max(unit_counts, key=unit_counts.get)
    same_unit = [metric for metric in deduplicated if metric.unit == preferred_unit]
    # Ein einzelner Wert ist eine Kennzahl, aber kein sinnvoller Balkenvergleich.
    # Bei gemischten Einheiten bleibt deshalb nur der zuerst genannte Hauptwert.
    return (same_unit if len(same_unit) >= 2 else deduplicated[:1])[:5]


def _same_metric(left: Metric | None, right: Metric) -> bool:
    return bool(
        left
        and abs(left.value - right.value) < 0.000001
        and left.unit == right.unit
        and left.display.lower() == right.display.lower()
    )


def _section_points(lines: list[str], metrics: list[Metric]) -> list[str]:
    points: list[str] = []
    table_header: list[str] | None = None
    narrow = bool(metrics)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        if stripped.startswith("|") and "|" in stripped[1:]:
            cells = [_plain(cell) for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
                continue
            if table_header is None and index + 1 < len(lines):
                next_cells = [
                    cell.strip()
                    for cell in lines[index + 1].strip("|").split("|")
                ]
                if next_cells and all(
                    re.fullmatch(r":?-{3,}:?", cell or "") for cell in next_cells
                ):
                    table_header = cells
                    continue
            if table_header:
                row = " · ".join(
                    f"{table_header[cell_index]}: {cell}"
                    for cell_index, cell in enumerate(cells)
                    if cell and cell_index < len(table_header)
                )
                row_metric = _metric_from_text(row, table_value=True)
                if not any(_same_metric(row_metric, metric) for metric in metrics):
                    points.extend(_split_point(row, 140))
                continue
        stripped = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", stripped)
        stripped = re.sub(r"^\s*>\s?", "", stripped)
        stripped = re.sub(r"^\s*#{1,6}\s+", "", stripped)
        line_metric = _metric_from_text(stripped)
        if any(_same_metric(line_metric, metric) for metric in metrics):
            continue
        if narrow and stripped.endswith(":") and re.search(
            r"(?i)\b(?:analyse|aufteilung|verteilung|kennzahlen|zahlen)\b",
            stripped,
        ):
            continue
        points.extend(_split_point(stripped, 82 if narrow else 140))
    return [point for point in points if point]


def _slide_role(slide: ContentSlide) -> str:
    text = slide.title.lower()
    roles = (
        ("context", r"\b(?:ausgang|problem|herausforderung|ist-zustand|ziel)\b"),
        ("evidence", r"\b(?:beleg|kennzahl|zahl|analyse|aufwand|zeithebel)\b"),
        ("solution", r"\b(?:lösung|pilot|vorgehen|umsetzung|automatisierung)\b"),
        ("risk", r"\b(?:risik|schutz|datenschutz|sicherheit)\b"),
        ("success", r"\b(?:erfolg|kriter|kpi|messbar|zielwert)\b"),
        ("decision", r"\b(?:entscheid|empfehl|nächste|ausblick|fazit|skalierung)\b"),
    )
    for role, pattern in roles:
        if re.search(pattern, text):
            return role
    return "other"


def _slide_score(slide: ContentSlide, index: int, total: int) -> int:
    score = min(4, len(slide.points))
    score += min(4, len(slide.metrics) * 2)
    if "fortsetzung" not in slide.title.lower():
        score += 2
    if index in {0, total - 1}:
        score += 2
    if _slide_role(slide) in {"decision", "success", "solution"}:
        score += 2
    return score


def _condense_slides(
    slides: list[ContentSlide],
    limit: int = TARGET_CONTENT_SLIDES,
) -> list[ContentSlide]:
    if len(slides) <= limit:
        return slides

    total = len(slides)
    selected: set[int] = {0, total - 1}
    narrative_roles = (
        "context",
        "evidence",
        "solution",
        "risk",
        "success",
        "decision",
    )
    for role in narrative_roles:
        candidates = [
            index for index, slide in enumerate(slides)
            if _slide_role(slide) == role
        ]
        if not candidates:
            continue
        best = max(
            candidates,
            key=lambda index: _slide_score(slides[index], index, total),
        )
        selected.add(best)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        remaining = [
            index for index in range(total)
            if index not in selected
        ]
        remaining.sort(
            key=lambda index: (
                _slide_score(slides[index], index, total),
                -abs(index - (total / 2)),
            ),
            reverse=True,
        )
        selected.update(remaining[:limit - len(selected)])

    ordered = [slides[index] for index in sorted(selected)[:limit]]
    if ordered:
        final_role = _slide_role(ordered[-1])
        ordered[-1].closing = final_role == "decision"
    return ordered


def parse_presentation_content(title: str, content: str) -> DeckContent:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^```(?:markdown|md|text)?\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    lines = text.splitlines()

    deck_title = _clip(title, 110)
    subtitle = ""
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    preface: list[str] = []

    def flush_section() -> None:
        nonlocal current_lines
        if current_title or current_lines:
            sections.append((
                current_title or f"Kernaussage {len(sections) + 1}",
                current_lines,
            ))
        current_lines = []

    for line in lines:
        heading = re.match(r"^\s*(#{1,3})\s+(.+?)\s*#*\s*$", line)
        if heading and len(heading.group(1)) == 1 and not sections and not current_title:
            deck_title = _clip(heading.group(2), 110)
            continue
        if heading and len(heading.group(1)) >= 2:
            flush_section()
            current_title = _clean_slide_title(
                heading.group(2),
                f"Kernaussage {len(sections) + 1}",
            )
            continue
        if current_title:
            current_lines.append(line)
        elif line.strip():
            preface.append(line)

    flush_section()
    if preface:
        first_preface = _plain(re.sub(r"^\s*>\s?", "", preface[0]))
        if sections and len(first_preface) <= 180:
            subtitle = first_preface
            preface = preface[1:]
        if preface or not sections:
            sections.insert(0, ("Überblick", preface))
    if not subtitle:
        subtitle = (
            f"Entscheidungsvorlage · {sections[0][0]}"
            if sections
            else "Entscheidungsvorlage"
        )

    slides: list[ContentSlide] = []
    for section_title, section_lines in sections:
        metrics = _extract_metrics(section_lines)
        points = _section_points(section_lines, metrics)
        if not points and metrics:
            strongest = max(metrics, key=lambda metric: abs(metric.value))
            points = [
                f"Der größte ausgewiesene Hebel liegt bei {strongest.label}."
            ]
        if not points:
            continue
        for offset in range(0, len(points), 5):
            chunk = points[offset:offset + 5]
            continuation = offset > 0
            slide_title = (
                _clip(f"{section_title} – Fortsetzung", 80)
                if continuation
                else section_title
            )
            closing = bool(re.search(
                r"(?i)\b(?:fazit|abschluss|nächste schritte|empfehlung|ausblick)\b",
                section_title,
            )) and not continuation and len(chunk) <= 2
            slide_title = _takeaway_title(slide_title, chunk, metrics)
            if (
                len(chunk) > 1
                and _plain(chunk[0]).rstrip(" .").casefold()
                == _plain(slide_title).rstrip(" .").casefold()
            ):
                chunk = chunk[1:]
            slides.append(ContentSlide(
                title=slide_title,
                points=chunk,
                metrics=metrics if not continuation else [],
                closing=closing,
            ))

    if not slides:
        slides = [ContentSlide(
            title="Kernaussage",
            points=["Der ausgewählte Inhalt enthält keinen darstellbaren Text."],
            metrics=[],
        )]
    slides = _condense_slides(slides)
    return DeckContent(
        title=deck_title or "Mini LLM Präsentation",
        subtitle=_clip(subtitle, 155),
        slides=slides,
    )


def _shape(root: etree._Element, name: str) -> etree._Element | None:
    for marker in root.xpath(".//p:cNvPr", namespaces=NS):
        if marker.get("name") == name:
            parent = marker.getparent()
            return parent.getparent() if parent is not None else None
    return None


def _set_text(root: etree._Element, name: str, value: str) -> None:
    shape = _shape(root, name)
    if shape is None:
        raise ValueError(f"PPTX-Vorlage enthält das Feld {name!r} nicht.")
    texts = shape.xpath(".//a:t", namespaces=NS)
    if not texts:
        raise ValueError(f"PPTX-Feld {name!r} besitzt keinen Textlauf.")
    texts[0].text = value
    for item in texts[1:]:
        item.text = ""


def _set_font_size(root: etree._Element, name: str, points: float) -> None:
    shape = _shape(root, name)
    if shape is None:
        return
    size = str(max(1, int(points * 100)))
    for node in shape.xpath(
        ".//a:rPr | .//a:defRPr | .//a:endParaRPr",
        namespaces=NS,
    ):
        node.set("sz", size)


def _hide(root: etree._Element, name: str) -> None:
    shape = _shape(root, name)
    if shape is None:
        return
    marker = shape.find("./p:nvSpPr/p:cNvPr", namespaces=NS)
    if marker is not None:
        marker.set("hidden", "1")
    for text in shape.xpath(".//a:t", namespaces=NS):
        text.text = ""
    extent = shape.find("./p:spPr/a:xfrm/a:ext", namespaces=NS)
    if extent is not None:
        extent.set("cx", "0")
        extent.set("cy", "0")


def _set_width(root: etree._Element, name: str, pixels: float) -> None:
    shape = _shape(root, name)
    if shape is None:
        return
    extent = shape.find("./p:spPr/a:xfrm/a:ext", namespaces=NS)
    if extent is not None:
        extent.set("cx", str(max(1, int(pixels * EMU_PER_PIXEL))))


def _fill_bullets(
    root: etree._Element,
    points: list[str],
    wide: bool,
) -> None:
    for index in range(1, 6):
        if index <= len(points):
            _set_text(root, f"bullet-{index}", points[index - 1])
            if wide:
                _set_width(root, f"bullet-{index}", 1032)
        else:
            _hide(root, f"bullet-{index}")
            _hide(root, f"bullet-dot-{index}")


def _fill_chart(
    root: etree._Element,
    metrics: list[Metric],
    slide_title: str = "",
) -> None:
    if len(metrics) == 1:
        metric = metrics[0]
        prominent_value = metric.display
        prominent_label = metric.label
        if len(prominent_value) > 14:
            number_match = re.match(
                r"^\s*([+-]?(?:\d[\d.\s]*)(?:,\d+)?)\s*(.*)$",
                prominent_value,
            )
            if number_match:
                prominent_value = number_match.group(1).strip()
                unit_label = number_match.group(2).strip()
                if unit_label:
                    prominent_label = f"{unit_label} · {prominent_label}"
        _set_text(root, "chart-title", "Zentrale Kennzahl")
        _set_text(root, "metric-big-value", prominent_value)
        _set_text(root, "metric-big-label", _clip(prominent_label, 46))
        for index in range(1, 6):
            for prefix in ("chart-label", "chart-track", "chart-bar", "chart-value"):
                _hide(root, f"{prefix}-{index}")
        return

    _hide(root, "metric-big-value")
    _hide(root, "metric-big-label")
    max_value = max((abs(metric.value) for metric in metrics), default=1.0) or 1.0
    comparable = len({metric.unit for metric in metrics}) <= 1
    unit = metrics[0].unit if metrics else ""
    title = "Kennzahlen im Überblick"
    if re.search(r"(?i)\b(?:zielwert|messbar|erfolg|kriter)\b", slide_title):
        title = "Zielwerte im Überblick"
    elif comparable and unit:
        title = f"Vergleich in {unit.title() if unit != '%' else '%'}"
    _set_text(root, "chart-title", title)
    for index in range(1, 6):
        if index <= len(metrics):
            metric = metrics[index - 1]
            _set_text(root, f"chart-label-{index}", metric.label)
            _set_text(root, f"chart-value-{index}", metric.display)
            ratio = abs(metric.value) / max_value if comparable else 0.72
            _set_width(root, f"chart-bar-{index}", max(18, 210 * max(0.08, ratio)))
        else:
            for prefix in ("chart-label", "chart-track", "chart-bar", "chart-value"):
                _hide(root, f"{prefix}-{index}")


def _hide_chart(root: etree._Element) -> None:
    _hide(root, "chart-frame")
    _hide(root, "chart-title")
    _hide(root, "metric-big-value")
    _hide(root, "metric-big-label")
    for index in range(1, 6):
        for prefix in ("chart-label", "chart-track", "chart-bar", "chart-value"):
            _hide(root, f"{prefix}-{index}")


def _fill_title_slide(xml: bytes, deck: DeckContent, author: str = "") -> bytes:
    root = etree.fromstring(xml)
    _set_text(root, "deck-title", deck.title)
    _set_font_size(
        root,
        "deck-title",
        54 if len(deck.title) <= 58 else 50 if len(deck.title) <= 85 else 46,
    )
    _set_text(root, "deck-subtitle", deck.subtitle)
    _set_text(root, "deck-date", f"Stand: {date.today().strftime('%d.%m.%Y')}")
    if author:
        _set_text(root, "deck-author", _clip(author, 80))
    else:
        _hide(root, "deck-author-label")
        _hide(root, "deck-author")
    _set_text(root, "slide-number", "01")
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _fill_content_slide(
    xml: bytes,
    slide: ContentSlide,
    display_index: int,
    with_chart: bool,
) -> bytes:
    root = etree.fromstring(xml)
    _set_text(root, "slide-kicker", f"KAPITEL {display_index:02d}")
    _set_text(root, "slide-title", _clip(slide.title, 80))
    _set_font_size(root, "slide-title", 38 if len(slide.title) <= 52 else 32)
    _set_text(root, "slide-index", f"{display_index:02d}")
    _set_text(root, "slide-number", f"{display_index + 1:02d}")
    _fill_bullets(root, slide.points, wide=not with_chart)
    if with_chart:
        _fill_chart(root, slide.metrics, slide.title)
    else:
        _hide_chart(root)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _fill_closing_slide(
    xml: bytes,
    slide: ContentSlide,
    display_index: int,
) -> bytes:
    root = etree.fromstring(xml)
    _set_text(root, "closing-title", _clip(slide.title, 68))
    _set_text(root, "closing-body", _clip(" ".join(slide.points), 220))
    _set_text(
        root,
        "closing-metric",
        slide.metrics[0].display if slide.metrics else "NÄCHSTER SCHRITT",
    )
    _set_text(root, "slide-number", f"{display_index + 1:02d}")
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _slide_relationships(
    relationship_xml: bytes,
) -> tuple[etree._Element, dict[str, tuple[str, str]]]:
    root = etree.fromstring(relationship_xml.lstrip(b"\xef\xbb\xbf"))
    relationships: dict[str, tuple[str, str]] = {}
    for item in root.findall("pr:Relationship", namespaces=NS):
        if item.get("Type") == SLIDE_REL_TYPE:
            target = (item.get("Target") or "").lstrip("/")
            relationships[target] = (item.get("Id") or "", item.get("Target") or "")
    return root, relationships


def _prune_presentation_relationships(
    root: etree._Element,
    selected_parts: set[str],
) -> bytes:
    for item in list(root):
        if item.get("Type") != SLIDE_REL_TYPE:
            continue
        target = (item.get("Target") or "").lstrip("/")
        if target not in selected_parts:
            root.remove(item)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _prune_content_types(xml: bytes, selected_numbers: set[int]) -> bytes:
    root = etree.fromstring(xml)
    for item in list(root):
        part_name = item.get("PartName") or ""
        match = re.fullmatch(
            r"/ppt/(?:slides/slide|notesSlides/notesSlide)(\d+)\.xml",
            part_name,
        )
        if match and int(match.group(1)) not in selected_numbers:
            root.remove(item)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _unused_slide_entry(filename: str, selected_numbers: set[int]) -> bool:
    match = re.fullmatch(
        r"ppt/(?:"
        r"slides/slide|slides/_rels/slide|"
        r"notesSlides/notesSlide|notesSlides/_rels/notesSlide"
        r")(\d+)\.xml(?:\.rels)?",
        filename,
    )
    return bool(match and int(match.group(1)) not in selected_numbers)


def _select_slide_parts(deck: DeckContent) -> list[tuple[str, ContentSlide | None, bool]]:
    # Die hervorgehobenen Textvarianten werden zuerst eingesetzt, damit auch
    # kurze Decks visuell mehr als eine einzige Folien-Silhouette erhalten.
    standard_parts = [
        "ppt/slides/slide3.xml",
        "ppt/slides/slide2.xml",
        "ppt/slides/slide5.xml",
        "ppt/slides/slide4.xml",
        "ppt/slides/slide6.xml",
    ]
    chart_parts = [f"ppt/slides/slide{index}.xml" for index in range(7, 12)]
    result: list[tuple[str, ContentSlide | None, bool]] = [
        ("ppt/slides/slide1.xml", None, False)
    ]
    for index, slide in enumerate(deck.slides):
        if slide.closing and index == len(deck.slides) - 1:
            result.append(("ppt/slides/slide12.xml", slide, False))
        elif slide.metrics and chart_parts:
            result.append((chart_parts.pop(0), slide, True))
        elif standard_parts:
            result.append((standard_parts.pop(0), slide, False))
        elif chart_parts:
            result.append((chart_parts.pop(0), slide, False))
        else:
            raise ValueError("Die Präsentation enthält zu viele Folien.")
    return result


def _update_presentation_order(
    presentation_xml: bytes,
    relationships: dict[str, tuple[str, str]],
    selected_parts: list[str],
) -> bytes:
    root = etree.fromstring(presentation_xml)
    slide_list = root.find("p:sldIdLst", namespaces=NS)
    if slide_list is None:
        raise ValueError("PPTX-Vorlage enthält keine Folienliste.")
    original_by_relationship = {
        item.get(R_ID): copy.deepcopy(item)
        for item in slide_list.findall("p:sldId", namespaces=NS)
    }
    for item in list(slide_list):
        slide_list.remove(item)
    for part in selected_parts:
        relationship_id = relationships.get(part, ("", ""))[0]
        source = original_by_relationship.get(relationship_id)
        if source is None:
            raise ValueError(f"PPTX-Vorlage enthält keine Beziehung für {part}.")
        slide_list.append(source)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _update_app_properties(xml: bytes, slide_count: int) -> bytes:
    root = etree.fromstring(xml)
    namespace = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
    node = root.find("ep:Slides", namespaces=namespace)
    if node is not None:
        node.text = str(slide_count)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def _update_core_properties(xml: bytes, author: str) -> bytes:
    if not author:
        return xml
    root = etree.fromstring(xml)
    namespaces = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    }
    creator = root.find("dc:creator", namespaces=namespaces)
    if creator is None:
        creator = etree.SubElement(root, f"{{{namespaces['dc']}}}creator")
    creator.text = author
    modified_by = root.find("cp:lastModifiedBy", namespaces=namespaces)
    if modified_by is None:
        modified_by = etree.SubElement(
            root,
            f"{{{namespaces['cp']}}}lastModifiedBy",
        )
    modified_by.text = author
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def validate_presentation_bytes(payload: bytes, expected_slides: int) -> None:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            required = {
                "[Content_Types].xml",
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
            }
            if not required.issubset(set(archive.namelist())):
                raise ValueError("Die erzeugte PPTX-Datei ist unvollständig.")
            presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
            slide_ids = presentation.xpath("./p:sldIdLst/p:sldId", namespaces=NS)
            if len(slide_ids) != expected_slides:
                raise ValueError("Die erzeugte PPTX-Datei enthält eine falsche Folienzahl.")
            _, relationships = _slide_relationships(
                archive.read("ppt/_rels/presentation.xml.rels")
            )
            part_by_relationship = {
                relationship_id: part
                for part, (relationship_id, _target) in relationships.items()
            }
            selected_parts = [
                part_by_relationship.get(item.get(R_ID) or "", "")
                for item in slide_ids
            ]
            selected_xml = b"".join(
                archive.read(name)
                for name in selected_parts
                if name in archive.namelist()
            )
            if b"Titel der Pr" in selected_xml or b"Inhalt " in selected_xml:
                raise ValueError("Die Präsentation enthält noch Vorlagen-Platzhalter.")
    except (etree.XMLSyntaxError, KeyError) as exc:
        raise ValueError("Die erzeugte PPTX-Datei ist technisch ungültig.") from exc


def build_pptx(title: str, content: str, author: str = "") -> bytes:
    if not TEMPLATE_PATH.is_file():
        raise ValueError("Die PPTX-Vorlage ist nicht installiert.")
    author = _clip(author, 80) if author else ""
    deck = parse_presentation_content(title, content)
    selected = _select_slide_parts(deck)
    selected_parts = [item[0] for item in selected]
    selected_part_set = set(selected_parts)
    selected_numbers = {
        int(re.search(r"slide(\d+)\.xml$", part).group(1))
        for part in selected_parts
    }

    output = BytesIO()
    with ZipFile(TEMPLATE_PATH, "r") as source, ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
    ) as target:
        relationship_root, relationships = _slide_relationships(
            source.read("ppt/_rels/presentation.xml.rels")
        )
        relationship_xml = _prune_presentation_relationships(
            relationship_root,
            selected_part_set,
        )
        presentation_xml = _update_presentation_order(
            source.read("ppt/presentation.xml"),
            relationships,
            selected_parts,
        )
        for entry in source.infolist():
            if _unused_slide_entry(entry.filename, selected_numbers):
                continue
            data = source.read(entry.filename)
            if entry.filename == "ppt/presentation.xml":
                data = presentation_xml
            elif entry.filename == "ppt/_rels/presentation.xml.rels":
                data = relationship_xml
            elif entry.filename == "[Content_Types].xml":
                data = _prune_content_types(data, selected_numbers)
            elif entry.filename == "docProps/app.xml":
                data = _update_app_properties(data, len(selected_parts))
            elif entry.filename == "docProps/core.xml":
                data = _update_core_properties(data, author)
            elif entry.filename == "ppt/slides/slide1.xml":
                data = _fill_title_slide(data, deck, author)
            else:
                selected_match = next(
                    (
                        (slide, with_chart, index)
                        for index, (part, slide, with_chart) in enumerate(selected[1:], 1)
                        if part == entry.filename and slide is not None
                    ),
                    None,
                )
                if selected_match:
                    slide, with_chart, display_index = selected_match
                    if slide.closing and entry.filename == "ppt/slides/slide12.xml":
                        data = _fill_closing_slide(data, slide, display_index)
                    else:
                        data = _fill_content_slide(
                            data,
                            slide,
                            display_index,
                            with_chart,
                        )
            target.writestr(entry, data)

    payload = output.getvalue()
    validate_presentation_bytes(payload, len(selected_parts))
    return payload
