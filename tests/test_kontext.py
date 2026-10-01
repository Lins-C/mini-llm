# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Dokumente passen jetzt so weit ins Fenster, wie das Modell es verträgt.

Beobachtet: Ein eingefügter Text mit 26.482 Zeichen — rund 7.500 Tokens,
viermal in das lokale 32k-Fenster passend — lief durch fünf nacheinander
laufende Einzelanalysen, bevor die eigentliche Antwort begann. Grund war eine
feste Direktgrenze von 18.000 Zeichen, gleich welches Modell antwortete.
"""
from __future__ import annotations

import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import kontext
from app.main import rank_context_chunks

WURZEL = Path(__file__).resolve().parents[1]
LOKAL, CLOUD = "granite4.1:8b", "glm-5.3-flash:cloud"


def dokument(kennung: str, name: str, zeichen: int, wort: str = "Inhalt") -> dict:
    """Ein gespeichertes Dokument wie im Kontextspeicher: Text plus Abschnitte."""
    from app.intelligence import split_text

    satz = f"{wort} steht in diesem Satz mit einigen weiteren Wörtern. "
    text = (satz * (zeichen // len(satz) + 1))[:zeichen]
    return {
        "id": kennung * 64, "name": name, "kind": "document", "text": text,
        "chunks": [{"text": teil} for teil in split_text(text)],
    }


class Grundlage(unittest.TestCase):
    """Feste Umgebung: 32k lokal, keine echte Ollama-Datenbank."""

    def setUp(self) -> None:
        kontext._zwischenspeicher.clear()
        umgebung = mock.patch.dict(os.environ, {"CHAT_NUM_CTX": "32768"}, clear=False)
        umgebung.start()
        self.addCleanup(umgebung.stop)
        self.addCleanup(kontext._zwischenspeicher.clear)


class ModellTests(Grundlage):
    def test_cloud_models_are_recognised(self):
        for name in ("glm-5.3-flash:cloud", "kimi-k3:cloud", "gpt-oss:120b-cloud"):
            self.assertTrue(kontext.ist_cloud_modell(name), name)
        for name in ("granite4.1:8b", "ministral-3:8b", "gemma4:12b-mlx", ""):
            self.assertFalse(kontext.ist_cloud_modell(name), name)

    def test_the_local_budget_follows_the_window(self):
        self.assertEqual(kontext.kontext_tokens(LOKAL), 32768)
        self.assertEqual(kontext.material_budget(LOKAL), int((32768 - 8192) * 3.0))

    def test_the_cloud_budget_is_capped_per_request(self):
        self.assertEqual(kontext.kontext_tokens(CLOUD), kontext.CLOUD_KONTEXT)
        self.assertGreater(kontext.material_budget(CLOUD), kontext.material_budget(LOKAL))

    def test_only_cloud_models_run_in_parallel(self):
        self.assertEqual(kontext.parallelitaet(LOKAL), 1)
        self.assertEqual(kontext.parallelitaet(CLOUD), 4)

    def test_local_calls_always_carry_the_window(self):
        """Ohne num_ctx kam ein 26.482-Zeichen-Text mit 2.050 Tokens an — gekürzt."""
        self.assertEqual(kontext.kontext_optionen(LOKAL), {"num_ctx": 32768})
        self.assertEqual(kontext.kontext_optionen(CLOUD), {})
        with mock.patch.dict(os.environ, {"CHAT_NUM_CTX": "", "OLLAMA_CONTEXT_LENGTH": ""}), \
                mock.patch.object(kontext, "OLLAMA_EINSTELLUNGEN", Path("/nicht/vorhanden.sqlite")):
            kontext._zwischenspeicher.clear()
            self.assertEqual(kontext.kontext_optionen(LOKAL), {"num_ctx": kontext.LOKAL_RUECKFALL})


class OllamaReglerTests(unittest.TestCase):
    """Der Regler der Ollama-App ist die Quelle — ohne Neustart wirksam."""

    def setUp(self) -> None:
        kontext._zwischenspeicher.clear()
        self.addCleanup(kontext._zwischenspeicher.clear)
        self.ordner = tempfile.TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)

    def mit_datenbank(self, fenster: int | None):
        pfad = Path(self.ordner.name) / "db.sqlite"
        if fenster is not None:
            verbindung = sqlite3.connect(pfad)
            verbindung.execute("create table settings (id integer, context_length integer)")
            verbindung.execute("insert into settings values (1, ?)", (fenster,))
            verbindung.commit()
            verbindung.close()
        return mock.patch.multiple(kontext, OLLAMA_EINSTELLUNGEN=pfad)

    def test_the_slider_value_is_read(self):
        with mock.patch.dict(os.environ, {"CHAT_NUM_CTX": "", "OLLAMA_CONTEXT_LENGTH": ""}), \
                self.mit_datenbank(32768):
            self.assertEqual(kontext.lokales_kontextfenster(), 32768)

    def test_without_settings_the_fallback_is_cautious(self):
        with mock.patch.dict(os.environ, {"CHAT_NUM_CTX": "", "OLLAMA_CONTEXT_LENGTH": ""}), \
                self.mit_datenbank(None):
            self.assertEqual(kontext.lokales_kontextfenster(), kontext.LOKAL_RUECKFALL)

    def test_an_explicit_setting_wins(self):
        with mock.patch.dict(os.environ, {"CHAT_NUM_CTX": "16384"}), self.mit_datenbank(32768):
            self.assertEqual(kontext.lokales_kontextfenster(), 16384)


class BlockTests(Grundlage):
    def test_consecutive_parts_are_grouped(self):
        abschnitte = [(f"T{n}", "x" * 4000) for n in range(10)]
        bloecke = kontext.bloecke_bilden(abschnitte, 10_000)
        self.assertEqual([len(block) for block in bloecke], [2, 2, 2, 2, 2])
        self.assertEqual([label for block in bloecke for label, _ in block],
                         [f"T{n}" for n in range(10)])

    def test_an_oversized_part_stays_alone(self):
        bloecke = kontext.bloecke_bilden([("A", "x" * 50), ("B", "y" * 500), ("C", "z" * 50)], 100)
        self.assertEqual([[label for label, _ in block] for block in bloecke], [["A"], ["B"], ["C"]])


class PlanTests(Grundlage):
    """Welcher Weg für welches Material — an beobachteten Größen gemessen."""

    def plane(self, kontexte, frage, modell=LOKAL, vorrang=None):
        return kontext.plane_material(kontexte, frage, modell, rank_context_chunks, vorrang)

    def test_the_observed_text_goes_in_directly(self):
        """26.482 Zeichen, fünf Abschnitte — jetzt ohne einen Zusatzaufruf."""
        text = dokument("a", "eingefuegter-text.txt", 26_482)
        self.assertEqual(len(text["chunks"]), 5)
        weg, bloecke, zahlen = self.plane([text], "Was steht darin?", vorrang={text["id"]})
        self.assertEqual(weg, "direkt")
        self.assertEqual(len(bloecke), 1)
        self.assertEqual(zahlen["weg"], "vollständig")
        self.assertEqual(sum(len(t) for _, t in bloecke[0]), 26_482)

    def test_a_short_pdf_goes_in_directly(self):
        pdf = dokument("b", "drei-seiten.pdf", 9_000)
        weg, _, _ = self.plane([pdf], "Fasse das Dokument zusammen.", vorrang={pdf["id"]})
        self.assertEqual(weg, "direkt")

    def test_a_long_pdf_with_a_targeted_question_uses_the_best_passages(self):
        pdf = dokument("c", "handbuch-200-seiten.pdf", 500_000)
        weg, bloecke, zahlen = self.plane([pdf], "Was steht zur Gewährleistung?", vorrang={pdf["id"]})
        self.assertEqual(weg, "direkt")
        self.assertEqual(zahlen["weg"], "passendste Stellen")
        belegt = sum(len(t) for _, t in bloecke[0])
        budget = kontext.material_budget(LOKAL)
        self.assertLessEqual(belegt, budget)
        # Gemessen wird die Ausnutzung des Fensters, nicht eine Anzahl: Lokal
        # sind das bei rund 5.700 Zeichen je Abschnitt eben zwölf Abschnitte.
        self.assertGreaterEqual(belegt, budget * 0.85, "Das Fenster wird nicht ausgenutzt.")

    def test_the_cloud_window_takes_far_more_passages(self):
        pdf = dokument("m", "handbuch-200-seiten.pdf", 500_000)
        _, lokal, _ = self.plane([pdf], "Was steht zur Gewährleistung?", LOKAL, {pdf["id"]})
        _, cloud, _ = self.plane([pdf], "Was steht zur Gewährleistung?", CLOUD, {pdf["id"]})
        self.assertGreater(len(cloud[0]), 4 * len(lokal[0]))

    def test_a_long_pdf_to_summarise_needs_few_blocks_locally(self):
        pdf = dokument("d", "handbuch-200-seiten.pdf", 500_000)
        weg, bloecke, _ = self.plane([pdf], "Fasse das gesamte Dokument zusammen.", vorrang={pdf["id"]})
        self.assertEqual(weg, "bloecke")
        erwartet = math.ceil(500_000 / kontext.material_budget(LOKAL))
        self.assertLessEqual(len(bloecke), erwartet + 1)
        self.assertLess(len(bloecke), len(pdf["chunks"]) // 5,
                        "Die Blöcke nutzen das Fenster nicht aus.")

    def test_the_cloud_needs_even_fewer_blocks(self):
        pdf = dokument("e", "handbuch-200-seiten.pdf", 500_000)
        _, lokal, _ = self.plane([pdf], "Fasse alles zusammen.", LOKAL, {pdf["id"]})
        _, cloud, _ = self.plane([pdf], "Fasse alles zusammen.", CLOUD, {pdf["id"]})
        self.assertLess(len(cloud), len(lokal))
        self.assertLessEqual(len(cloud), 2)

    def test_blocks_cover_the_whole_document(self):
        pdf = dokument("f", "handbuch.pdf", 300_000)
        _, bloecke, _ = self.plane([pdf], "Fasse das gesamte Dokument zusammen.", vorrang={pdf["id"]})
        abgedeckt = sum(len(t) for block in bloecke for _, t in block)
        self.assertGreaterEqual(abgedeckt, 300_000)

    def test_a_new_document_comes_complete_and_older_ones_by_relevance(self):
        neu = dokument("g", "neu.pdf", 20_000, wort="Vertrag")
        alt = dokument("h", "alt.pdf", 200_000, wort="Kündigungsfrist")
        weg, bloecke, zahlen = self.plane([neu, alt], "Wie lang ist die Kündigungsfrist?",
                                          vorrang={neu["id"]})
        self.assertEqual(weg, "direkt")
        namen = [label for label, _ in bloecke[0]]
        self.assertEqual(namen[0], "neu.pdf")
        self.assertTrue(any(label.startswith("alt.pdf – Teil") for label in namen))
        self.assertLessEqual(sum(len(t) for _, t in bloecke[0]), kontext.material_budget(LOKAL))

    def test_the_same_document_twice_counts_once(self):
        text = dokument("i", "doppelt.txt", 10_000)
        _, bloecke, zahlen = self.plane([text, text], "Was steht darin?")
        self.assertEqual(zahlen["dokumente"], 1)

    def test_nothing_stored_means_nothing_planned(self):
        self.assertEqual(self.plane([], "Frage")[0], "leer")


class RanglisteTests(Grundlage):
    """Die Auswahl nach Relevanz kennt jetzt ein Budget statt nur einer Anzahl."""

    def test_without_a_budget_the_old_limits_stay(self):
        text = dokument("j", "handbuch.pdf", 200_000)
        self.assertEqual(len(rank_context_chunks([text], "Was steht zur Gewährleistung?")), 12)

    def test_the_budget_is_never_exceeded(self):
        text = dokument("k", "handbuch.pdf", 200_000)
        auswahl = rank_context_chunks([text], "Was steht zur Gewährleistung?", budget_chars=50_000)
        self.assertLessEqual(sum(len(t) for _, t in auswahl), 50_000)
        self.assertGreater(len(auswahl), 6)

    def test_the_best_passages_are_chosen_first(self):
        text = dokument("l", "handbuch.pdf", 60_000)
        text["chunks"][7]["text"] = "Die Gewährleistung beträgt zwei Jahre. " * 40
        auswahl = rank_context_chunks([text], "Wie lange gilt die Gewährleistung?", budget_chars=4000)
        self.assertTrue(any("Gewährleistung beträgt" in t for _, t in auswahl))


class OllamaAufrufTests(Grundlage):
    """Jeder nicht streamende Aufruf läuft über ollama_chat_post — dort sitzt num_ctx."""

    def sende(self, payload: dict) -> dict:
        import asyncio

        import httpx

        from app.main import ollama_chat_post

        gesendet: dict = {}

        class Kunde:
            async def post(self, url, json):
                gesendet.update(json)
                return httpx.Response(200, json={"message": {"content": "ok"}},
                                      request=httpx.Request("POST", url))

        asyncio.run(ollama_chat_post(Kunde(), payload))
        return gesendet

    def test_a_local_call_gets_the_window(self):
        gesendet = self.sende({"model": LOKAL, "messages": [], "options": {"temperature": 0.1}})
        self.assertEqual(gesendet["options"]["num_ctx"], 32768)
        self.assertEqual(gesendet["options"]["temperature"], 0.1)

    def test_a_cloud_call_is_left_alone(self):
        gesendet = self.sende({"model": CLOUD, "messages": []})
        self.assertNotIn("num_ctx", gesendet.get("options", {}))

    def test_an_explicit_window_is_not_overwritten(self):
        gesendet = self.sende({"model": LOKAL, "messages": [], "options": {"num_ctx": 16384}})
        self.assertEqual(gesendet["options"]["num_ctx"], 16384)


class VerdrahtungTests(unittest.TestCase):
    """Der Chat-Pfad benutzt das Budget — die feste Grenze ist weg."""

    def setUp(self) -> None:
        self.quelltext = (WURZEL / "app/main.py").read_text(encoding="utf-8")

    def test_the_fixed_limit_is_gone(self):
        self.assertNotIn("direct_chars <= 18000", self.quelltext)
        self.assertIn("plane_material(", self.quelltext)

    def test_blocks_run_in_parallel_where_it_helps(self):
        self.assertIn("asyncio.Semaphore(gleichzeitig)", self.quelltext)
        self.assertIn("asyncio.as_completed(aufgaben)", self.quelltext)

    def test_joshi_shares_the_chat_window_but_never_below_16k(self):
        self.assertIn('{"num_ctx": joshi_kontextfenster()}', self.quelltext)
        self.assertIn("max(JOSHI_MINDESTKONTEXT, lokales_kontextfenster())", self.quelltext)

    def test_the_streaming_call_carries_the_window_setting(self):
        self.assertIn("**kontext_optionen(model),", self.quelltext)


if __name__ == "__main__":
    unittest.main()
