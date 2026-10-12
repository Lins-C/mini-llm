# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Whitepaper-Chat vom 12.10.2026 — vier Fehler in einem Gespräch.

1. „gib den inhalt wieder …" zu einem fünfseitigen PDF kam bei Umfang „Mittel"
   (rund 400 Wörter) als knappe Zusammenfassung zurück.
2. Zweimal „Weiter" auf die fertige Antwort: ohne das PDF setzte das Modell fort
   und erfand Zusagen („Wir melden uns innerhalb von 48 Stunden").
3. Die Nachfrage „ich wollte aber den gesamten inhalt … wort für wort" kam ohne
   das PDF an: „Das referenzierte 5-seitige Dokument liegt mir nicht vor."
4. „Bericht" auf den markierten Prompt analysierte den Prompt selbst — fünf
   Kapitel mit je 1.100 Wörtern, 43.476 Tokens über einen Tippfehler.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from app.main import explicitly_requests_stored_documents, select_document_contexts
from app.task_skills import answer_shape_system_prompt, ist_wiedergabe, report_plan

WURZEL = Path(__file__).resolve().parent.parent

PDF = {
    "id": "d" * 64,
    "name": "Whitepaper_Digitale_Stellen_Muster.pdf",
    "kind": "document",
    "chunks": [{"text": "Whitepaper für Herrn Muster. Digitale Stellen mit Core."}],
}
AELTER = {
    "id": "a" * 64,
    "name": "Mietvertrag-2026.pdf",
    "kind": "document",
    "chunks": [{"text": "Kündigungsfrist drei Monate."}],
}


class FolgefrageTests(unittest.TestCase):
    def test_the_follow_up_keeps_the_pdf_of_the_previous_message(self):
        ausgewaehlt, erneut = select_document_contexts(
            [AELTER, PDF],
            "du hast es nun knapp zusammengefasst ich wollte aber den gesamten inhalt "
            "also exakt 5 seiten wort für wort. nimm herrn muster raus und behandle es oberflächlich",
            set(),
            {PDF["id"]},
        )
        self.assertEqual(ausgewaehlt, [PDF])
        self.assertTrue(erneut)

    def test_a_follow_up_without_hint_words_still_keeps_the_pdf(self):
        ausgewaehlt, _ = select_document_contexts(
            [AELTER, PDF], "nimm herrn muster raus", set(), {PDF["id"]},
        )
        self.assertEqual(ausgewaehlt, [PDF])

    def test_rewording_the_answer_stays_without_the_file(self):
        for frage in ("Kannst du das bitte freundlicher formulieren?", "danke!", "mach es kürzer"):
            ausgewaehlt, _ = select_document_contexts([AELTER, PDF], frage, set(), {PDF["id"]})
            self.assertEqual(ausgewaehlt, [], frage)
        # Wer beim Umformen das Dokument nennt, bekommt es.
        ausgewaehlt, _ = select_document_contexts(
            [AELTER, PDF], "Übersetze das Dokument ins Englische", set(), {PDF["id"]},
        )
        self.assertEqual(ausgewaehlt, [PDF])

    def test_word_for_word_names_the_source_even_without_a_previous_upload(self):
        self.assertTrue(explicitly_requests_stored_documents("bitte wort für wort", [PDF]))
        self.assertTrue(explicitly_requests_stored_documents("den gesamten Inhalt bitte", [PDF]))
        ausgewaehlt, erneut = select_document_contexts([AELTER, PDF], "alles wort für wort")
        self.assertEqual(ausgewaehlt, [PDF], "Gemeint ist die jüngste Quelle.")
        self.assertTrue(erneut)

    def test_without_previous_files_nothing_changes(self):
        ausgewaehlt, _ = select_document_contexts([AELTER, PDF], "nimm herrn muster raus")
        self.assertEqual(ausgewaehlt, [])


class WiedergabeTests(unittest.TestCase):
    def test_reproduction_requests_are_recognised(self):
        for frage in (
            "gib den inhalt wieder und passe ihn enstpsrechend meiner tatsächlichen daten an",
            "schreibe den text hier nieder",
            "ich wollte aber den gesamten inhalt wort für wort",
            "Bitte im Wortlaut",
        ):
            self.assertTrue(ist_wiedergabe(frage), frage)
        for frage in ("Fasse das Dokument zusammen", "Was ist eine Niederlage?",
                      "Wie geht es in den Niederlanden weiter?"):
            self.assertFalse(ist_wiedergabe(frage), frage)

    def test_the_length_setting_does_not_shorten_a_reproduction(self):
        optionen = {"length": "medium", "density": "rich"}
        self.assertIn("400 Wörter", answer_shape_system_prompt(optionen))
        vollstaendig = answer_shape_system_prompt(optionen, wiedergabe=True)
        self.assertNotIn("Wörter", vollstaendig)
        self.assertIn("Dichte", vollstaendig)

    def test_the_endpoint_uses_the_reproduction_rule(self):
        quelle = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("answer_shape_system_prompt(selected_skill_options, wiedergabe=wiedergabe)", quelle)
        self.assertIn("WIEDERGABE_HINWEIS", quelle)

    def test_the_user_is_author_never_recipient(self):
        # Echtlauf 12.10.2026: Statt des Kunden stand der Name des Nutzers als Empfänger.
        from app.main import WIEDERGABE_HINWEIS, build_personalization_system
        self.assertIn("nicht Empfänger", WIEDERGABE_HINWEIS)
        self.assertIn("neutral", WIEDERGABE_HINWEIS)
        system = build_personalization_system(
            {"name": "Admin", "organization": "Beispiel GmbH"}, True, "none", "", "gib den inhalt wieder",
        )
        self.assertIn("nie Empfänger", system)


class BerichtBelegTests(unittest.TestCase):
    def test_a_report_on_a_document_uses_the_document_not_general_knowledge(self):
        from app.task_skills import report_section_prompt
        plan = report_plan("medium", 13_040, quellgebunden=True)
        system = report_section_prompt("T", plan, [{"titel": "a", "inhalt": ""}], 0, "M", "",
                                       has_sources=False)[0]["content"]
        self.assertIn("ausschließlich das bereitgestellte Material", system)
        self.assertNotIn("Allgemeinwissen", system)
        offen = report_plan("medium", 20_000)
        system = report_section_prompt("T", offen, [{"titel": "a", "inhalt": ""}], 0, "M", "",
                                       has_sources=False)[0]["content"]
        self.assertIn("Allgemeinwissen", system, "Ein Bericht ohne Stoff bleibt wie bisher.")

    def test_bound_chapters_are_not_padded(self):
        quelle = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('not plan.get("quellgebunden")', quelle)


class BerichtUmfangTests(unittest.TestCase):
    def test_a_report_on_a_tiny_selection_is_one_call(self):
        # Der markierte Prompt hatte 80 Zeichen; „Mittel" plante fünf Kapitel.
        self.assertIsNone(report_plan("medium", 80, auf_auswahl=True))
        self.assertIsNone(report_plan("long", 900, auf_auswahl=True))

    def test_a_report_on_a_document_stays_in_its_measure(self):
        # Das Whitepaper: 13.040 Zeichen, rund 2.000 Wörter.
        plan = report_plan("medium", 13_040, quellgebunden=True)
        self.assertIsNotNone(plan)
        self.assertLessEqual(plan["sections"] * plan["words"], 13_040 / 6.5 + 1, "Nicht länger als das Dokument.")
        ungebunden = report_plan("medium", 13_040)
        self.assertEqual(ungebunden["sections"] * ungebunden["words"], 8 * 1100)

    def test_long_stays_long_where_the_material_carries_it(self):
        self.assertEqual(report_plan("long", 17_865, auf_auswahl=True)["sections"], 12)
        self.assertEqual(report_plan("long", 20_000)["sections"], 12)


class OberflaechenTests(unittest.TestCase):
    def setUp(self):
        self.js = (WURZEL / "static/app.js").read_text(encoding="utf-8")

    def test_continue_is_only_offered_for_an_unfinished_answer(self):
        start = self.js.index("function renderResponseControls")
        abschnitt = self.js[start:start + 1800]
        self.assertIn('const unfinished = message.doneReason === "length"', abschnitt)
        self.assertIn("if (!unfinished) return;", abschnitt)

    def test_retry_continue_and_follow_up_send_their_files(self):
        self.assertIn('data.append("auftrag_context_ids"', self.js)
        self.assertIn('data.append("folge_context_ids"', self.js)
        for funktion in ("async function retryAssistantMessage", "async function continueAssistantMessage"):
            start = self.js.index(funktion)
            self.assertIn("auftragContextIds:", self.js[start:start + 2600], funktion)
        start = self.js.index("async function sendMessage")
        self.assertIn("folgeContextIds: followContextIds", self.js[start:start + 6000])

    def test_a_marked_prompt_is_run_again_with_its_files(self):
        start = self.js.index("async function executeSelectedSkills")
        self.assertIn("rerunPromptWithSkills", self.js[start:start + 3000])
        start = self.js.index("async function rerunPromptWithSkills")
        abschnitt = self.js[start:start + 3500]
        self.assertIn("auftragContextIds: sourceContextIds", abschnitt)
        self.assertIn("promptRerun: true", abschnitt)
        self.assertIn("auf markierten Prompt anwenden", self.js)
        self.assertNotIn("auf markierte ${sourceLabel}", self.js)

    def test_active_skills_are_shown_at_the_composer(self):
        html = (WURZEL / "static/index.html").read_text(encoding="utf-8")
        self.assertIn('id="composer-skills"', html)
        self.assertIn("function renderComposerSkills", self.js)
        self.assertIn("renderComposerSkills(conversation, selected)", self.js)

    def test_bare_links_become_clickable(self):
        start = self.js.index("function inlineMarkdown")
        self.assertIn("Nackte Adressen", self.js[start:start + 1800])

    def test_unproven_statements_are_shown_as_a_badge(self):
        self.assertIn('class="claim-unbelegt"', self.js)
        css = (WURZEL / "static/styles.css").read_text(encoding="utf-8")
        self.assertIn(".claim-unbelegt", css)


if __name__ == "__main__":
    unittest.main()
