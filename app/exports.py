# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import html
import unicodedata
import re
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Image,
    CondPageBreak,
    KeepTogether,
)

from app.task_skills import normalize_letter_artifact
from app.presentation_export import build_pptx


NAVY = "0D2742"
BLUE = "377CF6"
PALE_BLUE = "EAF1FB"
MUTED = "5D6B78"
MAX_EXPORT_CHARS = 1_000_000


LOGO_CANDIDATES = ("logo.png", "logo.jpg", "logo.jpeg")


def logo_path() -> Path | None:
    """Optionales Logo für Kopfzeilen: app/assets/logo.png (oder .jpg).

    Ohne diese Datei bleibt jedes Dokument exakt so, wie es vorher war.
    """

    assets = Path(__file__).resolve().parent / "assets"
    for name in LOGO_CANDIDATES:
        candidate = assets / name
        if candidate.is_file():
            return candidate
    return None


def _logo_size(path: Path, max_width_mm: float, max_height_mm: float) -> tuple[float, float]:
    """Skaliert das Logo seitenverhältnistreu in den erlaubten Rahmen."""

    try:
        from reportlab.lib.utils import ImageReader

        width, height = ImageReader(str(path)).getSize()
    except Exception:
        return max_width_mm, max_height_mm
    if not width or not height:
        return max_width_mm, max_height_mm
    scale = min(max_width_mm / width, max_height_mm / height)
    return width * scale, height * scale


# Die Standardschriften im PDF können nur cp1252. Alles darüber hinaus druckt
# reportlab als schwarzes Kästchen — aus „Z‑Außenlager“ wird „Z■Außenlager“.
# Deshalb werden solche Zeichen vorher auf druckbare Entsprechungen abgebildet.
PDF_ZEICHENERSATZ = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-",
    "\u2007": " ", "\u2008": " ", "\u2009": " ", "\u200a": " ", "\u202f": " ",
    "\u200b": "", "\u2060": "", "\ufeff": "", "\u00ad": "",
    "\u2248": "ca.", "\u2264": "<=", "\u2265": ">=", "\u2260": "!=",
    "\u2192": "->", "\u2190": "<-", "\u2194": "<->", "\u21d2": "=>",
    "\u2713": "+", "\u2714": "+", "\u2717": "x", "\u2718": "x",
    "\u2116": "Nr.", "\u2044": "/", "\u2033": '"', "\u2032": "'",
}


def pdf_safe_text(value: Any) -> str:
    """Ersetzt Zeichen, die die PDF-Schrift nicht kennt."""

    text = str(value or "")
    for zeichen, ersatz in PDF_ZEICHENERSATZ.items():
        text = text.replace(zeichen, ersatz)
    try:
        text.encode("cp1252")
        return text
    except UnicodeEncodeError:
        pass
    # Für den Rest zuerst die Zerlegung versuchen (é → e), sonst weglassen.
    zeichenkette = []
    for zeichen in text:
        try:
            zeichen.encode("cp1252")
            zeichenkette.append(zeichen)
            continue
        except UnicodeEncodeError:
            pass
        zerlegt = "".join(
            teil for teil in unicodedata.normalize("NFKD", zeichen)
            if not unicodedata.combining(teil)
        )
        for teil in zerlegt:
            try:
                teil.encode("cp1252")
                zeichenkette.append(teil)
            except UnicodeEncodeError:
                continue
    return "".join(zeichenkette)


def safe_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned[:120] or "Mini LLM Antwort"


def safe_filename(value: str) -> str:
    replacements = str.maketrans({
        "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe",
        "Ü": "Ue", "ß": "ss",
    })
    slug = safe_title(value).translate(replacements)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-._")
    return (slug[:80] or "mini-llm-antwort").lower()


def strip_inline_markdown(value: str) -> str:
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"(\*\*|__)(.*?)\1", r"\2", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", value)
    value = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", value)
    return value.strip()


