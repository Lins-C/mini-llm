# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Skill auf markierter Seite — durch den echten Chat-Endpunkt.

Beobachtet mit glm-5.3-flash: „Protokoll", „Zusammenfassung" und „Analyse" auf
den markierten Dienstplan-Generator gaben die HTML-Seite zurück. Ursache war
eine Weiche, die im markierten Inhalt „HTML" und „generieren" fand und dem
Modell befahl, eine vollständige HTML-Datei auszugeben. Hier läuft der ganze
Endpunkt gegen ein nachgestelltes Ollama.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx

import app.main as main

SEITE = """<!DOCTYPE html><html lang="de"><head><title>Dienstplan-Generator</title>
<style>.tag.fk{background:#1a4d2e;color:#7ee2a8}</style></head><body>
<h1>Dienstplan-Generator</h1><button>Plan generieren</button>
<script>let staff=[{n:"Müller",fk:true},{n:"Koch",fk:false}];</script></body></html>"""

SKILL_AUFTRAG = (
    "Wende die aktiven Skills ausschließlich auf den nachfolgend markierten Inhalt an. "
    "Gib nur das fertige Ergebnis in der Form der aktiven Skills aus.\n\n"
    "--- START MARKIERTER INHALT (KI-Ausgabe) ---\n```html\n" + SEITE
    + "\n```\n--- ENDE MARKIERTER INHALT ---"
)

# So begann die beobachtete Antwort auf „Protokoll".
ECHO = "```html\n<!DOCTYPE html>\n<html lang=\"de\"><head><style>.tag.fk{background:#1a4d2e}\n"
PROTOKOLL = "# Protokoll: Dienstplan-Generator\n\n- Beschluss: Pläne werden automatisch erzeugt."


class Auftraege:
    """Ersetzt den Hintergrund-Auftragsverwalter und reicht den Strom durch."""

    def __init__(self) -> None:
        self.strom = None

    async def start(self, job, strom) -> None:
        self.strom = strom

    async def subscribe(self, request_id, user_id):
        async for zeile in self.strom:
            yield zeile


