# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import unittest

from app.main import (
    build_verbatim_file_response,
    document_answer_issues,
    explicitly_requests_stored_documents,
    is_document_transform_request,
    is_verbatim_file_request,
    raw_stream_chunks,
    rank_context_chunks,
    select_document_contexts,
)
from app.intelligence import context_source_text, split_text


SOURCE = """
## PDF-Seite 1/2
Einleitung und Projektziel.

## PDF-Seite 2/2
Evaluation mit Trefferquote und Fehlerfällen.
""".strip()


class DocumentQualityTests(unittest.TestCase):
    def test_detects_impossible_page_and_repetition(self) -> None:
        repeated = (
            "Evaluation mit identischem Testbestand und nachvollziehbaren Messgrößen "
            "bildet eine belastbare Entscheidungsgrundlage für den nächsten Schritt."
        )
        answer = (
            "## PDF-Seite 3/2\n"
            + "\n".join(repeated for _ in range(5))
        )
        issues = document_answer_issues(answer, SOURCE)
        self.assertTrue(any("Seitenangabe" in issue for issue in issues))
        self.assertTrue(any("wiederholt" in issue for issue in issues))

    def test_accepts_clean_document_text(self) -> None:
        self.assertEqual(document_answer_issues(SOURCE, SOURCE), [])

    def test_deduplicates_same_cached_context(self) -> None:
        context = {
            "id": "a" * 64,
            "name": "test.pdf",
            "kind": "document",
            "chunks": [{"text": SOURCE}],
        }
        chunks = rank_context_chunks(
            [context, context],
            "Hole den gesamten Text heraus.",
        )
        self.assertEqual(len(chunks), 1)

    def test_recognizes_document_rewrite_request(self) -> None:
        self.assertTrue(is_document_transform_request(
            "Kannst du den gesamten Text einmal rausholen und chronologisch aufbauen?"
        ))
        self.assertTrue(is_document_transform_request(
            "Kannst du diese zunächst abschreiben?"
        ))

    def test_verbatim_html_request_reconstructs_source_without_summary(self) -> None:
        source = (
            "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n"
            "  <style>body { color: #123; }</style>\n</head>\n"
            "<body>\n  <h1>Original</h1>\n</body>\n</html>"
        )
        wrapped = (
            '<datei name="seite.html" typ="text">\n'
            + source
            + "\n</datei>"
        )
        context = {
            "id": "e" * 64,
            "name": "seite.html",
            "kind": "document",
            "chunks": [
                {"text": chunk}
                for chunk in split_text(wrapped, size=70, overlap=20)
            ],
        }
        self.assertEqual(context_source_text(context), wrapped)
        response = build_verbatim_file_response(
            [context],
            "Kannst du diese zunächst abschreiben, damit ich sie als Vorschau sehe?",
            priority_ids={context["id"]},
        )
        self.assertEqual(response, f"```html\n{source}\n```")

    def test_correction_to_html_code_is_not_routed_to_summary(self) -> None:
        prompt = (
            "Ich wollte keine Zusammenfassung. Du solltest den HTML-Code "
            "anfertigen und als Vorschau zeigen."
        )
        self.assertTrue(is_verbatim_file_request(prompt))
        context = {
            "id": "f" * 64,
            "name": "seite.html",
            "kind": "document",
            "chunks": [
                {"text": f"Abschnitt {index} ohne Treffer"}
                for index in range(38)
            ],
        }
        self.assertEqual(len(rank_context_chunks([context], prompt)), 12)

    def test_raw_streaming_preserves_source_whitespace(self) -> None:
        source = "```html\n<div>\n    exakt eingerückt\n</div>\n```"
        self.assertEqual("".join(raw_stream_chunks(source, 9)), source)

    def test_targeted_question_limits_unrelated_document_chunks(self) -> None:
        context = {
            "id": "b" * 64,
            "name": "handbuch.pdf",
            "kind": "document",
            "chunks": [{"text": f"Abschnitt {index} ohne Treffer"} for index in range(30)],
        }
        chunks = rank_context_chunks([context], "Was steht zur Gewährleistung?")
        self.assertEqual(len(chunks), 12)

    def test_full_document_request_keeps_all_chunks(self) -> None:
        context = {
            "id": "c" * 64,
            "name": "handbuch.pdf",
            "kind": "document",
            "chunks": [{"text": f"Abschnitt {index}"} for index in range(20)],
        }
        chunks = rank_context_chunks(
            [context],
            "Fasse das gesamte Dokument vollständig zusammen.",
        )
        self.assertEqual(len(chunks), 20)

    def test_plain_summary_request_keeps_all_chunks(self) -> None:
        context = {
            "id": "d" * 64,
            "name": "handbuch.pdf",
            "kind": "document",
            "chunks": [{"text": f"Abschnitt {index}"} for index in range(16)],
        }
        chunks = rank_context_chunks(
            [context],
            "Fasse das Dokument bitte zusammen.",
        )
        self.assertEqual(len(chunks), 16)


