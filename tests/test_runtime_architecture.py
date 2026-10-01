# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.main import (
    build_personalization_system,
    event_line,
    model_fit,
    normalize_ollama_model_command,
    ollama_complete,
    ollama_fehlertext,
    ollama_model_payload,
    ollama_thinking_control,
    persisted_chat_job_snapshot,
    select_history_for_request,
)
from app.task_skills import active_skills_system_prompt


class RuntimeArchitectureTests(unittest.TestCase):
    def test_handled_letter_skill_is_not_sent_twice(self) -> None:
        prompt = active_skills_system_prompt(["letter"], {}, handled_skill="letter")
        self.assertEqual(prompt, "")

    def test_translation_runtime_contains_only_selected_contract(self) -> None:
        prompt = active_skills_system_prompt(
            ["translation"],
            {"translation_language": "fr"},
        )
        self.assertIn("Französisch", prompt)
        self.assertIn("ausschließlich die Übersetzung", prompt)
        self.assertNotIn("PROTOKOLL", prompt)
        self.assertLess(len(prompt), 700)

    def test_long_history_keeps_recent_and_relevant_older_turn(self) -> None:
        messages = []
        for index in range(10):
            topic = "Finanzamt Borken Aktenzeichen" if index == 1 else f"Thema {index}"
            messages.extend((
                {"role": "user", "content": f"{topic}: Nutzerfrage"},
                {"role": "assistant", "content": f"{topic}: Antwort"},
            ))
        selected = select_history_for_request(
            messages,
            "Was war das Aktenzeichen beim Finanzamt Borken?",
            False,
        )
        content = "\n".join(item["content"] for item in selected)
        self.assertIn("Finanzamt Borken Aktenzeichen", content)
        self.assertIn("Thema 9", content)
        self.assertLess(len(selected), len(messages))

    def test_letter_sender_data_stays_out_of_model_context(self) -> None:
        profile = {
            "name": "Admin",
            "email": "admin@example.com",
            "address": {"street": "Testweg 1", "postal_code": "12345", "city": "Teststadt"},
            "global_persona": "Antworte sachlich.",
        }
        prompt = build_personalization_system(
            profile,
            True,
            "global",
            "",
            "Schreibe einen Brief an das Finanzamt.",
            "letter",
        )
        self.assertIn("Antworte sachlich", prompt)
        self.assertNotIn("Testweg 1", prompt)
        self.assertNotIn("admin@example.com", prompt)

    def test_role_is_not_sent_when_personal_context_is_disabled(self) -> None:
        prompt = build_personalization_system(
            {"global_persona": "Antworte nur als KI-Architekt."},
            False,
            "global",
            "",
            "Hallo, wie geht es dir?",
        )
        self.assertEqual(prompt, "")

    def test_cloud_authorization_error_is_explained_without_raw_json(self) -> None:
        message = ollama_fehlertext('{"error":"Unauthorized"}', 401)
        self.assertIn("Anmeldung", message)
        self.assertIn("ollama signin", message)
        self.assertNotIn('{"error"', message)

    def test_document_format_wins_when_skills_are_combined(self) -> None:
        prompt = active_skills_system_prompt(
            ["report", "translation", "summary", "analysis"],
            {"translation_language": "en"},
        )
        self.assertIn("Endformat: Bericht", prompt)
        self.assertIn("vollständig auf Englisch", prompt)
        self.assertIn("keine zusätzliche Fünf-Punkte-Zusammenfassung", prompt)
        self.assertIn("keine zweite Analyse-Struktur", prompt)
        self.assertIn("HTML, Markdown, Tabellen und Code", prompt)


class OllamaModelManagerTests(unittest.TestCase):
    def test_an_18_gb_model_is_red_on_a_16_gb_mac(self) -> None:
        fit = model_fit(18 * 1024**3, 16 * 1024**3)
        self.assertEqual(fit["status"], "too-large")

    def test_a_small_model_is_green_on_a_32_gb_mac(self) -> None:
        fit = model_fit(4 * 1024**3, 32 * 1024**3)
        self.assertEqual(fit["status"], "good")

    def test_the_terminal_accepts_only_ollama_pull(self) -> None:
        self.assertEqual(normalize_ollama_model_command("ollama pull qwen3:8b"), "qwen3:8b")
        with self.assertRaises(ValueError):
            normalize_ollama_model_command("ollama pull qwen3:8b; rm -rf ~")

    def test_cloud_models_are_not_judged_by_local_ram(self) -> None:
        for name in ("gemma4:cloud", "gpt-oss:120b-cloud"):
            model = ollama_model_payload(
                {"name": name, "size": 512, "details": {}},
                16 * 1024**3,
            )
            self.assertEqual(model["fit"]["status"], "cloud")


class OllamaReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_temporary_502_is_retried_without_user_action(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(502, text="temporary gateway failure")
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Fertige HTML-Seite"},
                    "prompt_eval_count": 10,
                    "eval_count": 5,
                },
            )

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("app.main.OLLAMA_URL", "http://ollama.test"), patch(
                "app.main.OLLAMA_RETRY_DELAYS", (0.0, 0.0, 0.0)
            ):
                answer = await ollama_complete(
                    client,
                    "test-model",
                    [{"role": "user", "content": "Baue HTML"}],
                    usage=usage,
                )

        self.assertEqual(answer, "Fertige HTML-Seite")
        self.assertEqual(calls, 3)
        self.assertEqual(usage, {
            "prompt_tokens": 10, "completion_tokens": 5, "calls": 1,
            "provider_input_usage_reported": True,
            "provider_output_usage_reported": True,
            "provider_input_usage_calls": 1,
            "provider_output_usage_calls": 1,
        })

    async def test_glm_uses_a_low_thinking_budget(self) -> None:
        observed_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed_payload.update(json.loads(request.content))
            return httpx.Response(200, json={"message": {"content": "OK"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("app.main.OLLAMA_URL", "http://ollama.test"):
                self.assertEqual(
                    await ollama_complete(
                        client,
                        "glm-5.3-flash:cloud",
                        [{"role": "user", "content": "OK"}],
                    ),
                    "OK",
                )

        self.assertEqual(observed_payload["think"], "low")
        self.assertEqual(ollama_thinking_control("gpt-oss:120b-cloud"), "low")
        self.assertIsNone(ollama_thinking_control("gemma4:cloud"))

    async def test_an_empty_success_response_is_not_accepted(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            content = "" if calls == 1 else "Jetzt sichtbar"
            return httpx.Response(200, json={"message": {"content": content}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("app.main.OLLAMA_URL", "http://ollama.test"):
                answer = await ollama_complete(
                    client,
                    "test-model",
                    [{"role": "user", "content": "Antworte"}],
                )

        self.assertEqual(answer, "Jetzt sichtbar")
        self.assertEqual(calls, 2)

    async def test_a_persisted_job_can_be_recovered_after_restart(self) -> None:
        chat = {
            "id": "chat-1",
            "contextIds": [],
            "messages": [{
                "id": "assistant-1",
                "role": "assistant",
                "requestId": "request-1",
                "content": "Bisheriger Inhalt",
                "status": "done",
                "model": "qwen3:8b",
            }],
        }
        snapshot = persisted_chat_job_snapshot(chat, "request-1")
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["content"], "Bisheriger Inhalt")
        self.assertTrue(snapshot["persisted"])


class StartScriptTests(unittest.TestCase):
    """Eine gestoppte Zugabe darf den Start der WebUI nicht verhindern."""

    def _tailscale_block(self) -> str:
        skript = (Path(__file__).resolve().parent.parent / "start.command").read_text(
            encoding="utf-8"
        )
        treffer = re.search(
            r'^TAILSCALE_URL=""$.*?^fi$\n^if \[\[ -n "\$TAILSCALE" \]\].*?^fi$',
            skript,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(treffer, "Der Tailscale-Abschnitt wurde umbenannt.")
        return treffer.group(0)

    def test_a_stopped_tailscale_does_not_abort_the_start(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            attrappe = Path(ordner) / "tailscale"
            attrappe.write_text(
                '#!/bin/sh\necho "Tailscale is stopped."\nexit 1\n', encoding="utf-8"
            )
            attrappe.chmod(0o755)
            lauf = subprocess.run(
                ["bash", "-euo", "pipefail", "-c",
                 self._tailscale_block() + '\necho "URL=[$TAILSCALE_URL]"'],
                capture_output=True, text=True,
                env={**os.environ, "PATH": f"{ordner}:{os.environ['PATH']}"},
            )
        self.assertEqual(lauf.returncode, 0, f"Start bricht ab: {lauf.stderr}")
        self.assertIn("URL=[]", lauf.stdout)

    def test_a_running_tailscale_yields_the_private_address(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            attrappe = Path(ordner) / "tailscale"
            attrappe.write_text(
                '#!/bin/sh\necho "https://mac-mini.example.ts.net (tailnet only)"\n',
                encoding="utf-8",
            )
            attrappe.chmod(0o755)
            lauf = subprocess.run(
                ["bash", "-euo", "pipefail", "-c",
                 self._tailscale_block() + '\necho "URL=[$TAILSCALE_URL]"'],
                capture_output=True, text=True,
                env={**os.environ, "PATH": f"{ordner}:{os.environ['PATH']}"},
            )
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        self.assertIn("URL=[https://mac-mini.example.ts.net]", lauf.stdout)

    def test_a_healthy_service_is_not_restarted_on_every_open(self) -> None:
        skript = (Path(__file__).resolve().parent.parent / "start.command").read_text(
            encoding="utf-8"
        )
        self.assertIn('SERVICE_WAS_READY=false', skript)
        self.assertIn('SOURCE_CHANGED=false', skript)
        self.assertIn('if ! open "$LOCAL_URL"; then', skript)
        self.assertIn('Fehlgeschlagener Schritt:', skript)


if __name__ == "__main__":
    unittest.main()