class SkillEndpunktTests(unittest.IsolatedAsyncioTestCase):
    async def lauf(
        self,
        stromantwort: str,
        zweitantwort: str,
        *,
        prompt: str = SKILL_AUFTRAG,
        skills: str = '["protocol"]',
        aktion: bool = True,
        verlauf: str = "[]",
        fehler: tuple[int, str] | None = None,
    ):
        gesendet: list[dict] = []

        def ollama(anfrage: httpx.Request) -> httpx.Response:
            nutzlast = json.loads(anfrage.content)
            gesendet.append(nutzlast)
            if fehler:
                return httpx.Response(fehler[0], json={"error": fehler[1]})
            if nutzlast.get("stream"):
                zeilen = [
                    json.dumps({"message": {"content": stromantwort[i:i + 40]}, "done": False})
                    for i in range(0, len(stromantwort), 40)
                ]
                zeilen.append(json.dumps({
                    "message": {"content": ""}, "done": True, "done_reason": "stop",
                    "prompt_eval_count": 5, "eval_count": 5,
                }))
                return httpx.Response(200, content="\n".join(zeilen).encode())
            return httpx.Response(200, json={"message": {"content": zweitantwort}, "done": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as client:
            anfrage = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http=client)))
            with patch.object(main, "require_user", return_value={"id": 1}), \
                    patch.object(main, "chat_jobs", Auftraege()), \
                    patch.object(main, "load_profile", return_value=(None, {})), \
                    patch.object(main, "allowed_context_ids", return_value=[]):
                antwort = await main.chat(
                    request=anfrage, model="glm-5.3-flash:cloud", prompt=prompt,
                    history=verlauf, request_id=f"test-{uuid.uuid4()}", chat_id="c1",
                    user_message_id="u1", assistant_message_id="a1", response_prefix="",
                    previous_usage="{}", temperature=0.7, web_enabled=False,
                    profile_context_enabled=False, persona_mode="global", chat_persona="",
                    active_skills=skills, skill_options="{}", skill_action=aktion,
                    context_ids="[]", files=None,
                )
                ereignisse = []
                async for zeile in antwort.body_iterator:
                    text = zeile.decode() if isinstance(zeile, bytes) else zeile
                    ereignisse += [json.loads(teil) for teil in text.splitlines() if teil.strip()]
        ausgabe = "".join(e.get("content", "") for e in ereignisse if e.get("type") == "token")
        return gesendet, ereignisse, ausgabe

    @staticmethod
    def systeme(nutzlast: dict) -> list[str]:
        return [m["content"] for m in nutzlast["messages"] if m["role"] == "system"]

    async def test_no_html_order_and_no_code_reaches_the_user(self):
        gesendet, ereignisse, ausgabe = await self.lauf(ECHO * 4, PROTOKOLL)
        systeme = self.systeme(gesendet[0])
        self.assertFalse(any("HTML-Artefakt" in text for text in systeme))
        self.assertTrue(any("MARKIERTER INHALT WAR HTML-CODE" in text for text in systeme))
        nutzer = gesendet[0]["messages"][-1]["content"]
        self.assertNotIn("<style", nutzer)
        self.assertIn("DATEN IM SKRIPT – staff", nutzer)
        # Die Code-Wache fängt das Echo ab und holt das Ergebnis neu.
        self.assertNotIn("<!DOCTYPE", ausgabe)
        self.assertEqual(ausgabe, PROTOKOLL)
        self.assertTrue(any("Code zurück" in str(e.get("message", "")) for e in ereignisse))
        self.assertEqual(gesendet[1]["messages"][-1]["content"], main.CODEECHO_KORREKTUR)

    async def test_a_second_echo_ends_with_an_honest_error(self):
        _, ereignisse, ausgabe = await self.lauf(ECHO * 4, ECHO)
        self.assertEqual(ausgabe, "")
        self.assertTrue(any(
            e.get("type") == "error" and "erneut Code" in e.get("message", "") for e in ereignisse
        ))

    async def test_a_proper_answer_streams_unchanged(self):
        gut = PROTOKOLL + "\n" + "- Punkt mit Inhalt.\n" * 30
        gesendet, _, ausgabe = await self.lauf(gut, "wird nicht gebraucht")
        self.assertEqual(ausgabe, gut)
        self.assertEqual(len(gesendet), 1)

    async def test_a_short_proper_answer_is_not_swallowed(self):
        _, _, ausgabe = await self.lauf("Kurzes Protokoll.", "x")
        self.assertEqual(ausgabe, "Kurzes Protokoll.")

    async def test_a_real_html_request_still_gets_the_html_order(self):
        gesendet, _, _ = await self.lauf(
            "```html\n<!DOCTYPE html><html></html>\n```", "",
            prompt="Bau mir eine HTML-Seite mit einem Quiz", skills="[]", aktion=False,
        )
        self.assertTrue(any("HTML-Artefakt" in text for text in self.systeme(gesendet[0])))

    async def test_a_follow_up_keeps_the_whole_page_and_its_design(self):
        verlauf = json.dumps([
            {"role": "user", "content": "Baue eine Arztsuche in vista Glass Optik"},
            {"role": "assistant", "content": (
                "```html\n<!DOCTYPE html><html><head><style>.glass{backdrop-filter:blur(18px)}"
                "</style></head><body></body></html>\n```"
            )},
        ])
        gesendet, _, _ = await self.lauf(
            "```html\n<!DOCTYPE html><html></html>\n```", "",
            prompt="mach nun die Buttons lebendig", skills="[]", aktion=False, verlauf=verlauf,
        )
        systeme = self.systeme(gesendet[0])
        self.assertTrue(any("HTML-Artefakt" in text for text in systeme))
        self.assertTrue(any("Überarbeitung der letzten HTML-Fassung" in text for text in systeme))
        verlaufstext = "\n".join(m["content"] for m in gesendet[0]["messages"] if m["role"] != "system")
        self.assertIn("backdrop-filter", verlaufstext)
        self.assertIn("vista Glass Optik", verlaufstext)


LIMIT = (
    "you (Beispiel-GmbH) have reached your session usage limit, upgrade for higher "
    "limits: https://ollama.com/upgrade or add usage credits: https://ollama.com/settings"
)


class NutzungslimitTests(unittest.IsolatedAsyncioTestCase):
    """Ein erschöpftes Cloud-Kontingent wird benannt und nicht wiederholt."""

    async def test_the_chat_names_the_limit_without_retrying(self):
        gesendet, ereignisse, ausgabe = await SkillEndpunktTests().lauf(
            "", "", prompt="Hallo", skills="[]", aktion=False, fehler=(429, LIMIT),
        )
        self.assertEqual(len(gesendet), 1)
        fehler = [e["message"] for e in ereignisse if e.get("type") == "error"]
        self.assertEqual(fehler, [main.NUTZUNGSLIMIT_TEXT])
        self.assertFalse(any("neuer Versuch" in str(e.get("message", "")) for e in ereignisse))

    async def test_a_non_streamed_call_is_not_repeated(self):
        aufrufe = 0

        def ollama(anfrage: httpx.Request) -> httpx.Response:
            nonlocal aufrufe
            aufrufe += 1
            return httpx.Response(429, json={"error": LIMIT})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as client:
            antwort = await main.ollama_chat_post(client, {"model": "glm-5.3-flash:cloud", "messages": []})
        self.assertEqual(antwort.status_code, 429)
        self.assertEqual(aufrufe, 1)

    def test_an_ordinary_throttle_is_not_mistaken_for_the_limit(self):
        self.assertTrue(main.ist_nutzungslimit(LIMIT))
        self.assertFalse(main.ist_nutzungslimit('{"error":"too many requests"}'))


if __name__ == "__main__":
    unittest.main()