def table_cells(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [strip_inline_markdown(cell.strip()) for cell in value.split("|")]


def is_table_divider(line: str) -> bool:
    cells = table_cells(line)
    return len(cells) > 1 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_markdown(markdown: str) -> list[dict[str, Any]]:
    markdown = (markdown or "")[:MAX_EXPORT_CHARS].replace("\r\n", "\n").replace("\r", "\n")
    lines = markdown.split("\n")
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    code_language = ""
    in_code = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append({
                "type": "paragraph",
                "text": strip_inline_markdown(" ".join(line.strip() for line in paragraph)),
            })
            paragraph = []

    index = 0
    while index < len(lines):
        line = lines[index]
        fence = re.fullmatch(r"\s*```([\w+-]*)\s*", line)
        if fence:
            flush_paragraph()
            if in_code:
                blocks.append({
                    "type": "code",
                    "language": code_language,
                    "text": "\n".join(code_lines),
                })
                code_lines = []
                code_language = ""
                in_code = False
            else:
                in_code = True
                code_language = fence.group(1) or ""
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if "|" in line and index + 1 < len(lines) and is_table_divider(lines[index + 1]):
            flush_paragraph()
            headers = table_cells(line)
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                row = table_cells(lines[index])
                rows.append((row + [""] * len(headers))[:len(headers)])
                index += 1
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue
        heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
        unordered = re.match(r"^\s*[-+*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        quote = re.match(r"^\s*>\s?(.+)$", line)
        if not line.strip():
            flush_paragraph()
        elif heading:
            flush_paragraph()
            blocks.append({
                "type": "heading",
                "level": len(heading.group(1)),
                "text": strip_inline_markdown(heading.group(2)),
            })
        elif unordered or ordered:
            flush_paragraph()
            # Die Nummer stammt aus der Vorlage. Ohne sie bekäme jeder Punkt
            # dieselbe Ziffer — im PDF stand bisher überall „1.“.
            nummer = 0
            if ordered:
                gezaehlt = re.match(r"^\s*(\d+)", line)
                vorher = blocks[-1] if blocks else None
                fortsetzung = (
                    isinstance(vorher, dict)
                    and vorher.get("type") == "list"
                    and vorher.get("ordered")
                )
                nummer = int(gezaehlt.group(1)) if gezaehlt else 1
                if fortsetzung and nummer == 1 and vorher.get("index", 0) >= 1:
                    nummer = int(vorher["index"]) + 1
            blocks.append({
                "type": "list",
                "ordered": bool(ordered),
                "index": nummer,
                "text": strip_inline_markdown((unordered or ordered).group(1)),
            })
        elif quote:
            flush_paragraph()
            blocks.append({"type": "quote", "text": strip_inline_markdown(quote.group(1))})
        elif re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            flush_paragraph()
            blocks.append({"type": "rule"})
        else:
            paragraph.append(line)
        index += 1

    flush_paragraph()
    if in_code and code_lines:
        blocks.append({"type": "code", "language": code_language, "text": "\n".join(code_lines)})
    return blocks


def _repeat_header_row(row: Any) -> None:
    """Die Kopfzeile einer Tabelle wiederholt sich auf jeder Folgeseite."""

    eigenschaften = row._tr.get_or_add_trPr()
    kopf = OxmlElement("w:tblHeader")
    kopf.set(qn("w:val"), "true")
    eigenschaften.append(kopf)


def _keep_row_together(row: Any) -> None:
    """Eine Tabellenzeile wird nicht über den Seitenumbruch zerrissen."""

    eigenschaften = row._tr.get_or_add_trPr()
    zusammen = OxmlElement("w:cantSplit")
    eigenschaften.append(zusammen)


def _set_cell_shading(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def build_docx(title: str, content: str) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string("202B35")
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.15

    logo = logo_path()
    if logo is not None:
        logo_paragraph = document.add_paragraph()
        logo_paragraph.paragraph_format.space_after = Pt(10)
        try:
            logo_paragraph.add_run().add_picture(str(logo), height=Cm(1.2))
        except Exception:
            # Ein unlesbares Logo darf das Dokument nicht verhindern.
            logo_paragraph.text = ""

    title_paragraph = document.add_paragraph()
    title_paragraph.paragraph_format.space_after = Pt(16)
    run = title_paragraph.add_run(safe_title(title))
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(22)
    run.font.color.rgb = RGBColor.from_string(NAVY)

    for level in range(1, 4):
        style = document.styles[f"Heading {level}"]
        style.font.name = "Arial"
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(NAVY)
        # Word soll eine Überschrift nie allein am Seitenfuß stehen lassen.
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True
        style.font.size = Pt({1: 17, 2: 14, 3: 12}[level])

    for block in parse_markdown(content):
        kind = block["type"]
        if kind == "heading":
            document.add_heading(block["text"], level=min(3, block["level"]))
        elif kind == "paragraph":
            document.add_paragraph(block["text"])
        elif kind == "list":
            if block["ordered"]:
                # Word zählt über das ganze Dokument weiter; deshalb wird die
                # Nummer der Vorlage geschrieben.
                absatz = document.add_paragraph()
                absatz.paragraph_format.left_indent = Cm(0.75)
                absatz.paragraph_format.first_line_indent = Cm(-0.5)
                absatz.paragraph_format.space_after = Pt(3)
                absatz.add_run(f"{block.get('index') or 1}. {block['text']}")
            else:
                document.add_paragraph(block["text"], style="List Bullet")
        elif kind == "quote":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.5)
            paragraph.paragraph_format.space_before = Pt(4)
            paragraph.paragraph_format.space_after = Pt(9)
            quote_run = paragraph.add_run(block["text"])
            quote_run.italic = True
            quote_run.font.color.rgb = RGBColor.from_string(MUTED)
        elif kind == "code":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(5)
            paragraph.paragraph_format.space_after = Pt(10)
            _set_cell_shading_like_paragraph(paragraph, "F1F4F7")
            code_run = paragraph.add_run(block["text"])
            code_run.font.name = "Courier New"
            code_run.font.size = Pt(8)
        elif kind == "rule":
            paragraph = document.add_paragraph(" ")
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.space_after = Pt(5)
            borders = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:color"), "D8E0E8")
            borders.append(bottom)
            paragraph._p.get_or_add_pPr().append(borders)
        elif kind == "table":
            headers = block["headers"]
            rows = block["rows"]
            table = document.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            table.autofit = True
            _repeat_header_row(table.rows[0])
            for index, value in enumerate(headers):
                cell = table.rows[0].cells[index]
                cell.text = value
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                _set_cell_shading(cell, NAVY)
                for cell_run in cell.paragraphs[0].runs:
                    cell_run.bold = True
                    cell_run.font.color.rgb = RGBColor(255, 255, 255)
                    cell_run.font.size = Pt(9)
            for row_index, values in enumerate(rows):
                zeile = table.add_row()
                _keep_row_together(zeile)
                cells = zeile.cells
                for index, value in enumerate(values):
                    cells[index].text = value
                    cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    if row_index % 2:
                        _set_cell_shading(cells[index], "F5F8FC")
                    for paragraph in cells[index].paragraphs:
                        paragraph.paragraph_format.space_after = Pt(0)
                        for cell_run in paragraph.runs:
                            cell_run.font.size = Pt(8.5)
            document.add_paragraph().paragraph_format.space_after = Pt(2)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("Erstellt mit Mini LLM")
    footer_run.font.name = "Arial"
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor.from_string(MUTED)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _letter_address_lines(
    value: dict[str, Any],
    include_contact: bool = False,
) -> list[str]:
    city_line = " ".join(filter(None, [
        str(value.get("postal_code") or "").strip(),
        str(value.get("city") or "").strip(),
    ]))
    lines = [
        str(value.get("name") or "").strip(),
        str(value.get("department") or "").strip(),
        str(value.get("street") or "").strip(),
        city_line,
        str(value.get("country") or "").strip(),
    ]
    if include_contact:
        email = str(value.get("email") or "").strip()
        phone = str(value.get("phone") or "").strip()
        if email:
            lines.append(email)
        if phone:
            lines.append(phone)
    return [line for line in lines if line]


def _remove_docx_table_borders(table: Any) -> None:
    properties = table._tbl.tblPr
    borders = properties.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "nil")


def build_letter_docx(artifact: dict[str, Any]) -> bytes:
    letter = normalize_letter_artifact(artifact)
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string("202B35")
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.15

    header = document.add_table(rows=1, cols=2)
    header.alignment = WD_TABLE_ALIGNMENT.CENTER
    header.autofit = False
    header.columns[0].width = Cm(8.0)
    header.columns[1].width = Cm(8.0)
    _remove_docx_table_borders(header)
    recipient_cell, sender_cell = header.rows[0].cells
    recipient_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    sender_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    recipient_label = recipient_cell.paragraphs[0]
    recipient_label.paragraph_format.space_after = Pt(5)
    label_run = recipient_label.add_run("EMPFÄNGER")
    label_run.bold = True
    label_run.font.name = "Arial"
    label_run.font.size = Pt(7)
    label_run.font.color.rgb = RGBColor.from_string(MUTED)
    for line in _letter_address_lines(letter["recipient"]):
        paragraph = recipient_cell.add_paragraph(line)
        paragraph.paragraph_format.space_after = Pt(1)

    sender_label = sender_cell.paragraphs[0]
    sender_label.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    sender_label.paragraph_format.space_after = Pt(5)
    label_run = sender_label.add_run("ABSENDER")
    label_run.bold = True
    label_run.font.name = "Arial"
    label_run.font.size = Pt(7)
    label_run.font.color.rgb = RGBColor.from_string(MUTED)
    for line in _letter_address_lines(letter["sender"], include_contact=True):
        paragraph = sender_cell.add_paragraph(line)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph.paragraph_format.space_after = Pt(1)

    date_paragraph = document.add_paragraph()
    date_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    date_paragraph.paragraph_format.space_before = Pt(15)
    date_paragraph.paragraph_format.space_after = Pt(15)
    date_paragraph.add_run(letter["date"])

    if letter["reference"]:
        reference = document.add_paragraph()
        reference.paragraph_format.space_after = Pt(5)
        run = reference.add_run(f"Aktenzeichen: {letter['reference']}")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor.from_string(MUTED)

    subject = document.add_paragraph()
    subject.paragraph_format.space_after = Pt(17)
    subject_run = subject.add_run(f"Betreff: {letter['subject']}")
    subject_run.bold = True
    subject_run.font.size = Pt(12)
    subject_run.font.color.rgb = RGBColor.from_string(NAVY)

    salutation = document.add_paragraph(letter["salutation"])
    salutation.paragraph_format.space_after = Pt(11)
    for value in letter["paragraphs"]:
        paragraph = document.add_paragraph(value)
        paragraph.paragraph_format.space_after = Pt(10)

    closing = document.add_paragraph()
    closing.paragraph_format.space_before = Pt(15)
    closing.paragraph_format.space_after = Pt(26)
    closing.add_run(letter["closing"])
    signature = document.add_paragraph(letter["signature"])
    signature.paragraph_format.space_after = Pt(0)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _set_cell_shading_like_paragraph(paragraph: Any, fill: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _pdf_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6D7985"))
    canvas.drawString(20 * mm, 12 * mm, "Erstellt mit Mini LLM")
    canvas.drawRightString(
        document.pagesize[0] - 20 * mm,
        12 * mm,
        f"Seite {document.page}",
    )
    canvas.restoreState()


def build_pdf(title: str, content: str) -> bytes:
    output = BytesIO()
    title = pdf_safe_text(title)
    blocks = parse_markdown(pdf_safe_text(content))
    page_size = (
        landscape(A4)
        if any(
            block["type"] == "table" and len(block["headers"]) > 5
            for block in blocks
        )
        else A4
    )
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=19 * mm,
        bottomMargin=20 * mm,
        title=safe_title(title),
        author="Mini LLM",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="MiniTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=colors.HexColor(f"#{NAVY}"),
        alignment=TA_LEFT,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="MiniBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#202B35"),
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="MiniTableHeader",
        parent=styles["MiniBody"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="MiniTableCell",
        parent=styles["MiniBody"],
        fontSize=8,
        leading=10,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="MiniQuote",
        parent=styles["MiniBody"],
        leftIndent=12,
        textColor=colors.HexColor(f"#{MUTED}"),
        borderColor=colors.HexColor(f"#{BLUE}"),
        borderWidth=1.5,
        borderPadding=7,
        spaceBefore=4,
        spaceAfter=10,
    ))
    for level, size in ((1, 17), (2, 14), (3, 12)):
        styles.add(ParagraphStyle(
            name=f"MiniHeading{level}",
            parent=styles[f"Heading{level}"],
            fontName="Helvetica-Bold",
            fontSize=size,
            leading=size + 4,
            textColor=colors.HexColor(f"#{NAVY}"),
            spaceBefore=(16 if level == 1 else 13 if level == 2 else 10),
            spaceAfter=(8 if level == 1 else 6),
            # Eine Überschrift ohne ihren Text am Seitenfuß ist ein Fehler.
            keepWithNext=1,
        ))

    story: list[Any] = []
    logo = logo_path()
    if logo is not None:
        width, height = _logo_size(logo, 34 * mm, 14 * mm)
        story.append(Image(str(logo), width=width, height=height, hAlign="LEFT"))
        story.append(Spacer(1, 8))
    story.append(Paragraph(html.escape(safe_title(title)), styles["MiniTitle"]))
    for position, block in enumerate(blocks):
        kind = block["type"]
        naechster = blocks[position + 1] if position + 1 < len(blocks) else None
        vorheriger = blocks[position - 1] if position else None
        if kind == "heading":
            # Ein Abschnitt beginnt lieber auf der neuen Seite, als unten noch
            # einen Stummel zu setzen.
            ebene = min(3, block["level"])
            platz = 46 if ebene == 1 else 34 if ebene == 2 else 24
            if naechster and naechster["type"] == "table":
                # Überschrift und Tabelle gehören zusammen auf eine Seite.
                platz = max(platz, 64)
            story.append(CondPageBreak(platz * mm))
            story.append(Paragraph(
                html.escape(block["text"]),
                styles[f"MiniHeading{ebene}"],
            ))
        elif kind == "paragraph":
            story.append(Paragraph(html.escape(block["text"]), styles["MiniBody"]))
        elif kind == "list":
            bullet = None if block["ordered"] else "•"
            prefix = f"{block.get('index') or 1}. " if block["ordered"] else ""
            story.append(Paragraph(
                html.escape(prefix + block["text"]),
                ParagraphStyle(
                    name=f"List-{len(story)}",
                    parent=styles["MiniBody"],
                    leftIndent=13,
                    firstLineIndent=-8,
                    bulletIndent=4,
                ),
                bulletText=bullet,
            ))
        elif kind == "quote":
            story.append(Paragraph(html.escape(block["text"]), styles["MiniQuote"]))
        elif kind == "code":
            story.extend([
                Preformatted(
                    block["text"],
                    ParagraphStyle(
                        name=f"Code-{len(story)}",
                        fontName="Courier",
                        fontSize=7,
                        leading=9,
                        textColor=colors.HexColor("#17212B"),
                        backColor=colors.HexColor("#F1F4F7"),
                        borderPadding=7,
                    ),
                    maxLineLength=105,
                ),
                Spacer(1, 7),
            ])
        elif kind == "rule":
            story.append(Spacer(1, 6))
        elif kind == "table":
            table_data = [
                [
                    Paragraph(html.escape(value), styles["MiniTableHeader"])
                    for value in block["headers"]
                ]
            ]
            table_data.extend(
                [Paragraph(html.escape(value), styles["MiniTableCell"]) for value in row]
                for row in block["rows"]
            )
            column_count = max(1, len(block["headers"]))
            available_width = page_size[0] - 40 * mm
            table = LongTable(
                table_data,
                colWidths=[available_width / column_count] * column_count,
                repeatRows=1,
                hAlign="LEFT",
            )
            # Eine Tabelle, die unten nur noch Kopfzeile und eine Zeile
            # unterbringt, wandert lieber ganz auf die nächste Seite. Steht sie
            # direkt unter einer Überschrift, hat die schon Platz gefordert.
            if not (vorheriger and vorheriger["type"] == "heading"):
                story.append(CondPageBreak(48 * mm))
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{NAVY}")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5DF")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    colors.white,
                    colors.HexColor("#F5F8FC"),
                ]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 9)])

    document.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    return output.getvalue()


