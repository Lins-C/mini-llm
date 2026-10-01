# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import unittest

from app.intelligence import (
    _source_score,
    extract_verified_authority_recipient,
)
from app.main import explicitly_requests_web
from app.task_skills import (
    apply_verified_recipient,
    choose_letter_artifact,
    resolve_task_skill,
)


class LetterResearchTests(unittest.TestCase):
    def test_letter_clarification_continues_existing_letter_dialog(self) -> None:
        history = [
            {
                "role": "user",
                "content": "Ich möchte einen Brief schreiben, hilfst du mir dabei?",
            },
            {
                "role": "assistant",
                "content": (
                    "An wen geht der Brief? Was ist das Ziel des Schreibens und "
                    "welchen Tonfall soll ich wählen?"
                ),
            },
        ]
        prompt = (
            "1. an das Finanzamt Borken, Kontaktdaten findest du im Netz. "
            "2. Anfrage zur Änderung der Firmenadresse. "
            "3. sachlich, klar, kurz und prägnant."
        )
        self.assertEqual(resolve_task_skill(prompt, [], history), "letter")

    def test_other_document_skill_overrides_letter_dialog(self) -> None:
        history = [
            {"role": "user", "content": "Ich möchte einen Brief schreiben."},
            {"role": "assistant", "content": "An wen geht der Brief?"},
        ]
        self.assertIsNone(resolve_task_skill(
            "Erstelle daraus einen sachlichen Bericht.",
            ["report"],
            history,
        ))

    def test_explicit_network_lookup_activates_web_research(self) -> None:
        self.assertTrue(explicitly_requests_web(
            "Die Kontaktdaten findest du bitte im Netz."
        ))
        self.assertFalse(explicitly_requests_web(
            "Verwende ausschließlich meine Angaben."
        ))

    def test_official_authority_source_is_ranked_above_template_page(self) -> None:
        query = "Finanzamt Borken Kontaktdaten Adresse"
        official = {
            "title": "Finanzamt Borken",
            "url": "https://www.finanzamt.nrw.de/sites/default/files/finanzamt/5307/orga.pdf",
            "snippet": "Nordring 184 46325 Borken",
            "date": "",
        }
        template = {
            "title": "Musterbrief Finanzamt",
            "url": "https://beispiel.invalid/musterbrief",
            "snippet": "Finanzamt Borken Kontaktdaten Adresse Muster",
            "date": "",
        }
        self.assertGreater(
            _source_score(official, query),
            _source_score(template, query),
        )

    def test_extracts_recipient_only_from_official_source(self) -> None:
        prompt = "Schreibe an das Finanzamt Borken und finde die Adresse im Netz."
        results = [
            {
                "title": "Finanzamt Borken",
                "url": (
                    "https://www.finanzamt.nrw.de/sites/default/files/"
                    "finanzamt/5307/orga.pdf"
                ),
                "snippet": "",
                "content": (
                    "Finanzamt Borken Telefonische Servicezeiten "
                    "Nordring 184 46325 Borken Mo. - Do. 8:00 bis 18:00 Uhr"
                ),
            },
        ]
        recipient = extract_verified_authority_recipient(prompt, results)
        self.assertEqual(recipient["name"], "Finanzamt Borken")
        self.assertEqual(recipient["street"], "Nordring 184")
        self.assertEqual(recipient["postal_code"], "46325")
        self.assertEqual(recipient["city"], "Borken")

    def test_audit_cannot_replace_specific_letter_with_generic_text(self) -> None:
        draft = {
            "recipient": {
                "name": "Finanzamt Borken",
                "department": "",
                "street": "Nordring 184",
                "postal_code": "46325",
                "city": "Borken",
                "country": "",
            },
            "date": "27.07.2026",
            "reference": "",
            "subject": "Änderung der Firmenadresse",
            "salutation": "Sehr geehrte Damen und Herren,",
            "paragraphs": [
                "hiermit teile ich Ihnen die Änderung der Firmenadresse von Beispiel GmbH mit.",
                "Bitte führen Sie künftig die nachfolgend genannte neue Geschäftsanschrift.",
            ],
            "closing": "Mit freundlichen Grüßen",
        }
        generic_audit = {
            "recipient": {
                "name": "",
                "department": "",
                "street": "",
                "postal_code": "",
                "city": "",
                "country": "",
            },
            "date": "27.07.2026",
            "reference": "",
            "subject": "",
            "salutation": "Sehr geehrte Damen und Herren,",
            "paragraphs": [
                "hiermit bitte ich um eine schriftliche Stellungnahme.",
                "Bitte teilen Sie mir den aktuellen Sachstand mit.",
            ],
            "closing": "Mit freundlichen Grüßen",
        }
        prompt = (
            "Brief an das Finanzamt Borken wegen Änderung der Firmenadresse "
            "von Beispiel GmbH."
        )
        artifact = choose_letter_artifact(
            draft,
            generic_audit,
            profile={"name": "Max Mustermann"},
            profile_enabled=True,
            date_label="27.07.2026",
            source_prompt=prompt,
        )
        self.assertEqual(artifact["recipient"]["name"], "Finanzamt Borken")
        self.assertEqual(artifact["subject"], "Änderung der Firmenadresse")
        self.assertIn("Firmenadresse", artifact["paragraphs"][0])

    def test_verified_recipient_overrides_model_placeholders(self) -> None:
        artifact = {
            "recipient": {
                "name": "[Name des Empfängers]",
                "street": "[Straße und Hausnummer]",
                "postal_code": "[PLZ]",
                "city": "[Ort]",
            },
        }
        result = apply_verified_recipient(artifact, {
            "name": "Finanzamt Borken",
            "street": "Nordring 184",
            "postal_code": "46325",
            "city": "Borken",
        })
        self.assertEqual(result["recipient"]["name"], "Finanzamt Borken")
        self.assertEqual(result["recipient"]["street"], "Nordring 184")


if __name__ == "__main__":
    unittest.main()
