# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Mehrere Aufträge nebeneinander: Chatwechsel und Browser beenden keinen Lauf.

Beobachtet: Ein Klick auf einen anderen Chat rief stopGeneration() auf — der
laufende Auftrag wurde auf dem Server abgebrochen, auch wenn er in der Cloud
lief und man nur nicht warten wollte. Senden war in jedem Chat gesperrt,
solange irgendwo etwas lief. Im Coding-Bereich schrieb der Strom eines
Ordners nach dem Wechsel in die Ansicht des nächsten.
"""
from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main

WURZEL = Path(__file__).resolve().parents[1]


def funktion(quelltext: str, kopf: str) -> str:
    """Der Rumpf einer JavaScript-Funktion ab ihrem Kopf bis zur schließenden Klammer."""
    start = quelltext.index(kopf)
    tiefe, ende = 0, start
    for position in range(quelltext.index("{", start), len(quelltext)):
        zeichen = quelltext[position]
        tiefe += zeichen == "{"
        tiefe -= zeichen == "}"
        if tiefe == 0:
            ende = position
            break
    return quelltext[start:ende + 1]


class ServerTests(unittest.IsolatedAsyncioTestCase):
    """Der Server kann es schon — belegt am echten Auftragsverwalter."""

    def auftrag(self, kennung: str, chat: str) -> main.ChatJob:
        return main.ChatJob(
            request_id=kennung, user_id="nutzer", chat_id=chat, user_message_id=f"u-{kennung}",
            assistant_message_id=f"a-{kennung}", model="m", response_prefix="", previous_usage={},
        )

    @staticmethod
    async def quelle(texte: list[str], pause: float):
        for text in texte:
            await asyncio.sleep(pause)
            yield main.event_line("token", content=text)
        yield main.event_line("done", done_reason="stop")

    async def asyncSetUp(self):
        p = patch.object(main, "update_workspace_chat_job", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        self.verwalter = main.ChatJobManager()

    async def asyncTearDown(self):
        await self.verwalter.shutdown()

    async def test_two_chats_run_side_by_side(self):
        a, b = self.auftrag("r-a", "chat-a"), self.auftrag("r-b", "chat-b")
        await self.verwalter.start(a, self.quelle(["Cloud ", "Antwort"], 0.03))
        await self.verwalter.start(b, self.quelle(["Lokal ", "Antwort"], 0.03))
        await asyncio.sleep(0.3)
        self.assertTrue(a.finished and b.finished)
        self.assertEqual((await self.verwalter.get("r-a", "nutzer")).snapshot()["content"], "Cloud Antwort")
        self.assertEqual((await self.verwalter.get("r-b", "nutzer")).snapshot()["content"], "Lokal Antwort")

    async def test_leaving_the_stream_does_not_end_the_job(self):
        """Wie ein geschlossener Browser: Der Zuhörer geht, der Auftrag bleibt."""
        a = self.auftrag("r-c", "chat-a")
        await self.verwalter.start(a, self.quelle(["eins ", "zwei ", "drei"], 0.05))
        zuhoerer = self.verwalter.subscribe("r-c", "nutzer")
        await zuhoerer.__anext__()
        await zuhoerer.aclose()
        await asyncio.sleep(0.4)
        self.assertTrue(a.finished)
        self.assertEqual(a.snapshot()["content"], "eins zwei drei")


class ChatOberflaecheTests(unittest.TestCase):
    def setUp(self):
        self.js = (WURZEL / "static/app.js").read_text(encoding="utf-8")

    def klick_auf_chat(self) -> str:
        return self.js.split('row.addEventListener("click", async () => {', 1)[1].split("});", 1)[0]

    def test_switching_chats_no_longer_stops_the_run(self):
        klick = self.klick_auf_chat()
        self.assertNotIn("stopGeneration", klick)
        self.assertIn("koppleAb();", klick)
        self.assertIn("refreshActiveGenerationState();", klick)

    def test_a_new_chat_does_not_stop_the_run_either(self):
        self.assertEqual(self.js.count("koppleAb();\n  createChat();"), 2)
        self.assertNotIn("if (state.generating) await stopGeneration();\n  createChat();", self.js)

    def test_detaching_only_ends_the_display_not_the_job(self):
        rumpf = funktion(self.js, "function koppleAb()")
        self.assertNotIn("/api/stop", rumpf)
        self.assertIn("state.controller.abort()", rumpf)
        self.assertIn("abgekoppelteAuftraege().add(state.requestId)", rumpf)

    def test_the_explicit_stop_still_stops(self):
        self.assertIn("/api/stop/", funktion(self.js, "async function stopGeneration()"))

    def test_a_detached_answer_keeps_generating_in_the_background(self):
        self.assertIn('if (error.name === "AbortError" && abgekoppelteAuftraege().has(activeRequestId))', self.js)
        zweig = self.js.split("abgekoppelteAuftraege().has(activeRequestId)) {", 1)[1][:300]
        self.assertIn('assistantMessage.status = "generating";', zweig)

    def test_the_old_chat_does_not_reset_the_new_one(self):
        self.assertIn("if (state.requestId === activeRequestId) {", self.js)
        abschluss = self.js.split("if (abgekoppelteAuftraege().delete(activeRequestId)) {", 1)[1][:600]
        self.assertIn("scheduleJobSync(500);", abschluss)
        self.assertNotIn("finishGeneration()", abschluss.split("} else if (detachedJob)")[0])

    def test_running_chats_are_marked_in_the_sidebar(self):
        self.assertIn('class="chat-running"', self.js)
        css = (WURZEL / "static/styles.css").read_text(encoding="utf-8")
        self.assertIn(".chat-running {", css)
        self.assertIn("prefers-reduced-motion: reduce) { .chat-running", css)


class JoshiOberflaecheTests(unittest.TestCase):
    """JOSHI ersetzt die Coding-Ansicht; ihr Strom läuft wie der Chat im Hintergrund."""

    def setUp(self):
        self.js = (WURZEL / "static/joshi.js").read_text(encoding="utf-8")

    def test_leaving_joshi_only_hides_the_view(self):
        rumpf = funktion(self.js, "function schliesseAnsicht()")
        self.assertNotIn("abbrechen", rumpf)
        self.assertIn("ansicht.hidden = true", rumpf)

    def test_the_assets_were_republished(self):
        html = (WURZEL / "static/index.html").read_text(encoding="utf-8")
        self.assertNotIn("coding.js", html)
        for datei in ("app.js?v=64", "joshi.js?v=10", "styles.css?v=71"):
            self.assertIn(datei, html)

if __name__ == "__main__":
    unittest.main()