def _pdf_safe_deep(wert: Any) -> Any:
    if isinstance(wert, str):
        return pdf_safe_text(wert)
    if isinstance(wert, list):
        return [_pdf_safe_deep(eintrag) for eintrag in wert]
    if isinstance(wert, dict):
        return {schluessel: _pdf_safe_deep(inhalt) for schluessel, inhalt in wert.items()}
    return wert


def build_letter_pdf(artifact: dict[str, Any]) -> bytes:
    letter = _pdf_safe_deep(normalize_letter_artifact(artifact))
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=safe_title(letter["subject"]),
        author=str(letter["sender"].get("name") or ""),
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        name="LetterBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#202B35"),
        spaceAfter=10,
    )
    address = ParagraphStyle(
        name="LetterAddress",
        parent=body,
        fontSize=9.5,
        leading=13,
        spaceAfter=0,
    )
    sender_address = ParagraphStyle(
        name="LetterSenderAddress",
        parent=address,
        alignment=2,
    )
    label = ParagraphStyle(
        name="LetterLabel",
        parent=address,
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor(f"#{MUTED}"),
        spaceAfter=5,
    )
    sender_label = ParagraphStyle(
        name="LetterSenderLabel",
        parent=label,
        alignment=2,
    )
    subject = ParagraphStyle(
        name="LetterSubject",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor(f"#{NAVY}"),
        spaceAfter=17,
    )
    meta = ParagraphStyle(
        name="LetterMeta",
        parent=body,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor(f"#{MUTED}"),
        spaceAfter=5,
    )
    date_style = ParagraphStyle(
        name="LetterDate",
        parent=body,
        alignment=2,
        spaceAfter=0,
    )

    def lines_html(lines: list[str]) -> str:
        return "<br/>".join(html.escape(line) for line in lines)

    recipient_flow = [
        Paragraph("EMPFÄNGER", label),
        Paragraph(lines_html(_letter_address_lines(letter["recipient"])), address),
    ]
    sender_flow = [
        Paragraph("ABSENDER", sender_label),
        Paragraph(
            lines_html(_letter_address_lines(letter["sender"], include_contact=True)),
            sender_address,
        ),
    ]
    header = Table(
        [[recipient_flow, sender_flow]],
        colWidths=[81 * mm, 81 * mm],
        hAlign="LEFT",
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    story: list[Any] = [
        header,
        Spacer(1, 12 * mm),
        Paragraph(html.escape(letter["date"]), date_style),
        Spacer(1, 8 * mm),
    ]
    if letter["reference"]:
        story.append(Paragraph(
            f"Aktenzeichen: {html.escape(letter['reference'])}",
            meta,
        ))
    story.extend([
        Paragraph(f"Betreff: {html.escape(letter['subject'])}", subject),
        Paragraph(html.escape(letter["salutation"]), body),
    ])
    story.extend(
        Paragraph(html.escape(paragraph), body)
        for paragraph in letter["paragraphs"]
    )
    story.extend([
        Spacer(1, 7 * mm),
        Paragraph(html.escape(letter["closing"]), body),
        Spacer(1, 11 * mm),
        Paragraph(html.escape(letter["signature"]), body),
    ])
    document.build(story)
    return output.getvalue()


def _safe_cell_value(value: str) -> str:
    value = value.strip()
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _safe_sheet_name(value: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", value).strip()[:31] or "Tabelle"
    candidate = base
    number = 2
    while candidate in used:
        suffix = f" {number}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        number += 1
    used.add(candidate)
    return candidate


def _style_worksheet(sheet: Any, max_column: int, max_row: int) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(max_column)}{max_row}"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    if max_column > 5:
        sheet.page_setup.orientation = "landscape"
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 26
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="202B35")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row % 2 == 1:
                cell.fill = PatternFill("solid", fgColor="F5F8FC")
    for column in range(1, max_column + 1):
        values = [
            str(sheet.cell(row=row, column=column).value or "")
            for row in range(1, min(max_row, 250) + 1)
        ]
        width = max((len(value) for value in values), default=8) + 2
        sheet.column_dimensions[get_column_letter(column)].width = min(48, max(10, width))


