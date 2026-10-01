# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

from app.exports import build_export
from app.main import is_email_draft_request, is_existing_content_email_transform


EMAIL_CONTENT = """
**Empfänger:** max.mustermann@example.com
**Betreff:** Update KI-Marktentwicklungen Juli 2026

Hallo Herr Mustermann,

hier ist die Zusammenfassung der aktuellen KI-Entwicklungen:

- NVIDIA reduziert langfristige Finanzmittel.
- Google stellt neue Gemini-Modelle vor.

Mit freundlichen Grüßen,

[Ihr Name]
""".strip()


class EmailExportTests(unittest.TestCase):
    def test_email_export_sets_real_headers_and_removes_metadata_from_body(self) -> None:
        payload, media_type, filename = build_export(
            "eml",
            "Suche nach aktuellen Nachrichten",
            EMAIL_CONTENT,
            email_request_prompt=(
                "Schreibe den Inhalt als E-Mail kurz und prägnant zusammen. "
                "Empfänger max.mustermann@example.com"
            ),
            email_sender_name="Max Mustermann",
            email_sender_email="max@example.com",
        )
        message = BytesParser(policy=policy.default).parsebytes(payload)

        self.assertEqual(media_type, "message/rfc822")
        self.assertEqual(message["To"], "max.mustermann@example.com")
        self.assertEqual(
            message["Subject"],
            "Zusammenfassung der aktuellen KI-Entwicklungen",
        )
        self.assertEqual(
            message["From"],
            "Max Mustermann <max@example.com>",
        )
        self.assertEqual(message["X-Unsent"], "1")
        self.assertEqual(
            filename,
            "zusammenfassung-der-aktuellen-ki-entwicklungen.eml",
        )
        body = message.get_body(preferencelist=("plain",)).get_content()
        self.assertNotIn("Empfänger:", body)
        self.assertNotIn("Betreff:", body)
        self.assertNotIn("[Ihr Name]", body)
        self.assertIn("Max Mustermann", body)
        self.assertIn("Hallo Herr Mustermann", body)

    def test_explicit_subject_in_user_request_has_priority(self) -> None:
        payload, _, _ = build_export(
            "eml",
            "Chatname",
            EMAIL_CONTENT,
            email_request_prompt=(
                "Erstelle eine E-Mail. Betreff: Interner KI-Lagebericht"
            ),
        )
        message = BytesParser(policy=policy.default).parsebytes(payload)
        self.assertEqual(message["Subject"], "Interner KI-Lagebericht")

    def test_email_request_is_recognized_and_frontend_sends_prompt(self) -> None:
        self.assertTrue(is_email_draft_request(
            "Schreibe den Inhalt als E-Mail kurz und prägnant zusammen."
        ))
        self.assertTrue(is_existing_content_email_transform(
            "Schreibe den Inhalt als E-Mail kurz und prägnant zusammen."
        ))
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "static" / "app.js").read_text(encoding="utf-8")
        index_html = (root / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("request_prompt:", app_js)
        self.assertIn('format === "eml" ? "/api/email-draft"', app_js)
        self.assertIn("mailto:", app_js)
        self.assertIn("showEmailComposeDialog", app_js)
        self.assertIn('id="email-compose-open"', index_html)
        self.assertIn("In Mail öffnen", index_html)
        self.assertNotIn("compose.click()", app_js)
        # Auf die Versionsnummer selbst kommt es nicht an, nur darauf, dass es
        # eine gibt — sonst liefert Safari nach einer Änderung den alten Stand.
        self.assertRegex(index_html, r"app\.js\?v=\d+")

class ExportSizeTests(unittest.TestCase):
    """Ein langer Bericht darf den Export nicht abweisen."""

    def test_a_long_marked_text_does_not_break_the_export(self):
        from app.main import ExportPayload

        # Beim Anwenden eines Skills steht der komplette markierte Bericht im
        # request_prompt — vorher gab das ein 422 und ein rotes Ausrufezeichen.
        payload = ExportPayload(
            format="pdf",
            content="Inhalt",
            request_prompt="Wende die aktiven Skills an. " + "x" * 60000,
        )
        self.assertLessEqual(len(payload.request_prompt), 12000)

    def test_a_very_long_report_still_becomes_a_pdf(self):
        from io import BytesIO

        from pypdf import PdfReader

        from app.exports import build_pdf

        text = "\n\n".join(
            f"## Kapitel {nummer}\n\n" + ("Ein Satz mit Inhalt und Beleg [[1]]. " * 120)
            for nummer in range(1, 15)
        )
        daten = build_pdf("Langer Bericht", text)
        seiten = len(PdfReader(BytesIO(daten)).pages)
        self.assertGreater(seiten, 12)


if __name__ == "__main__":
    unittest.main()