class StoredDocumentScopeTests(unittest.TestCase):
    """Old uploads must not consume the context window on ordinary chat turns."""

    def setUp(self) -> None:
        self.contract = {
            "id": "a" * 64,
            "name": "Mietvertrag-2026.pdf",
            "kind": "document",
            "chunks": [{"text": "Kündigungsfrist: drei Monate."}],
        }
        self.invoice = {
            "id": "b" * 64,
            "name": "Rechnung-Beispiel-GmbH.pdf",
            "kind": "document",
            "chunks": [{"text": "Rechnungsbetrag: 120 Euro."}],
        }
        self.contexts = [self.contract, self.invoice]

    def test_normal_follow_up_does_not_reopen_old_uploads(self) -> None:
        selected, reopened = select_document_contexts(
            self.contexts,
            "Kannst du das bitte freundlicher formulieren?",
        )
        self.assertEqual(selected, [])
        self.assertFalse(reopened)

    def test_explicit_document_request_reopens_latest_upload(self) -> None:
        selected, reopened = select_document_contexts(
            self.contexts,
            "Lies das hochgeladene Dokument noch einmal und nenne die Frist.",
        )
        self.assertEqual(selected, [self.invoice])
        self.assertTrue(reopened)

    def test_filename_selects_only_that_source(self) -> None:
        selected, reopened = select_document_contexts(
            self.contexts,
            "Prüfe bitte Mietvertrag-2026.pdf auf die Kündigungsfrist.",
        )
        self.assertEqual(selected, [self.contract])
        self.assertTrue(reopened)

    def test_new_upload_is_available_without_explicit_reference(self) -> None:
        selected, reopened = select_document_contexts(
            self.contexts,
            "Fasse den Inhalt verständlich zusammen.",
            {self.contract["id"]},
        )
        self.assertEqual(selected, [self.contract])
        self.assertFalse(reopened)

    def test_explicit_comparison_can_reopen_multiple_sources(self) -> None:
        selected, reopened = select_document_contexts(
            self.contexts,
            "Vergleiche bitte die beiden hochgeladenen Dokumente.",
        )
        self.assertEqual(selected, self.contexts)
        self.assertTrue(reopened)

    def test_filename_is_an_explicit_reference(self) -> None:
        self.assertTrue(explicitly_requests_stored_documents(
            "Was steht in der Rechnung-Beispiel-GmbH.pdf?",
            self.contexts,
        ))

class PdfCharacterTests(unittest.TestCase):
    """Die PDF-Standardschrift kennt nur cp1252 — alles andere wird zum Kästchen."""

    def test_typographic_hyphens_do_not_become_boxes(self):
        from io import BytesIO

        from pypdf import PdfReader

        from app.exports import build_pdf

        # U+2011 ist der geschützte Bindestrich, den Modelle gern schreiben.
        text = PdfReader(BytesIO(build_pdf(
            "Probe", "Z\u2011Außenlager, KZ\u2011Baracken, \u2248 7 Monate."
        ))).pages[0].extract_text()
        self.assertNotIn("\u25a0", text, "Im PDF steht ein schwarzes Kästchen.")
        self.assertIn("Z-Außenlager", text)
        self.assertIn("ca. 7 Monate", text)

    def test_unknown_signs_are_transliterated_or_dropped(self):
        from app.exports import pdf_safe_text

        self.assertEqual(pdf_safe_text("a\u2192b"), "a->b")
        self.assertEqual(pdf_safe_text("Häftlinge"), "Häftlinge")
        self.assertEqual(pdf_safe_text("1\u2009100"), "1 100")
        pdf_safe_text("Ω 漢字 🙂").encode("cp1252")   # darf nicht werfen