def build_xlsx(title: str, content: str) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    used_names: set[str] = set()
    blocks = parse_markdown(content)
    tables = [block for block in blocks if block["type"] == "table"]
    non_table_blocks = [block for block in blocks if block["type"] != "table"]

    if non_table_blocks or not tables:
        sheet = workbook.create_sheet(_safe_sheet_name("Antwort", used_names))
        sheet.append([f"Mini LLM · {safe_title(title)}"])
        row = 3
        for block in non_table_blocks:
            kind = block["type"]
            if kind == "heading":
                sheet.cell(row=row, column=1, value=block["text"])
                sheet.cell(row=row, column=1).font = Font(
                    name="Arial",
                    size=max(11, 17 - block["level"]),
                    bold=True,
                    color=NAVY,
                )
            elif kind == "list":
                sheet.cell(row=row, column=1, value=("1. " if block["ordered"] else "• ") + block["text"])
            elif kind == "code":
                sheet.cell(row=row, column=1, value=_safe_cell_value(block["text"]))
                sheet.cell(row=row, column=1).font = Font(name="Courier New", size=9)
            elif kind in {"paragraph", "quote"}:
                sheet.cell(row=row, column=1, value=_safe_cell_value(block["text"]))
            elif kind == "rule":
                row += 1
            row += 1
        sheet.column_dimensions["A"].width = 90
        sheet.freeze_panes = "A3"
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet["A1"].fill = PatternFill("solid", fgColor=NAVY)
        sheet["A1"].font = Font(name="Arial", bold=True, color="FFFFFF")
        for sheet_row in sheet.iter_rows(min_row=3):
            for cell in sheet_row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    for table_index, block in enumerate(tables, 1):
        sheet = workbook.create_sheet(
            _safe_sheet_name(f"Tabelle {table_index}", used_names)
        )
        sheet.append([_safe_cell_value(value) for value in block["headers"]])
        for row in block["rows"]:
            sheet.append([_safe_cell_value(value) for value in row])
        _style_worksheet(sheet, len(block["headers"]), len(block["rows"]) + 1)

    workbook.properties.title = safe_title(title)
    workbook.properties.creator = "Mini LLM"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_eml(title: str, content: str) -> bytes:
    return build_eml_with_context(title, content)


