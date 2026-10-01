# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import re
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from app.exports import build_export
from app.presentation_export import (
    NS,
    R_ID,
    build_pptx,
    parse_presentation_content,
)
from app.task_skills import (
    active_skills_system_prompt,
    normalize_active_skills,
    resolve_task_skill,
)


PRESENTATION_SOURCE = """
# Lokale KI schafft messbare Entlastung
> Entscheidungsgrundlage für den nächsten Umsetzungsschritt

## Der Ausgangspunkt ist klar
- Die Verwaltung bearbeitet 35 wiederkehrende Prozesse.
- Medienbrüche kosten jede Woche Zeit.

## Automatisierung setzt an den größten Hebeln an
| Bereich | Zeitersparnis |
| --- | ---: |
| Datenerfassung | 42 % |
| Dokumentprüfung | 28 % |
| Recherche | 18 % |

## Nächste Schritte
- Pilotprozess auswählen und Erfolgskriterien festlegen.
- Ergebnisse nach vier Wochen gemeinsam bewerten.
""".strip()


class PresentationExportTests(unittest.TestCase):
    def test_presentation_is_exclusive_document_skill(self) -> None:
        self.assertEqual(
            normalize_active_skills(["letter", "presentation"]),
            ["presentation"],
        )
        self.assertIsNone(resolve_task_skill(
            "Übertrage diesen Brief in eine Präsentation.",
            ["presentation"],
            [],
        ))

    def test_runtime_contract_preserves_numbers_for_renderer(self) -> None:
        prompt = active_skills_system_prompt(["presentation"])
        self.assertIn("folienfertige Markdown", prompt)
        self.assertIn("nichts erfinden", prompt)
        self.assertIn("Visualisierte Zahlen nicht zusätzlich", prompt)
        self.assertIn("Blockzitat", prompt)
        self.assertNotIn("PROTOKOLL", prompt)

    def test_parser_splits_sections_and_detects_chart_values(self) -> None:
        deck = parse_presentation_content("Fallback", PRESENTATION_SOURCE)
        self.assertEqual(deck.title, "Lokale KI schafft messbare Entlastung")
        self.assertEqual(len(deck.slides), 3)
        self.assertEqual(
            [metric.display for metric in deck.slides[1].metrics],
            ["42 %", "28 %", "18 %"],
        )
        self.assertEqual(len(deck.slides[1].points), 1)
        self.assertNotIn("42 %", deck.slides[1].points[0])
        self.assertTrue(deck.slides[-1].closing)

    def test_single_metric_becomes_callout_without_duplicate_point(self) -> None:
        deck = parse_presentation_content(
            "Pilot",
            """
# Sicherer Pilot
> Entscheidung über den kontrollierten Einstieg

## Der Pilot bleibt bewusst begrenzt
- Dauer: 8 Wochen
- Sechs Mitarbeitende testen den Ablauf.
- Entscheidungen bleiben beim Menschen.
""".strip(),
        )
        self.assertEqual(
            [metric.display for metric in deck.slides[0].metrics],
            ["8 Wochen"],
        )
        self.assertFalse(any(
            "8 Wochen" in point for point in deck.slides[0].points
        ))
        self.assertTrue(any(
            "Mitarbeitende" in point for point in deck.slides[0].points
        ))

        payload = build_pptx("Pilot", """
# Sicherer Pilot
> Entscheidung über den kontrollierten Einstieg

## Der Pilot bleibt bewusst begrenzt
- Dauer: 8 Wochen
- Sechs Mitarbeitende testen den Ablauf.
""".strip())
        with ZipFile(BytesIO(payload)) as archive:
            selected_xml = b"".join(
                archive.read(name)
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            )
        self.assertIn("Zentrale Kennzahl".encode(), selected_xml)
        self.assertIn("8 Wochen".encode(), selected_xml)

    def test_phase_numbers_are_not_interpreted_as_chart_values(self) -> None:
        deck = parse_presentation_content(
            "Zeitplan",
            """
# Klarer Abschluss
> Nächster Schritt nach Freigabe

## Der Ablauf bleibt nachvollziehbar
- Phase 1 & 2: Vorbereitung und Pilotbetrieb
- Phase 3: Auswertung und Ergebnisbericht
""".strip(),
        )
        self.assertEqual(deck.slides[0].metrics, [])
        self.assertEqual(len(deck.slides[0].points), 2)

    def test_metric_labels_remove_comparison_words(self) -> None:
        deck = parse_presentation_content(
            "Kriterien",
            """
# Erfolg ist messbar
> Zwei klare Zielwerte

## Die Kriterien bleiben eindeutig
- Manuelle Dateneingaben: mindestens 30 % weniger
- Fehlerquote: unter 5 %
""".strip(),
        )
        self.assertEqual(
            [metric.label for metric in deck.slides[0].metrics],
            ["Manuelle Dateneingaben", "Fehlerquote"],
        )

    def test_long_deck_title_is_not_truncated_at_old_limit(self) -> None:
        title = (
            "Pilotprojekt zur effizienzsteigernden Dokumentenverarbeitung "
            "mittels künstlicher Intelligenz"
        )
        deck = parse_presentation_content("Fallback", f"""
# {title}
> Entscheidungsvorlage für die Verwaltungsleitung

## Der Pilot schafft eine belastbare Grundlage
- Ein kontrollierter Test macht Nutzen und Risiken messbar.
""".strip())
        self.assertEqual(deck.title, title)
        self.assertNotIn(" …", deck.title)

    def test_builds_valid_editable_pptx_with_selected_slide_count(self) -> None:
        payload = build_pptx("Lokale KI", PRESENTATION_SOURCE)
        self.assertTrue(payload.startswith(b"PK"))
        with ZipFile(BytesIO(payload)) as archive:
            presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
            slide_ids = presentation.xpath("./p:sldIdLst/p:sldId", namespaces=NS)
            self.assertEqual(len(slide_ids), 4)
            relationships = etree.fromstring(
                archive.read("ppt/_rels/presentation.xml.rels").lstrip(b"\xef\xbb\xbf")
            )
            targets = {
                item.get("Id"): (item.get("Target") or "").lstrip("/")
                for item in relationships
            }
            selected_parts = [targets[item.get(R_ID)] for item in slide_ids]
            selected_xml = b"".join(archive.read(part) for part in selected_parts)
            self.assertIn("42 %".encode(), selected_xml)
            self.assertIn("Pilotprozess auswählen".encode(), selected_xml)
            self.assertNotIn(b"Inhalt ", selected_xml)

    def test_export_endpoint_builder_returns_pptx_metadata(self) -> None:
        payload, media_type, filename = build_export(
            "pptx",
            "Lokale KI",
            PRESENTATION_SOURCE,
            presentation_author="BEISPIEL GMBH",
        )
        self.assertTrue(payload.startswith(b"PK"))
        self.assertEqual(
            media_type,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        self.assertEqual(filename, "lokale-ki.pptx")
        with ZipFile(BytesIO(payload)) as archive:
            title_slide = archive.read("ppt/slides/slide1.xml")
            core = archive.read("docProps/core.xml")
        self.assertIn("BEISPIEL GMBH".encode(), title_slide)
        self.assertIn("BEISPIEL GMBH".encode(), core)

    def test_plain_text_is_not_duplicated_as_subtitle(self) -> None:
        deck = parse_presentation_content(
            "Kurzer Überblick",
            "Eine einzelne belastbare Kernaussage ohne Markdown-Überschrift.",
        )
        self.assertEqual(deck.subtitle, "Entscheidungsvorlage · Überblick")
        self.assertEqual(
            deck.slides[0].points,
            ["Eine einzelne belastbare Kernaussage ohne Markdown-Überschrift."],
        )

    def test_long_direct_export_is_condensed_instead_of_rejected(self) -> None:
        sections = "\n\n".join(
            f"## Abschnitt {index}\n- Kernaussage {index} bleibt für die Entscheidung relevant."
            for index in range(1, 15)
        )
        source = f"# Direkter Export\n> Automatisch verdichtete Präsentation\n\n{sections}"
        deck = parse_presentation_content("Direkter Export", source)
        self.assertLessEqual(len(deck.slides), 7)
        payload = build_pptx("Direkter Export", source)
        with ZipFile(BytesIO(payload)) as archive:
            presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
            slide_ids = presentation.xpath("./p:sldIdLst/p:sldId", namespaces=NS)
        self.assertLessEqual(len(slide_ids), 8)

    def test_generic_headings_become_takeaway_titles(self) -> None:
        deck = parse_presentation_content(
            "Pilot",
            """
# KI-Pilot
> Kontrollierter Test

## Aktuelle Ausgangslage der Dokumentenverarbeitung
- Doppelte Datenpflege erzeugt unnötigen Aufwand.

## Risiken und Schutzmaßnahmen
- Personenbezogene Daten bleiben in der lokalen Umgebung.
""".strip(),
        )
        self.assertEqual(
            [slide.title for slide in deck.slides],
            [
                "Doppelte Datenpflege erzeugt unnötigen Aufwand",
                "Kontrollen begrenzen die Datenschutzrisiken",
            ],
        )

    def test_frontend_exposes_skill_and_download_button(self) -> None:
        app_js = (
            Path(__file__).resolve().parents[1] / "static" / "app.js"
        ).read_text(encoding="utf-8")
        self.assertIn('id: "presentation"', app_js)
        self.assertIn('["PPTX", "pptx"', app_js)
        self.assertIn(
            "|| message.profileEnabled === true",
            app_js,
        )


if __name__ == "__main__":
    unittest.main()
