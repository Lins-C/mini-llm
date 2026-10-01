# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Welcher Verlauf ins Modell geht — gemessen am MediFlow-Chat.

Beim letzten Schritt jenes Chats sah glm-5.3-flash 32.000 Zeichen Verlauf:
jede HTML-Fassung ohne ihren <style>-Kopf, den ersten Auftrag („vista Glass
Optik") gar nicht. Das Modell erfand daraufhin ein neues Design.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.verlauf import (
    artefakt_art,
    kuerzen,
    ueberholte_fassungen_ersetzen,
    verlauf_auswaehlen,
    verlauf_budget,
)


def seite(kennung: str, laenge: int = 16_000) -> str:
    kopf = (
        "<!DOCTYPE html>\n<html lang=\"de\"><head><style>\n"
        f".glass{{backdrop-filter:blur(18px)}} /* {kennung} */\n"
    )
    fuellung = "".join(f".r{n}{{margin:{n}px}}\n" for n in range(laenge // 20))
    return kopf + fuellung + f"</style></head><body><h1>{kennung}</h1></body></html>"


def antwort(kennung: str, laenge: int = 16_000) -> str:
    return f"Hier die Fassung {kennung}:\n```html\n{seite(kennung, laenge)}\n```\nViel Spaß!"


def mediflow() -> list[dict[str, str]]:
    """Erster Auftrag, dann sechs Runden mit je einer ganzen HTML-Fassung."""
    nachrichten = [{"role": "user", "content": "Baue eine Arztsuche. Mach den Style vista Glass Optik."}]
    for runde in range(1, 7):
        nachrichten.append({"role": "assistant", "content": antwort(f"V{runde}")})
        if runde < 6:
            nachrichten.append({"role": "user", "content": f"Runde {runde}: ändere die Buttons."})
    return nachrichten


class UeberholteFassungenTests(unittest.TestCase):
    def test_only_the_newest_page_stays_whole(self):
        texte = [e["content"] for e in ueberholte_fassungen_ersetzen(mediflow()) if e["role"] == "assistant"]
        self.assertIn("/* V6 */", texte[-1])
        for alt in texte[:-1]:
            self.assertIn("[Ältere Fassung dieser HTML-Seite", alt)
            self.assertNotIn("<style>", alt)
        # Der Text rund um die Fassung bleibt stehen.
        self.assertTrue(texte[0].startswith("Hier die Fassung V1:"))
        self.assertTrue(texte[0].endswith("Viel Spaß!"))

    def test_a_snippet_does_not_replace_the_page(self):
        nachrichten = [
            {"role": "assistant", "content": antwort("V1")},
            {"role": "user", "content": "und der Knopf?"},
            {"role": "assistant", "content": "So:\n```html\n<a class=\"btn\">🗺️</a>\n```"},
        ]
        self.assertIn("/* V1 */", ueberholte_fassungen_ersetzen(nachrichten)[0]["content"])

    def test_user_messages_are_never_changed(self):
        nachrichten = [
            {"role": "user", "content": antwort("vom Nutzer")},
            {"role": "assistant", "content": antwort("V2")},
        ]
        self.assertEqual(ueberholte_fassungen_ersetzen(nachrichten)[0], nachrichten[0])

    def test_the_kind_of_a_code_block(self):
        self.assertEqual(artefakt_art("html", seite("x")), "html")
        self.assertEqual(artefakt_art("", seite("x")), "html")
        self.assertEqual(artefakt_art("python", "x = 1\n" * 400), "python")
        self.assertEqual(artefakt_art("javascript", "let a = 1;"), "")


class AuswahlTests(unittest.TestCase):
    def test_the_mediflow_case(self):
        auswahl = verlauf_auswaehlen(mediflow(), "mach die Buttons lebendig", budget=33_000)
        text = "\n".join(e["content"] for e in auswahl)
        self.assertIn("vista Glass Optik", text)       # der erste Auftrag
        self.assertIn("/* V6 */", text)                  # die jüngste Fassung …
        self.assertIn("<style>", text)                   # … mit ihrem Kopf
        self.assertIn("</html>", text)                   # … und ihrem Ende
        self.assertLessEqual(sum(len(e["content"]) for e in auswahl), 33_000)
        self.assertEqual(auswahl[0]["content"], mediflow()[0]["content"])

    def test_the_old_tail_cut_lost_the_head(self):
        # So sah es vorher aus: die letzten 12.000 Zeichen einer Fassung.
        self.assertNotIn("<style>", antwort("V6")[-12_000:])

    def test_a_tight_budget_cuts_in_the_middle(self):
        auswahl = verlauf_auswaehlen(mediflow(), "weiter", budget=9_000)
        letzte = auswahl[-1]["content"]
        self.assertIn("Zeichen ausgelassen", letzte)
        self.assertTrue(letzte.startswith("Hier die Fassung V6"))
        self.assertTrue(letzte.endswith("Viel Spaß!"))
        self.assertIn("vista Glass Optik", auswahl[0]["content"])
        self.assertLessEqual(sum(len(e["content"]) for e in auswahl), 9_000)

    def test_middle_cut(self):
        text = "A" * 5000 + "B" * 5000
        gekuerzt = kuerzen(text, 2000)
        self.assertLessEqual(len(gekuerzt), 2000)
        self.assertTrue(gekuerzt.startswith("A"))
        self.assertTrue(gekuerzt.endswith("B"))
        self.assertEqual(kuerzen("kurz", 100), "kurz")


class BudgetTests(unittest.TestCase):
    def test_the_budget_follows_the_window(self):
        with patch.dict(os.environ, {"CHAT_NUM_CTX": "32768"}):
            self.assertEqual(verlauf_budget("granite4.1:8b"), 33_177)
        self.assertEqual(verlauf_budget("glm-5.3-flash:cloud"), 100_000)

    def test_documents_leave_room(self):
        with patch.dict(os.environ, {"CHAT_NUM_CTX": "32768"}):
            self.assertEqual(verlauf_budget("granite4.1:8b", mit_dokument=True), 20_000)
        self.assertEqual(verlauf_budget("glm-5.3-flash:cloud", mit_dokument=True), 60_000)


class EndpunktTests(unittest.TestCase):
    def test_the_first_request_survives_a_long_chat(self):
        from app.main import normalize_history

        verlauf = [{"role": "user", "content": "Erster Auftrag: Glass Optik"}]
        for nummer in range(30):
            verlauf += [
                {"role": "assistant", "content": f"Antwort {nummer}"},
                {"role": "user", "content": f"Frage {nummer}"},
            ]
        ergebnis = normalize_history(json.dumps(verlauf))
        self.assertEqual(ergebnis[0]["content"], "Erster Auftrag: Glass Optik")
        self.assertEqual(ergebnis[-1]["content"], "Frage 29")

    def test_a_long_page_keeps_its_head(self):
        from app.main import normalize_history

        ergebnis = normalize_history(json.dumps([{"role": "assistant", "content": antwort("V1")}]))
        self.assertIn("<style>", ergebnis[0]["content"])

    def test_the_request_uses_the_model_budget(self):
        from app.main import select_history_for_request

        auswahl = select_history_for_request(
            mediflow(), "mach weiter", False, None, model="glm-5.3-flash:cloud",
        )
        text = "\n".join(e["content"] for e in auswahl)
        self.assertIn("/* V6 */", text)
        self.assertIn("vista Glass Optik", text)


if __name__ == "__main__":
    unittest.main()