class ReportSkillTests(unittest.TestCase):
    """Der Bericht darf kein ausgefülltes Formular werden."""

    def test_the_order_is_not_a_list_of_headings(self):
        from app.task_skills import SKILL_RUNTIMES

        anweisung = SKILL_RUNTIMES["report"].directive
        self.assertIn("keine Überschriftenliste", anweisung)
        self.assertIn("zwingend folgen", anweisung)

    def test_sources_survive_a_skill_pass(self):
        from app.task_skills import active_skills_system_prompt

        prompt = active_skills_system_prompt(["report"], {})
        self.assertIn("Quellenangaben, Links", prompt)
        self.assertIn("Fußnotenmarke ohne Ziel", prompt)

    def test_length_never_invites_padding(self):
        from app.task_skills import answer_shape_system_prompt

        lang = answer_shape_system_prompt({"length": "long", "density": "rich"})
        self.assertIn("statt zu strecken", lang)
        self.assertIn("keine erfundenen Beispiele", lang)

class WebSearchTopicTests(unittest.TestCase):
    """Die Suche muss nach dem Thema suchen, nicht nach dem Auftrag."""

    def test_the_task_wrapper_is_stripped(self):
        from app.intelligence import search_topic

        self.assertEqual(
            search_topic(
                "Dann schreib du ein ausführlichen Bericht über 49 Seiten. "
                "Such im netzt nach korrekten Angaben zum Lager holzen. "
                "Schreibe tief und umfangreich"
            ),
            "Lager holzen",
        )
        self.assertEqual(
            search_topic("Verfasse einen kurzen Bericht zur Lage der Bauwirtschaft 2026"),
            "Lage der Bauwirtschaft 2026",
        )
        self.assertIn(
            "Außenlager Holzen",
            search_topic("Schreibe einen Bericht über das KZ-Außenlager Holzen"),
        )

    def test_a_pure_instruction_has_no_topic(self):
        from app.intelligence import search_topic

        # Ohne Thema greift der Gesprächskontext — nicht eine Suche nach „Bericht“.
        self.assertEqual(search_topic("Schreibe den Bericht bitte so ausführlich, wie du kannst"), "")

    def test_how_to_pages_are_pushed_down(self):
        from app.intelligence import _source_score

        ratgeber = {
            "title": "Wie man einen Bericht schreibt: Schritt-für-Schritt-Anleitung",
            "snippet": "Vorlage und Übungen für Klasse 6",
            "url": "https://example.org/bericht-schreiben",
        }
        quelle = {
            "title": "KZ-Außenlager Holzen",
            "snippet": "Außenlager des KZ Buchenwald 1944",
            "url": "https://de.wikipedia.org/wiki/KZ-Au%C3%9Fenlager_Holzen",
        }
        thema = "Lager Holzen"
        self.assertLess(_source_score(ratgeber, thema), _source_score(quelle, thema))


class LongReportPlanTests(unittest.TestCase):
    """Vierzig Seiten entstehen aus Kapiteln, nicht aus einem Aufruf."""

    def test_the_steps_match_the_requested_size(self):
        from app.task_skills import report_plan

        self.assertEqual(report_plan("long", 20000)["sections"], 12)
        self.assertEqual(report_plan("medium", 20000)["sections"], 8)
        self.assertIsNone(report_plan("short", 20000), "Kurz braucht keine Kette.")

    def test_thin_material_shortens_the_plan_instead_of_inventing(self):
        from app.task_skills import report_plan

        self.assertEqual(report_plan("long", 1000)["sections"], 5)
        self.assertIsNone(report_plan("auto", 200), "Ohne Stoff kein Langbericht.")
        self.assertEqual(report_plan("auto", 20000)["sections"], 12)

    def test_every_section_prompt_forbids_invented_sources(self):
        from app.task_skills import report_section_prompt

        nachricht = report_section_prompt(
            "Lager Holzen",
            {"sections": 12, "pages": 40, "words": 1200},
            [{"titel": "Lage", "inhalt": "Wo das Lager stand"}, {"titel": "Arbeit", "inhalt": "x"}],
            0,
            "Material",
            "",
        )
        vertrag = nachricht[0]["content"]
        for verbot in ("Aktenzeichen", "Archivbestände", "Interviewnummern", "[unbelegt]"):
            self.assertIn(verbot, vertrag)

    def test_a_short_section_gets_one_continuation(self):
        from app.task_skills import report_continue_prompt

        nachricht = report_continue_prompt(
            "Lager Holzen",
            {"sections": 12, "pages": 40, "words": 1200},
            {"titel": "Lage", "inhalt": "x"},
            "## Lage\n\nZu kurzer Text.",
        )
        vertrag = nachricht[0]["content"]
        self.assertIn("Wiederhole nichts", vertrag)
        self.assertIn("keine neue Überschrift", vertrag)