EMAIL_ADDRESS_PATTERN = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)


def _email_header_value(content: str, labels: tuple[str, ...]) -> str:
    plain = "\n".join(
        strip_inline_markdown(line)
        for line in (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?im)^\s*(?:{label_pattern})\s*:\s*(.+?)\s*$",
        plain,
    )
    return match.group(1).strip() if match else ""


def _request_subject(request_prompt: str) -> str:
    plain = strip_inline_markdown(request_prompt or "")
    match = re.search(
        r"(?i)\bbetreff(?:\s+(?:ist|soll(?:te)?\s+(?:sein|lauten)))?"
        r"\s*(?::|–|—|-)\s*[\"„“']?([^\"„“'\n.!?]{3,120})",
        plain,
    )
    return safe_title(match.group(1)) if match else ""


def _body_summary_subject(content: str) -> str:
    plain = "\n".join(
        strip_inline_markdown(line)
        for line in (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    )
    match = re.search(
        r"(?i)\b(?:hier\s+ist|anbei|im\s+folgenden\s+findest\s+du)"
        r"\s+(?:die\s+)?"
        r"(zusammenfassung\s+(?:(?:der|zu\s+den|über\s+die|von\s+den)\s+)"
        r"[^:\n.!?]{3,100})\s*:",
        plain,
    )
    if not match:
        return ""
    subject = match.group(1).strip()
    return safe_title(subject[0].upper() + subject[1:])


def _clean_email_body(content: str, sender_name: str = "") -> str:
    cleaned: list[str] = []
    header_pattern = re.compile(
        r"(?i)^\s*(?:\*\*|__)?"
        r"(?:empfänger|empfaenger|an|to|betreff|subject|absender|von|from)"
        r"(?:\*\*|__)?\s*:"
    )
    for line in (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        if header_pattern.match(line):
            continue
        plain_line = strip_inline_markdown(line).strip()
        if sender_name and re.fullmatch(
            r"(?i)(?:\[|<|\{)?\s*"
            r"(?:(?:ihr|dein|mein)\s+)?"
            r"(?:name|vor-?\s*und\s+nachname|unterschrift)"
            r"\s*(?:\]|>|\})?",
            plain_line,
        ):
            cleaned.append(sender_name)
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def parse_email_draft(
    title: str,
    content: str,
    *,
    request_prompt: str = "",
    sender_name: str = "",
    sender_email: str = "",
) -> dict[str, str]:
    request_recipient = EMAIL_ADDRESS_PATTERN.search(request_prompt or "")
    content_recipient = EMAIL_ADDRESS_PATTERN.search(
        _email_header_value(content, ("Empfänger", "Empfaenger", "An", "To"))
    )
    recipient = (
        request_recipient.group(1)
        if request_recipient
        else content_recipient.group(1)
        if content_recipient
        else ""
    )
    subject = (
        _request_subject(request_prompt)
        or _body_summary_subject(content)
        or _email_header_value(content, ("Betreff", "Subject"))
        or safe_title(title)
    )
    safe_sender_email = ""
    sender_match = EMAIL_ADDRESS_PATTERN.fullmatch((sender_email or "").strip())
    if sender_match:
        safe_sender_email = sender_match.group(1)
    return {
        "to": recipient,
        "subject": safe_title(subject),
        "body": _clean_email_body(content, sender_name),
        "sender_name": safe_title(sender_name) if sender_name else "",
        "sender_email": safe_sender_email,
    }


def build_eml_with_context(
    title: str,
    content: str,
    *,
    request_prompt: str = "",
    sender_name: str = "",
    sender_email: str = "",
    draft: dict[str, str] | None = None,
) -> bytes:
    draft = draft or parse_email_draft(
        title,
        content,
        request_prompt=request_prompt,
        sender_name=sender_name,
        sender_email=sender_email,
    )
    message = EmailMessage()
    message["Subject"] = draft["subject"]
    if draft["to"]:
        message["To"] = draft["to"]
    if draft["sender_email"]:
        message["From"] = (
            f"{draft['sender_name']} <{draft['sender_email']}>"
            if draft["sender_name"]
            else draft["sender_email"]
        )
    message["X-Unsent"] = "1"
    message.set_content(email_draft_plain_text(draft), charset="utf-8")
    return message.as_bytes()


def email_draft_plain_text(draft: dict[str, str]) -> str:
    blocks = parse_markdown(draft["body"])
    lines: list[str] = []
    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            lines.extend([block["text"], ""])
        elif kind == "paragraph":
            lines.extend([block["text"], ""])
        elif kind == "list":
            lines.append(("1. " if block["ordered"] else "- ") + block["text"])
        elif kind == "quote":
            lines.extend(["> " + block["text"], ""])
        elif kind == "code":
            lines.extend([block["text"], ""])
        elif kind == "table":
            lines.append("\t".join(block["headers"]))
            lines.extend("\t".join(row) for row in block["rows"])
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_letter_eml(artifact: dict[str, Any]) -> bytes:
    letter = normalize_letter_artifact(artifact)
    message = EmailMessage()
    message["Subject"] = letter["subject"]
    recipient_name = str(letter["recipient"].get("name") or "").strip()
    message["To"] = recipient_name or "Empfänger"
    sender_email = str(letter["sender"].get("email") or "").strip()
    sender_name = str(letter["sender"].get("name") or "").strip()
    if sender_email and not sender_email.startswith("["):
        message["From"] = (
            f"{sender_name} <{sender_email}>"
            if sender_name and not sender_name.startswith("[")
            else sender_email
        )
    message["X-Unsent"] = "1"
    lines = [letter["salutation"], ""]
    for paragraph in letter["paragraphs"]:
        lines.extend([paragraph, ""])
    lines.extend([letter["closing"], "", letter["signature"]])
    message.set_content("\n".join(lines).strip() + "\n", charset="utf-8")
    return message.as_bytes()


def title_from_content(title: str, content: str) -> tuple[str, str]:
    """Nimmt die erste Überschrift des Textes als Dokumenttitel.

    Sonst steht auf dem PDF der Auftrag („Schreibe einen Bericht über …“)
    statt des Gegenstands — und direkt darunter noch einmal der echte Titel.
    """

    treffer = re.match(r"\s*#\s+(.+?)\s*(?:\n|$)", content or "")
    if not treffer:
        return title, content
    kopf = strip_inline_markdown(treffer.group(1)).strip()
    if len(kopf) < 3:
        return title, content
    return kopf, (content[treffer.end():].lstrip("\n"))


def build_export(
    format_name: str,
    title: str,
    content: str,
    artifact: dict[str, Any] | None = None,
    presentation_author: str = "",
    email_request_prompt: str = "",
    email_sender_name: str = "",
    email_sender_email: str = "",
) -> tuple[bytes, str, str]:
    if not (content or "").strip():
        raise ValueError("Die Antwort ist leer.")
    if format_name != "pptx":
        # Bei einer Präsentation ist die erste Überschrift der Titel der
        # Auftaktfolie und muss im Inhalt bleiben.
        title, content = title_from_content(title, content)
    title = safe_title(title)
    if isinstance(artifact, dict) and artifact.get("type") == "letter":
        letter = normalize_letter_artifact(artifact)
        letter_title = safe_title(letter["subject"])
        letter_builders = {
            "docx": (
                build_letter_docx,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "pdf": (build_letter_pdf, "application/pdf"),
            "eml": (build_letter_eml, "message/rfc822"),
        }
        if format_name in letter_builders:
            builder, media_type = letter_builders[format_name]
            payload = builder(letter)
            return payload, media_type, f"{safe_filename(letter_title)}.{format_name}"
    builders = {
        "docx": (build_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "xlsx": (build_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "pdf": (build_pdf, "application/pdf"),
        "pptx": (
            build_pptx,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        "eml": (build_eml, "message/rfc822"),
    }
    if format_name not in builders:
        raise ValueError("Unbekanntes Exportformat.")
    builder, media_type = builders[format_name]
    if format_name == "pptx":
        payload = build_pptx(
            title,
            content[:MAX_EXPORT_CHARS],
            author=presentation_author,
        )
    elif format_name == "eml":
        draft = parse_email_draft(
            title,
            content[:MAX_EXPORT_CHARS],
            request_prompt=email_request_prompt,
            sender_name=email_sender_name,
            sender_email=email_sender_email,
        )
        payload = build_eml_with_context(
            title,
            content[:MAX_EXPORT_CHARS],
            draft=draft,
        )
        return (
            payload,
            media_type,
            f"{safe_filename(draft['subject'])}.{format_name}",
        )
    else:
        payload = builder(title, content[:MAX_EXPORT_CHARS])
    return payload, media_type, f"{safe_filename(title)}.{format_name}"