class DocumentTitleTests(unittest.TestCase):
    """Auf dem Dokument steht der Gegenstand, nicht der Auftrag."""

    def test_the_heading_of_the_text_becomes_the_title(self):
        from app.exports import title_from_content

        titel, inhalt = title_from_content(
            "Schreibe einen Bericht über den Bau der El…",
            "# Bau und Realisierung der Elbphilharmonie Hamburg\n\n## Initiative\n\nText.",
        )
        self.assertEqual(titel, "Bau und Realisierung der Elbphilharmonie Hamburg")
        self.assertTrue(inhalt.startswith("## Initiative"), "Der Titel steht sonst doppelt.")

    def test_a_text_without_heading_keeps_its_title(self):
        from app.exports import title_from_content

        titel, inhalt = title_from_content("Mein Chat", "Einfach nur Text.")
        self.assertEqual(titel, "Mein Chat")
        self.assertEqual(inhalt, "Einfach nur Text.")

    def test_the_file_is_named_after_the_content(self):
        from app.exports import build_export

        _, _, name = build_export(
            "pdf",
            "Schreibe einen Bericht über den Bau der El…",
            "# Bau der Elbphilharmonie\n\nText mit Inhalt.",
        )
        self.assertIn("elbphilharmonie", name)
        self.assertNotIn("schreibe", name)


class ReportWithoutSourcesTests(unittest.TestCase):
    def test_without_sources_no_citation_marks_are_requested(self):
        from app.task_skills import report_section_prompt

        ohne = report_section_prompt(
            "Thema", {"sections": 8, "pages": 28, "words": 1100},
            [{"titel": "A", "inhalt": "x"}, {"titel": "B", "inhalt": "y"}],
            0, "Material", "", "", has_sources=False,
        )[0]["content"]
        self.assertIn("keine Quellenmarken", ohne)
        mit = report_section_prompt(
            "Thema", {"sections": 8, "pages": 28, "words": 1100},
            [{"titel": "A", "inhalt": "x"}, {"titel": "B", "inhalt": "y"}],
            0, "Material", "", "", has_sources=True,
        )[0]["content"]
        self.assertIn("[[n]]", mit)

class AdvisoryNoteTests(unittest.TestCase):
    """Der Beratungshinweis steht nur unter Berichten, die wirklich raten."""

    def test_a_construction_report_gets_no_advisory_note(self):
        from app.task_skills import braucht_beratungshinweis

        self.assertFalse(braucht_beratungshinweis(
            "Die Bühnenanlagen und Lüftungsanlagen wurden erneuert. Die Kosten "
            "trugen am Ende die Steuerzahler. Renditen waren nie das Ziel; es "
            "wird empfohlen, den Rechnungshof einzubeziehen."
        ), "Anlagen, Steuern und Renditen sind hier Bauvokabular.")

    def test_a_supplement_report_keeps_the_advisory_note(self):
        from app.task_skills import braucht_beratungshinweis

        self.assertTrue(braucht_beratungshinweis(
            "Die Dosierung von Magnesium liegt bei 300 mg. Vor der Einnahme von "
            "Präparaten sollten Sie ärztlichen Rat einholen."
        ))

    def test_technical_terms_without_advice_stay_silent(self):
        from app.task_skills import braucht_beratungshinweis

        self.assertFalse(braucht_beratungshinweis(
            "Der Wirkstoff wurde 1928 entdeckt. Die Therapie setzte sich in den "
            "1940er Jahren durch."
        ), "Eine Wissenschaftsgeschichte rät niemandem etwas.")


if __name__ == "__main__":
    unittest.main()
